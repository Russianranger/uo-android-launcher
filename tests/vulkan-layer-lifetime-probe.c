/* Model the loader finishing dispatch tables after the layer's create call.
 * This exercises the actual layer, including two overlapping instance lives,
 * physical-device lookup and queue/command-buffer device dispatch. */
#include "../native/graphics-diagnostics/layer.c"
#include <assert.h>
struct handle {void *dispatch;};
static int old_instance_table[2],instance_table[2],old_device_table,device_table;
static struct handle fake_instances[2],fake_physical,fake_device,fake_queue,fake_commands;
static int instance_creates,instance_destroys,device_destroys,buffer_calls,queue_calls,command_calls;
static VkInstance expected_instance;
static VKAPI_ATTR VkResult VKAPI_CALL create_instance(const VkInstanceCreateInfo *info,const VkAllocationCallbacks *allocator,VkInstance *out){
    (void)info;assert(!allocator);assert(instance_creates<2);
    int i=instance_creates++;fake_instances[i].dispatch=&old_instance_table[i];*out=(VkInstance)&fake_instances[i];return VK_SUCCESS;
}
static VKAPI_ATTR void VKAPI_CALL destroy_instance(VkInstance instance,const VkAllocationCallbacks *allocator){assert(!allocator);assert(instance==expected_instance);instance_destroys++;}
static VKAPI_ATTR VkResult VKAPI_CALL create_device(VkPhysicalDevice physical,const VkDeviceCreateInfo *info,const VkAllocationCallbacks *allocator,VkDevice *out){
    (void)info;assert(physical==(VkPhysicalDevice)&fake_physical);assert(!allocator);fake_device.dispatch=&old_device_table;*out=(VkDevice)&fake_device;return VK_SUCCESS;
}
static VKAPI_ATTR void VKAPI_CALL destroy_device(VkDevice device,const VkAllocationCallbacks *allocator){assert(device==(VkDevice)&fake_device);assert(!allocator);device_destroys++;}
static VKAPI_ATTR VkResult VKAPI_CALL create_buffer(VkDevice device,const VkBufferCreateInfo *info,const VkAllocationCallbacks *allocator,VkBuffer *buffer){
    assert(device==(VkDevice)&fake_device);assert(info->size==4096);assert(!allocator);*buffer=(VkBuffer)(uintptr_t)0x1234;buffer_calls++;return VK_SUCCESS;
}
static VKAPI_ATTR VkResult VKAPI_CALL queue_submit(VkQueue queue,uint32_t count,const VkSubmitInfo *infos,VkFence fence){assert(queue==(VkQueue)&fake_queue);assert(count==0&&!infos&&!fence);queue_calls++;return VK_SUCCESS;}
static VKAPI_ATTR VkResult VKAPI_CALL end_commands(VkCommandBuffer commands){assert(commands==(VkCommandBuffer)&fake_commands);command_calls++;return VK_SUCCESS;}
static VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL device_proc(VkDevice device,const char *name){
    assert(device==(VkDevice)&fake_device);
    if(!strcmp(name,"vkDestroyDevice"))return (PFN_vkVoidFunction)destroy_device;
    if(!strcmp(name,"vkCreateBuffer"))return (PFN_vkVoidFunction)create_buffer;
    if(!strcmp(name,"vkQueueSubmit"))return (PFN_vkVoidFunction)queue_submit;
    if(!strcmp(name,"vkEndCommandBuffer"))return (PFN_vkVoidFunction)end_commands;
    return NULL;
}
static VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL instance_proc(VkInstance instance,const char *name){
    if(!strcmp(name,"vkCreateInstance"))return (PFN_vkVoidFunction)create_instance;
    if(!strcmp(name,"vkDestroyInstance"))return (PFN_vkVoidFunction)destroy_instance;
    if(!strcmp(name,"vkCreateDevice")){assert(instance==expected_instance);return (PFN_vkVoidFunction)create_device;}
    return NULL;
}
int main(void){
    for(int i=0;i<2;i++){
        VkLayerInstanceLink link={.pfnNextGetInstanceProcAddr=instance_proc};
        VkLayerInstanceCreateInfo chain={.sType=VK_STRUCTURE_TYPE_LOADER_INSTANCE_CREATE_INFO,.function=VK_LAYER_LINK_INFO,.u={.pLayerInfo=&link}};
        VkInstanceCreateInfo info={.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,.pNext=&chain};VkInstance out;
        assert(trace_CreateInstance(&info,NULL,&out)==VK_SUCCESS);assert(out==(VkInstance)&fake_instances[i]);
        fake_instances[i].dispatch=&instance_table[i];
    }
    expected_instance=(VkInstance)&fake_instances[1];fake_physical.dispatch=&instance_table[1];
    VkLayerDeviceLink link={.pfnNextGetInstanceProcAddr=instance_proc,.pfnNextGetDeviceProcAddr=device_proc};
    VkLayerDeviceCreateInfo chain={.sType=VK_STRUCTURE_TYPE_LOADER_DEVICE_CREATE_INFO,.function=VK_LAYER_LINK_INFO,.u={.pLayerInfo=&link}};
    VkDeviceCreateInfo info={.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,.pNext=&chain};VkDevice device;
    assert(trace_CreateDevice((VkPhysicalDevice)&fake_physical,&info,NULL,&device)==VK_SUCCESS);
    fake_device.dispatch=fake_queue.dispatch=fake_commands.dispatch=&device_table;
    PFN_vkCreateBuffer buffer=(PFN_vkCreateBuffer)trace_GetDeviceProcAddr(device,"vkCreateBuffer");
    VkBufferCreateInfo buffer_info={.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,.size=4096};VkBuffer out;
    assert(buffer(device,&buffer_info,NULL,&out)==VK_SUCCESS&&out==(VkBuffer)(uintptr_t)0x1234);
    assert(trace_QueueSubmit((VkQueue)&fake_queue,0,NULL,VK_NULL_HANDLE)==VK_SUCCESS);
    assert(trace_EndCommandBuffer((VkCommandBuffer)&fake_commands)==VK_SUCCESS);
    assert(!trace_GetDeviceProcAddr(device,"vkMissingFunction"));trace_DestroyDevice(device,NULL);
    expected_instance=(VkInstance)&fake_instances[0];trace_DestroyInstance(expected_instance,NULL);
    expected_instance=(VkInstance)&fake_instances[1];trace_DestroyInstance(expected_instance,NULL);
    assert(instance_destroys==2&&device_destroys==1&&buffer_calls==1&&queue_calls==1&&command_calls==1&&!instances&&!devices);
    puts("VULKAN_LAYER_LIFETIME_OK late_dispatch=true instances=2 physical_queue_command=true calls_once=true");return 0;
}
