#define _POSIX_C_SOURCE 200809L
#include <vulkan/vulkan.h>
#include <stdio.h>
#include <string.h>
#define OK(call) do {VkResult r=(call);if(r!=VK_SUCCESS){fprintf(stderr,"%s failed %d\n",#call,r);return 1;}}while(0)
int main(int argc,char **argv){
    (void)argv;
    VkInstanceCreateInfo instance_info={.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};VkInstance instance;
    OK(vkCreateInstance(&instance_info,NULL,&instance));
    uint32_t count=1;VkPhysicalDevice physical;OK(vkEnumeratePhysicalDevices(instance,&count,&physical));if(!count)return 2;
    uint32_t families=0;vkGetPhysicalDeviceQueueFamilyProperties(physical,&families,NULL);
    VkQueueFamilyProperties properties[64];if(families>64)return 3;vkGetPhysicalDeviceQueueFamilyProperties(physical,&families,properties);
    uint32_t family=0;while(family<families&&!(properties[family].queueFlags&VK_QUEUE_GRAPHICS_BIT))family++;if(family==families)return 4;
    float priority=1;VkDeviceQueueCreateInfo queue_info={.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,.queueFamilyIndex=family,.queueCount=1,.pQueuePriorities=&priority};
    VkDeviceCreateInfo device_info={.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,.queueCreateInfoCount=1,.pQueueCreateInfos=&queue_info};VkDevice device;
    OK(vkCreateDevice(physical,&device_info,NULL,&device));VkQueue queue;vkGetDeviceQueue(device,family,0,&queue);
    /* A minimal valid no-op compute shader exercises real driver compilation. */
    const uint32_t code[]={0x07230203,0x00010000,0,5,0,0x00020011,1,0x0003000e,0,1,
        0x0005000f,5,3,0x6e69616d,0,0x00060010,3,17,1,1,1,0x00020013,1,
        0x00030021,2,1,0x00050036,1,3,0,2,0x000200f8,4,0x000100fd,0x00010038};
    VkShaderModuleCreateInfo shader_info={.sType=VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,.codeSize=sizeof(code),.pCode=code};VkShaderModule shader;
    OK(vkCreateShaderModule(device,&shader_info,NULL,&shader));
    VkPipelineLayoutCreateInfo layout_info={.sType=VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};VkPipelineLayout layout;
    OK(vkCreatePipelineLayout(device,&layout_info,NULL,&layout));
    VkComputePipelineCreateInfo pipeline_info={.sType=VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,.stage={.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,.stage=VK_SHADER_STAGE_COMPUTE_BIT,.module=shader,.pName="main"},.layout=layout};VkPipeline pipeline;
    OK(vkCreateComputePipelines(device,VK_NULL_HANDLE,1,&pipeline_info,NULL,&pipeline));
    vkDestroyPipeline(device,pipeline,NULL);vkDestroyPipelineLayout(device,layout,NULL);vkDestroyShaderModule(device,shader,NULL);
    VkBufferCreateInfo buffer_info={.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,.size=4096,.usage=VK_BUFFER_USAGE_TRANSFER_DST_BIT|VK_BUFFER_USAGE_TRANSFER_SRC_BIT,.sharingMode=VK_SHARING_MODE_EXCLUSIVE};VkBuffer buffer;
    OK(vkCreateBuffer(device,&buffer_info,NULL,&buffer));VkMemoryRequirements requirements;vkGetBufferMemoryRequirements(device,buffer,&requirements);
    VkPhysicalDeviceMemoryProperties memory_properties;vkGetPhysicalDeviceMemoryProperties(physical,&memory_properties);uint32_t type=0;
    while(type<memory_properties.memoryTypeCount&&(!(requirements.memoryTypeBits&(1u<<type))||((memory_properties.memoryTypes[type].propertyFlags&(VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT))!=(VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT))))type++;
    if(type==memory_properties.memoryTypeCount)return 5;
    VkMemoryAllocateInfo allocation={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,.allocationSize=requirements.size,.memoryTypeIndex=type};VkDeviceMemory memory;
    OK(vkAllocateMemory(device,&allocation,NULL,&memory));OK(vkBindBufferMemory(device,buffer,memory,0));
    /* A 2048-square sampled image models atlas metadata while copying just
     * one 32-square region; the layer must not change buffer pixels or waits. */
    VkImageCreateInfo image_info={.sType=VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,.imageType=VK_IMAGE_TYPE_2D,.format=VK_FORMAT_R8G8B8A8_UNORM,.extent={2048,2048,1},.mipLevels=1,.arrayLayers=1,.samples=VK_SAMPLE_COUNT_1_BIT,.tiling=VK_IMAGE_TILING_OPTIMAL,.usage=VK_IMAGE_USAGE_TRANSFER_DST_BIT|VK_IMAGE_USAGE_SAMPLED_BIT,.sharingMode=VK_SHARING_MODE_EXCLUSIVE,.initialLayout=VK_IMAGE_LAYOUT_UNDEFINED};VkImage image;
    OK(vkCreateImage(device,&image_info,NULL,&image));VkMemoryRequirements image_requirements;vkGetImageMemoryRequirements(device,image,&image_requirements);
    uint32_t image_type=0;while(image_type<memory_properties.memoryTypeCount&&!(image_requirements.memoryTypeBits&(1u<<image_type)))image_type++;if(image_type==memory_properties.memoryTypeCount)return 8;
    VkMemoryAllocateInfo image_allocation={.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,.allocationSize=image_requirements.size,.memoryTypeIndex=image_type};VkDeviceMemory image_memory;
    OK(vkAllocateMemory(device,&image_allocation,NULL,&image_memory));OK(vkBindImageMemory(device,image,image_memory,0));
    VkCommandPoolCreateInfo pool_info={.sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,.queueFamilyIndex=family};VkCommandPool pool;OK(vkCreateCommandPool(device,&pool_info,NULL,&pool));
    VkCommandBufferAllocateInfo commands_info={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,.commandPool=pool,.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY,.commandBufferCount=1};VkCommandBuffer commands;
    OK(vkAllocateCommandBuffers(device,&commands_info,&commands));VkCommandBufferBeginInfo begin={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};OK(vkBeginCommandBuffer(commands,&begin));
    vkCmdFillBuffer(commands,buffer,0,4096,0x1234abcd);
    VkBufferMemoryBarrier buffer_barrier={.sType=VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER,.srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT,.dstAccessMask=VK_ACCESS_TRANSFER_READ_BIT,.srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,.buffer=buffer,.offset=0,.size=4096};
    VkImageMemoryBarrier image_barrier={.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,.dstAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT,.oldLayout=VK_IMAGE_LAYOUT_UNDEFINED,.newLayout=VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,.srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,.image=image,.subresourceRange={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.levelCount=1,.layerCount=1}};
    vkCmdPipelineBarrier(commands,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_TRANSFER_BIT,0,0,NULL,1,&buffer_barrier,1,&image_barrier);
    VkBufferImageCopy image_copy={.imageSubresource={.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT,.layerCount=1},.imageExtent={32,32,1}};
    vkCmdCopyBufferToImage(commands,buffer,image,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,1,&image_copy);
    VkBufferMemoryBarrier host_barrier={.sType=VK_STRUCTURE_TYPE_BUFFER_MEMORY_BARRIER,.srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT,.dstAccessMask=VK_ACCESS_HOST_READ_BIT,.srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,.buffer=buffer,.offset=0,.size=4096};
    vkCmdPipelineBarrier(commands,VK_PIPELINE_STAGE_TRANSFER_BIT,VK_PIPELINE_STAGE_HOST_BIT,0,0,NULL,1,&host_barrier,0,NULL);OK(vkEndCommandBuffer(commands));
    VkFenceCreateInfo fence_info={.sType=VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};VkFence fence;OK(vkCreateFence(device,&fence_info,NULL,&fence));
    VkSubmitInfo submit={.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO,.commandBufferCount=1,.pCommandBuffers=&commands};OK(vkQueueSubmit(queue,1,&submit,fence));
    OK(vkWaitForFences(device,1,&fence,VK_TRUE,10000000000ull));uint32_t *pixels;OK(vkMapMemory(device,memory,0,4096,0,(void **)&pixels));
    for(int i=0;i<1024;i++)if(pixels[i]!=0x1234abcd)return 6;
    OK(vkResetFences(device,1,&fence));OK(vkQueueSubmit(queue,1,&submit,fence));OK(vkWaitForFences(device,1,&fence,VK_TRUE,10000000000ull));
    if(argc>1){
        OK(vkResetFences(device,1,&fence));
        for(int i=0;i<12;i++)if(vkWaitForFences(device,1,&fence,VK_TRUE,60000000ull)!=VK_TIMEOUT)return 7;
        puts("VULKAN_TRACE_TIMEOUT_OK original_result=2 calls=12");
    }
    vkUnmapMemory(device,memory);OK(vkDeviceWaitIdle(device));vkDestroyFence(device,fence,NULL);vkDestroyCommandPool(device,pool,NULL);vkDestroyBuffer(device,buffer,NULL);vkFreeMemory(device,memory,NULL);vkDestroyImage(device,image,NULL);vkFreeMemory(device,image_memory,NULL);vkDestroyDevice(device,NULL);vkDestroyInstance(instance,NULL);
    puts("VULKAN_TRACE_GPU_OK pixels=1024 submissions=2 image=2048x2048 fence_reused=true");return 0;
}
