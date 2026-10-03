#define _GNU_SOURCE
#include <vulkan/vk_layer.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/syscall.h>

/* An explicit Linux loader layer, below Wine's Vulkan thunk. Every observed
 * call is forwarded once with identical arguments and its original result.
 * No fences, flushes, submissions, shader caches or validation are added. */
#include "tracker.h"
enum operation {
#define CALL(name, declaration, arguments, handle, before, after) OP_##name,
#include "commands.h"
#undef CALL
#define VOID_CALL(name, declaration, arguments, handle, before, after) OP_##name,
#include "void_commands.h"
#undef VOID_CALL
    OP_COUNT
};
static const char *names[] = {
#define CALL(name, declaration, arguments, handle, before, after) "vk" #name,
#include "commands.h"
#undef CALL
#define VOID_CALL(name, declaration, arguments, handle, before, after) "vk" #name,
#include "void_commands.h"
#undef VOID_CALL
};
struct instance {
    VkInstance handle;
    PFN_vkGetInstanceProcAddr next;
    PFN_vkDestroyInstance destroy;
    PFN_GetPhysicalDeviceProcAddr physical;
    struct instance *link;
};
struct device {
    VkDevice handle;
    PFN_vkGetDeviceProcAddr next;
    PFN_vkDestroyDevice destroy;
#define CALL(name, declaration, arguments, handle, before, after) PFN_vk##name name;
#include "commands.h"
#undef CALL
#define VOID_CALL(name, declaration, arguments, handle, before, after) PFN_vk##name name;
#include "void_commands.h"
#undef VOID_CALL
    struct tracker track;
    struct device *link;
};
static pthread_mutex_t registry = PTHREAD_MUTEX_INITIALIZER;
static struct instance *instances;
static struct device *devices;
static int lifetime_debug;
static atomic_ulong generation;
static atomic_ullong device_identity;
static _Thread_local struct device *cached_device;
static _Thread_local void *cached_key;
static _Thread_local unsigned long cached_generation;
struct stats {
    uint64_t since, calls[OP_COUNT], total[OP_COUNT], maximum[OP_COUNT], cpu[OP_COUNT], suppressed;
    uint64_t bookkeeping, bookkeeping_max, image_creates, image_2048_creates, allocation_bytes;
    unsigned written;
};
static _Thread_local struct stats stats;
static uint64_t clock_ns(clockid_t id){struct timespec t;if(clock_gettime(id,&t))return 0;return (uint64_t)t.tv_sec*1000000000ull+(uint64_t)t.tv_nsec;}
static void utc(char *out,size_t size){struct timespec t;struct tm tm;clock_gettime(CLOCK_REALTIME,&t);gmtime_r(&t.tv_sec,&tm);size_t n=strftime(out,size,"%Y-%m-%dT%H:%M:%S",&tm);snprintf(out+n,size-n,".%03ldZ",t.tv_nsec/1000000);}
static const char *fence_origin(unsigned origin) {
    static const char *origins[]={"unattributed","submit","acquire","created_signaled","reset_unattributed","truncated_reset_unknown"};
    return origin<sizeof(origins)/sizeof(*origins)?origins[origin]:"unknown";
}
static void print_correlation(const struct correlation *c,uint64_t start) {
    fprintf(stderr," device_id=%llu queue_id=%llu queue_family=%u queue_index=%u submit_id=%llu prior_queue_submit_id=%llu acquire_id=%llu object_id=%llu batches=%u commands_seen=%u wait_semaphores_seen=%u signal_semaphores_seen=%u observed_transfer_calls=%llu observed_draw_calls=%llu observed_dispatch_calls=%llu observed_render_pass_calls=%llu observed_secondary_calls=%llu first_copy_image_id=%llu image_width=%u image_height=%u image_depth=%u image_format=%u image_usage=%u image_levels=%u image_layers=%u allocation_bytes=%llu memory_type=%u fence_count=%u wait_all=%u timeout_ns=%llu refs_omitted=%u missing_refs=%u evidence_uncertain=%u fences=",
        (unsigned long long)c->device_id,(unsigned long long)c->queue_id,c->queue_family,c->queue_index,
        (unsigned long long)c->submit_id,(unsigned long long)c->prior_queue_submit_id,(unsigned long long)c->acquire_id,(unsigned long long)c->object_id,
        c->batch_count,c->command_count,c->wait_semaphores,c->signal_semaphores,
        (unsigned long long)c->transfer,(unsigned long long)c->draw,(unsigned long long)c->dispatch,
        (unsigned long long)c->render_pass,(unsigned long long)c->secondary,(unsigned long long)c->image_id,
        c->width,c->height,c->depth,c->format,c->usage,c->levels,c->layers,(unsigned long long)c->allocation_bytes,c->memory_type,
        c->fence_count,c->wait_all,(unsigned long long)c->timeout,c->refs_omitted,c->missing,c->uncertain);
    if(!c->fence_refs)fputs("none",stderr);
    for(uint32_t i=0;i<c->fence_refs;i++) {
        const struct fence_reference *f=&c->fences[i];
        fprintf(stderr,"%s%llu:",i?",":"",(unsigned long long)f->id);
        if(f->generation)fprintf(stderr,"%llu:",(unsigned long long)f->generation);else fputs("unknown:",stderr);
        fprintf(stderr,"%s:%llu:%llu:",fence_origin(f->origin),(unsigned long long)f->origin_id,(unsigned long long)f->queue_id);
        if(f->origin_end&&start>=f->origin_end)fprintf(stderr,"%.3f",(start-f->origin_end)/1e6);else fputs("unknown",stderr);
    }
    fputs(" fence_submit_evidence=",stderr);
    if(!c->fence_refs)fputs("none",stderr);
    for(uint32_t i=0;i<c->fence_refs;i++) {
        const struct fence_reference *f=&c->fences[i];const struct submit_evidence *e=&f->evidence;
        fprintf(stderr,"%s%llu:%u:%u:%llu:%llu:%llu:%llu:%llu:%llu:%u:%u:%u:%u:%.3f",i?",":"",(unsigned long long)f->id,e->batches,e->commands,(unsigned long long)e->transfer,(unsigned long long)e->draw,(unsigned long long)e->dispatch,(unsigned long long)e->render_pass,(unsigned long long)e->secondary,(unsigned long long)e->image_id,e->width,e->height,e->uncertain,e->missing,e->wall_ns/1e6);
    }
}
static void report(uint64_t now,struct tracker *track){
    char timestamp[40];utc(timestamp,sizeof(timestamp));
    for(int i=0;i<OP_COUNT;i++)if(stats.calls[i])
        fprintf(stderr,"VULKAN_WINDOW utc=%s pid=%ld tid=%ld seconds=%.3f op=%s calls=%llu total_ms=%.3f max_ms=%.3f thread_cpu_ms=%.3f\n",timestamp,(long)getpid(),(long)syscall(SYS_gettid),(now-stats.since)/1e9,names[i],(unsigned long long)stats.calls[i],stats.total[i]/1e6,stats.maximum[i]/1e6,stats.cpu[i]/1e6);
    pthread_mutex_lock(&track->mutex);uint64_t overflow=track->overflow,missing=track->missing,truncated=track->truncated;pthread_mutex_unlock(&track->mutex);
    fprintf(stderr,"VULKAN_COUNTS utc=%s pid=%ld tid=%ld slow_records_suppressed=%llu metadata_ms=%.3f metadata_max_ms=%.3f scope=thread_all_devices tracker_device_id=%llu tracking_overflow_total=%llu tracking_missing_total=%llu tracking_truncated_total=%llu image_creates=%llu image_2048_square_creates=%llu allocation_bytes=%llu\n",timestamp,(long)getpid(),(long)syscall(SYS_gettid),(unsigned long long)stats.suppressed,stats.bookkeeping/1e6,stats.bookkeeping_max/1e6,(unsigned long long)track->device_id,(unsigned long long)overflow,(unsigned long long)missing,(unsigned long long)truncated,(unsigned long long)stats.image_creates,(unsigned long long)stats.image_2048_creates,(unsigned long long)stats.allocation_bytes);
    memset(&stats,0,sizeof(stats));stats.since=now;
}
static void observed(int operation,uint64_t start,uint64_t end,uint64_t cpu,uint64_t cpu_end,VkResult result,const struct correlation *correlation,uint64_t bookkeeping,struct tracker *track){
    uint64_t elapsed=end>=start?end-start:0;
    if(!stats.since)stats.since=start;
    stats.calls[operation]++;stats.total[operation]+=elapsed;
    if(operation==OP_CreateImage&&result==VK_SUCCESS){stats.image_creates++;if(correlation->width==2048&&correlation->height==2048)stats.image_2048_creates++;}
    if(operation==OP_AllocateMemory&&result==VK_SUCCESS)stats.allocation_bytes+=correlation->allocation_bytes;
    if(elapsed>stats.maximum[operation])stats.maximum[operation]=elapsed;
    uint64_t cpu_ns=cpu_end>=cpu?cpu_end-cpu:0;stats.cpu[operation]+=cpu_ns;
    stats.bookkeeping+=bookkeeping;if(bookkeeping>stats.bookkeeping_max)stats.bookkeeping_max=bookkeeping;
    if(elapsed>=50000000ull){
        if(stats.written<8){
            stats.written++;char timestamp[40];utc(timestamp,sizeof(timestamp));
            flockfile(stderr);
            fprintf(stderr,"VULKAN_CALL utc=%s pid=%ld tid=%ld op=%s wall_ms=%.3f thread_cpu_ms=%.3f result=%d metadata_ms=%.3f",timestamp,(long)getpid(),(long)syscall(SYS_gettid),names[operation],elapsed/1e6,cpu_ns/1e6,result,bookkeeping/1e6);
            print_correlation(correlation,start);fputc('\n',stderr);funlockfile(stderr);
        }else stats.suppressed++;
    }
    if(end-stats.since>=5000000000ull)report(end,track);
}
static void *dispatch_key(const void *handle){return *(void *const *)handle;}
static struct instance *instance_for(VkInstance handle){
    /* The loader can finish setting dispatch pointers after CreateInstance.
     * Prefer the stable handle; allow loader aliases using the current table. */
    pthread_mutex_lock(&registry);
    void *key=dispatch_key(handle);
    struct instance *item=instances;while(item&&item->handle!=handle&&dispatch_key(item->handle)!=key)item=item->link;
    pthread_mutex_unlock(&registry);return item;
}
static struct instance *physical_instance(VkPhysicalDevice handle){
    void *key=dispatch_key(handle);pthread_mutex_lock(&registry);
    struct instance *item=instances;
    while(item&&dispatch_key(item->handle)!=key)item=item->link;
    pthread_mutex_unlock(&registry);return item;
}
static struct device *device_for(const void *handle){
    void *key=dispatch_key(handle);unsigned long current=atomic_load_explicit(&generation,memory_order_acquire);
    if(cached_device&&cached_key==key&&cached_generation==current)return cached_device;
    pthread_mutex_lock(&registry);struct device *item=devices;
    while(item&&item->handle!=(VkDevice)handle&&dispatch_key(item->handle)!=key)item=item->link;
    cached_device=item;cached_key=key;cached_generation=current;pthread_mutex_unlock(&registry);return item;
}
#define CALL(name, declaration, arguments, handle, before, after) \
static VKAPI_ATTR VkResult VKAPI_CALL trace_##name declaration { \
    uint64_t metadata_start=clock_ns(CLOCK_MONOTONIC); \
    struct device *d=device_for(handle); \
    struct correlation c={.device_id=d->track.device_id}; \
    before; \
    uint64_t cpu=clock_ns(CLOCK_THREAD_CPUTIME_ID),start=clock_ns(CLOCK_MONOTONIC); \
    VkResult result=d->name arguments; \
    uint64_t end=clock_ns(CLOCK_MONOTONIC),cpu_end=clock_ns(CLOCK_THREAD_CPUTIME_ID); \
    after; \
    uint64_t metadata_end=clock_ns(CLOCK_MONOTONIC); \
    observed(OP_##name,start,end,cpu,cpu_end,result,&c,(start-metadata_start)+(metadata_end-end),&d->track);return result; \
}
#include "commands.h"
#undef CALL
#define VOID_CALL(name, declaration, arguments, handle, before, after) \
static VKAPI_ATTR void VKAPI_CALL trace_##name declaration { \
    uint64_t metadata_start=clock_ns(CLOCK_MONOTONIC); \
    struct device *d=device_for(handle);struct correlation c={.device_id=d->track.device_id}; \
    before; \
    uint64_t cpu=clock_ns(CLOCK_THREAD_CPUTIME_ID),start=clock_ns(CLOCK_MONOTONIC); \
    d->name arguments; \
    uint64_t end=clock_ns(CLOCK_MONOTONIC),cpu_end=clock_ns(CLOCK_THREAD_CPUTIME_ID); \
    after;uint64_t metadata_end=clock_ns(CLOCK_MONOTONIC); \
    observed(OP_##name,start,end,cpu,cpu_end,VK_SUCCESS,&c,(start-metadata_start)+(metadata_end-end),&d->track); \
}
#include "void_commands.h"
#undef VOID_CALL

static VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL trace_GetInstanceProcAddr(VkInstance instance,const char *name);
static VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL trace_GetDeviceProcAddr(VkDevice device,const char *name);
static VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL trace_GetPhysicalDeviceProcAddr(VkInstance instance,const char *name);
static VKAPI_ATTR VkResult VKAPI_CALL trace_CreateInstance(const VkInstanceCreateInfo *info,const VkAllocationCallbacks *allocator,VkInstance *out){
    VkLayerInstanceCreateInfo *chain=(VkLayerInstanceCreateInfo *)info->pNext;
    while(chain&&(chain->sType!=VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO||chain->function!=VK_LAYER_LINK_INFO))chain=(VkLayerInstanceCreateInfo *)chain->pNext;
    if(!chain)return VK_ERROR_INITIALIZATION_FAILED;
    struct instance *item=calloc(1,sizeof(*item));if(!item)return VK_ERROR_OUT_OF_HOST_MEMORY;
    item->next=chain->u.pLayerInfo->pfnNextGetInstanceProcAddr;item->physical=chain->u.pLayerInfo->pfnNextGetPhysicalDeviceProcAddr;
    PFN_vkCreateInstance create=(PFN_vkCreateInstance)item->next(VK_NULL_HANDLE,"vkCreateInstance");
    chain->u.pLayerInfo=chain->u.pLayerInfo->pNext;
    VkResult result=create(info,allocator,out);if(result!=VK_SUCCESS){free(item);return result;}
    item->handle=*out;
    /* Cache the next lifetime callback before the loader finalizes dispatch.
     * Resolving it again during destruction can select a different terminator
     * on the retained 1.3.239 loader used by Wine/FEX. */
    item->destroy=(PFN_vkDestroyInstance)item->next(*out,"vkDestroyInstance");
    lifetime_debug=getenv("MEMENTO_VULKAN_LIFETIME_DEBUG")!=NULL;
    if(lifetime_debug)fprintf(stderr,"VULKAN_LIFETIME create instance=%p dispatch=%p next=%p\n",(void *)*out,dispatch_key(*out),(void *)item->next);
    pthread_mutex_lock(&registry);item->link=instances;instances=item;pthread_mutex_unlock(&registry);
    char timestamp[40];utc(timestamp,sizeof(timestamp));
    fprintf(stderr,"VULKAN_TRACE_ACTIVE utc=%s revision=2 pid=%ld tid=%ld long_call_ms=50 max_slow_records_per_thread_5s=8 passive=true fence_refs_max=8 submit_refs_max=64 tracked_queues_max=16 tracked_fences_max=256 tracked_commands_max=512 tracked_images_max=512 fence_format=id:generation:origin:origin_id:queue_id:age_ms incomplete_command_coverage=true metadata_excludes_log_io=true window_scope=thread_all_devices\n",timestamp,(long)getpid(),(long)syscall(SYS_gettid));
    return result;
}
static VKAPI_ATTR void VKAPI_CALL trace_DestroyInstance(VkInstance instance,const VkAllocationCallbacks *allocator){
    struct instance *item=instance_for(instance);
    if(lifetime_debug)fprintf(stderr,"VULKAN_LIFETIME destroy instance=%p dispatch=%p record=%p\n",(void *)instance,dispatch_key(instance),(void *)item);
    PFN_vkDestroyInstance destroy=item->destroy;
    if(lifetime_debug)fprintf(stderr,"VULKAN_LIFETIME forward_destroy function=%p\n",(void *)destroy);
    destroy(instance,allocator);
    if(lifetime_debug)fprintf(stderr,"VULKAN_LIFETIME destroy_returned\n");
    pthread_mutex_lock(&registry);
    struct instance **link=&instances;while(*link!=item)link=&(*link)->link;*link=item->link;
    pthread_mutex_unlock(&registry);free(item);
}
static VKAPI_ATTR VkResult VKAPI_CALL trace_CreateDevice(VkPhysicalDevice physical,const VkDeviceCreateInfo *info,const VkAllocationCallbacks *allocator,VkDevice *out){
    struct instance *instance=physical_instance(physical);
    VkLayerDeviceCreateInfo *chain=(VkLayerDeviceCreateInfo *)info->pNext;
    while(chain&&(chain->sType!=VK_STRUCTURE_TYPE_LOADER_DEVICE_CREATE_INFO||chain->function!=VK_LAYER_LINK_INFO))chain=(VkLayerDeviceCreateInfo *)chain->pNext;
    if(!chain)return VK_ERROR_INITIALIZATION_FAILED;
    struct device *item=calloc(1,sizeof(*item));if(!item)return VK_ERROR_OUT_OF_HOST_MEMORY;
    item->next=chain->u.pLayerInfo->pfnNextGetDeviceProcAddr;
    PFN_vkCreateDevice create=(PFN_vkCreateDevice)chain->u.pLayerInfo->pfnNextGetInstanceProcAddr(instance->handle,"vkCreateDevice");
    chain->u.pLayerInfo=chain->u.pLayerInfo->pNext;
    VkResult result=create(physical,info,allocator,out);if(result!=VK_SUCCESS){free(item);return result;}
    pthread_mutex_init(&item->track.mutex,NULL);item->track.device_id=atomic_fetch_add_explicit(&device_identity,1,memory_order_relaxed)+1;
    item->handle=*out;item->destroy=(PFN_vkDestroyDevice)item->next(*out,"vkDestroyDevice");
#define CALL(name, declaration, arguments, handle, before, after) item->name=(PFN_vk##name)item->next(*out,"vk" #name);
#include "commands.h"
#undef CALL
#define VOID_CALL(name, declaration, arguments, handle, before, after) item->name=(PFN_vk##name)item->next(*out,"vk" #name);
#include "void_commands.h"
#undef VOID_CALL
    pthread_mutex_lock(&registry);item->link=devices;devices=item;atomic_fetch_add_explicit(&generation,1,memory_order_release);pthread_mutex_unlock(&registry);
    return result;
}
static VKAPI_ATTR void VKAPI_CALL trace_DestroyDevice(VkDevice device,const VkAllocationCallbacks *allocator){
    struct device *item=device_for(device);item->destroy(device,allocator);
    if(stats.since)report(clock_ns(CLOCK_MONOTONIC),&item->track);
    pthread_mutex_lock(&registry);struct device **link=&devices;while(*link!=item)link=&(*link)->link;*link=item->link;
    atomic_fetch_add_explicit(&generation,1,memory_order_release);pthread_mutex_unlock(&registry);pthread_mutex_destroy(&item->track.mutex);free(item);
}
static PFN_vkVoidFunction wrapped(const char *name){
    if(!strcmp(name,"vkGetInstanceProcAddr"))return (PFN_vkVoidFunction)trace_GetInstanceProcAddr;
    if(!strcmp(name,"vkGetDeviceProcAddr"))return (PFN_vkVoidFunction)trace_GetDeviceProcAddr;
    if(!strcmp(name,"vkCreateInstance"))return (PFN_vkVoidFunction)trace_CreateInstance;
    if(!strcmp(name,"vkDestroyInstance"))return (PFN_vkVoidFunction)trace_DestroyInstance;
    if(!strcmp(name,"vkCreateDevice"))return (PFN_vkVoidFunction)trace_CreateDevice;
    if(!strcmp(name,"vkDestroyDevice"))return (PFN_vkVoidFunction)trace_DestroyDevice;
#define CALL(command, declaration, arguments, handle, before, after) if(!strcmp(name,"vk" #command))return (PFN_vkVoidFunction)trace_##command;
#include "commands.h"
#undef CALL
#define VOID_CALL(command, declaration, arguments, handle, before, after) if(!strcmp(name,"vk" #command))return (PFN_vkVoidFunction)trace_##command;
#include "void_commands.h"
#undef VOID_CALL
    return NULL;
}
static VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL trace_GetInstanceProcAddr(VkInstance instance,const char *name){
    if(!name)return NULL;
    if(!strcmp(name,"vkGetInstanceProcAddr")||!strcmp(name,"vkCreateInstance"))return wrapped(name);
    if(!instance)return NULL;
    PFN_vkVoidFunction next=instance_for(instance)->next(instance,name);if(!next)return NULL;
    PFN_vkVoidFunction hook=wrapped(name);return hook?hook:next;
}
static VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL trace_GetDeviceProcAddr(VkDevice device,const char *name){
    if(!device||!name)return NULL;
    PFN_vkVoidFunction next=device_for(device)->next(device,name);if(!next)return NULL;
    PFN_vkVoidFunction hook=wrapped(name);return hook?hook:next;
}
static VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL trace_GetPhysicalDeviceProcAddr(VkInstance instance,const char *name){
    if(!instance||!name)return NULL;
    struct instance *item=instance_for(instance);return item->physical?item->physical(instance,name):item->next(instance,name);
}
VKAPI_ATTR VkResult VKAPI_CALL vkNegotiateLoaderLayerInterfaceVersion(VkNegotiateLayerInterface *version){
    if(!version||version->sType!=LAYER_NEGOTIATE_INTERFACE_STRUCT||version->loaderLayerInterfaceVersion<2)return VK_ERROR_INITIALIZATION_FAILED;
    version->loaderLayerInterfaceVersion=2;version->pfnGetInstanceProcAddr=trace_GetInstanceProcAddr;
    version->pfnGetDeviceProcAddr=trace_GetDeviceProcAddr;version->pfnGetPhysicalDeviceProcAddr=trace_GetPhysicalDeviceProcAddr;return VK_SUCCESS;
}
