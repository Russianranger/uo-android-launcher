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
enum operation {
#define CALL(name, declaration, arguments, handle) OP_##name,
#include "commands.h"
#undef CALL
    OP_COUNT
};
static const char *names[] = {
#define CALL(name, declaration, arguments, handle) "vk" #name,
#include "commands.h"
#undef CALL
};
struct instance {
    VkInstance handle;
    PFN_vkGetInstanceProcAddr next;
    PFN_GetPhysicalDeviceProcAddr physical;
    struct instance *link;
};
struct device {
    VkDevice handle;
    PFN_vkGetDeviceProcAddr next;
    PFN_vkDestroyDevice destroy;
#define CALL(name, declaration, arguments, handle) PFN_vk##name name;
#include "commands.h"
#undef CALL
    struct device *link;
};
static pthread_mutex_t registry = PTHREAD_MUTEX_INITIALIZER;
static struct instance *instances;
static struct device *devices;
static atomic_ulong generation;
static _Thread_local struct device *cached_device;
static _Thread_local void *cached_key;
static _Thread_local unsigned long cached_generation;
struct stats {
    uint64_t since, calls[OP_COUNT], total[OP_COUNT], maximum[OP_COUNT], cpu[OP_COUNT], suppressed;
    unsigned written;
};
static _Thread_local struct stats stats;
static uint64_t clock_ns(clockid_t id){struct timespec t;if(clock_gettime(id,&t))return 0;return (uint64_t)t.tv_sec*1000000000ull+(uint64_t)t.tv_nsec;}
static void utc(char *out,size_t size){struct timespec t;struct tm tm;clock_gettime(CLOCK_REALTIME,&t);gmtime_r(&t.tv_sec,&tm);size_t n=strftime(out,size,"%Y-%m-%dT%H:%M:%S",&tm);snprintf(out+n,size-n,".%03ldZ",t.tv_nsec/1000000);}
static void report(uint64_t now){
    char timestamp[40];utc(timestamp,sizeof(timestamp));
    for(int i=0;i<OP_COUNT;i++)if(stats.calls[i])
        fprintf(stderr,"VULKAN_WINDOW utc=%s pid=%ld tid=%ld seconds=%.3f op=%s calls=%llu total_ms=%.3f max_ms=%.3f thread_cpu_ms=%.3f\n",timestamp,(long)getpid(),(long)syscall(SYS_gettid),(now-stats.since)/1e9,names[i],(unsigned long long)stats.calls[i],stats.total[i]/1e6,stats.maximum[i]/1e6,stats.cpu[i]/1e6);
    fprintf(stderr,"VULKAN_COUNTS utc=%s pid=%ld tid=%ld slow_records_suppressed=%llu\n",timestamp,(long)getpid(),(long)syscall(SYS_gettid),(unsigned long long)stats.suppressed);
    memset(&stats,0,sizeof(stats));stats.since=now;
}
static void observed(int operation,uint64_t start,uint64_t cpu,VkResult result){
    uint64_t end=clock_ns(CLOCK_MONOTONIC),elapsed=end-start,cpu_end=clock_ns(CLOCK_THREAD_CPUTIME_ID);
    if(!stats.since)stats.since=start;
    stats.calls[operation]++;stats.total[operation]+=elapsed;
    if(elapsed>stats.maximum[operation])stats.maximum[operation]=elapsed;
    uint64_t cpu_ns=cpu_end>=cpu?cpu_end-cpu:0;stats.cpu[operation]+=cpu_ns;
    if(elapsed>=50000000ull){
        if(stats.written<8){
            stats.written++;char timestamp[40];utc(timestamp,sizeof(timestamp));
            fprintf(stderr,"VULKAN_CALL utc=%s pid=%ld tid=%ld op=%s wall_ms=%.3f thread_cpu_ms=%.3f result=%d\n",timestamp,(long)getpid(),(long)syscall(SYS_gettid),names[operation],elapsed/1e6,cpu_ns/1e6,result);
        }else stats.suppressed++;
    }
    if(end-stats.since>=5000000000ull)report(end);
}
static void *dispatch_key(const void *handle){return *(void *const *)handle;}
static struct instance *instance_for(VkInstance handle){
    /* The loader can finish setting an instance's dispatch pointer after our
     * CreateInstance returns. Instance calls already supply the stable handle;
     * do not identify that lifetime by its mutable dispatch-table pointer. */
    pthread_mutex_lock(&registry);
    struct instance *item=instances;while(item&&item->handle!=handle)item=item->link;
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
#define CALL(name, declaration, arguments, handle) \
static VKAPI_ATTR VkResult VKAPI_CALL trace_##name declaration { \
    struct device *d=device_for(handle); \
    uint64_t start=clock_ns(CLOCK_MONOTONIC),cpu=clock_ns(CLOCK_THREAD_CPUTIME_ID); \
    VkResult result=d->name arguments; observed(OP_##name,start,cpu,result);return result; \
}
#include "commands.h"
#undef CALL

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
    pthread_mutex_lock(&registry);item->link=instances;instances=item;pthread_mutex_unlock(&registry);
    char timestamp[40];utc(timestamp,sizeof(timestamp));
    fprintf(stderr,"VULKAN_TRACE_ACTIVE utc=%s revision=1 pid=%ld tid=%ld long_call_ms=50 max_slow_records_per_thread_5s=8 passive=true\n",timestamp,(long)getpid(),(long)syscall(SYS_gettid));
    return result;
}
static VKAPI_ATTR void VKAPI_CALL trace_DestroyInstance(VkInstance instance,const VkAllocationCallbacks *allocator){
    struct instance *item=instance_for(instance);PFN_vkDestroyInstance destroy=(PFN_vkDestroyInstance)item->next(instance,"vkDestroyInstance");
    destroy(instance,allocator);pthread_mutex_lock(&registry);
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
    item->handle=*out;item->destroy=(PFN_vkDestroyDevice)item->next(*out,"vkDestroyDevice");
#define CALL(name, declaration, arguments, handle) item->name=(PFN_vk##name)item->next(*out,"vk" #name);
#include "commands.h"
#undef CALL
    pthread_mutex_lock(&registry);item->link=devices;devices=item;atomic_fetch_add_explicit(&generation,1,memory_order_release);pthread_mutex_unlock(&registry);
    return result;
}
static VKAPI_ATTR void VKAPI_CALL trace_DestroyDevice(VkDevice device,const VkAllocationCallbacks *allocator){
    struct device *item=device_for(device);item->destroy(device,allocator);
    if(stats.since)report(clock_ns(CLOCK_MONOTONIC));
    pthread_mutex_lock(&registry);struct device **link=&devices;while(*link!=item)link=&(*link)->link;*link=item->link;
    atomic_fetch_add_explicit(&generation,1,memory_order_release);pthread_mutex_unlock(&registry);free(item);
}
static PFN_vkVoidFunction wrapped(const char *name){
    if(!strcmp(name,"vkGetInstanceProcAddr"))return (PFN_vkVoidFunction)trace_GetInstanceProcAddr;
    if(!strcmp(name,"vkGetDeviceProcAddr"))return (PFN_vkVoidFunction)trace_GetDeviceProcAddr;
    if(!strcmp(name,"vkCreateInstance"))return (PFN_vkVoidFunction)trace_CreateInstance;
    if(!strcmp(name,"vkDestroyInstance"))return (PFN_vkVoidFunction)trace_DestroyInstance;
    if(!strcmp(name,"vkCreateDevice"))return (PFN_vkVoidFunction)trace_CreateDevice;
    if(!strcmp(name,"vkDestroyDevice"))return (PFN_vkVoidFunction)trace_DestroyDevice;
#define CALL(command, declaration, arguments, handle) if(!strcmp(name,"vk" #command))return (PFN_vkVoidFunction)trace_##command;
#include "commands.h"
#undef CALL
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
