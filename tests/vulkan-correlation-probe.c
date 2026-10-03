/* Actual wrapper forwarding + deterministic bounded correlation without a GPU.
 * The live driver probe separately verifies pixels/results with the layer. */
#include "../native/graphics-diagnostics/layer.c"
#include <assert.h>
struct fake_handle { void *dispatch; };
static int table;
static struct fake_handle dev_handle={&table},queue_handle={&table},command_handle={&table};
static struct device fixture;
static VkResult next_result=VK_SUCCESS;
static unsigned waits,submit2_calls,acquire2_calls,queue2_calls,allocate_calls,begin_calls,end_calls,reset_command_calls,reset_pool_calls,free_calls,pool_destroy_calls;
static int recycle_command;
static int recycle_fence,recycle_image;
static unsigned fence_creates,fence_resets,fence_destroys,submits,acquires,image_creates,image_destroys,copies,queue_gets;
static VkFence output_fence=(VkFence)(uintptr_t)101;
static VkImage output_image=(VkImage)(uintptr_t)201;
static const VkSubmitInfo *expected_submit;
static const VkSubmitInfo2 *expected_submit2;
static const VkBufferImageCopy *expected_regions;
static VKAPI_ATTR void VKAPI_CALL fake_queue(VkDevice device,uint32_t family,uint32_t index,VkQueue *out){assert(device==fixture.handle&&family==7&&index==3);*out=(VkQueue)&queue_handle;queue_gets++;}
static VKAPI_ATTR VkResult VKAPI_CALL fake_create_fence(VkDevice device,const VkFenceCreateInfo *info,const VkAllocationCallbacks *allocator,VkFence *out){assert(device==fixture.handle&&info->sType==VK_STRUCTURE_TYPE_FENCE_CREATE_INFO&&!allocator);if(next_result==VK_SUCCESS)*out=output_fence;fence_creates++;return next_result;}
static VKAPI_ATTR VkResult VKAPI_CALL fake_wait(VkDevice device,uint32_t count,const VkFence *fences,VkBool32 all,uint64_t timeout){assert(device==fixture.handle&&count==1&&fences[0]==output_fence&&all==VK_TRUE&&timeout==60000000ull);struct timespec delay={.tv_nsec=60000000};nanosleep(&delay,NULL);waits++;return VK_TIMEOUT;}
static VKAPI_ATTR VkResult VKAPI_CALL fake_reset(VkDevice device,uint32_t count,const VkFence *fences){assert(device==fixture.handle&&count&&fences);fence_resets++;return next_result;}
static VKAPI_ATTR void VKAPI_CALL fake_destroy_fence(VkDevice device,VkFence fence,const VkAllocationCallbacks *allocator){assert(device==fixture.handle&&fence&&!allocator);fence_destroys++;if(recycle_fence){VkFenceCreateInfo info={.sType=VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};VkFence out;assert(trace_CreateFence(device,&info,allocator,&out)==VK_SUCCESS&&out==fence);}}
static VKAPI_ATTR VkResult VKAPI_CALL fake_submit(VkQueue queue,uint32_t count,const VkSubmitInfo *info,VkFence fence){assert(queue==(VkQueue)&queue_handle&&count==1&&info==expected_submit&&fence==output_fence);submits++;return next_result;}
static VKAPI_ATTR VkResult VKAPI_CALL fake_acquire(VkDevice device,VkSwapchainKHR swapchain,uint64_t timeout,VkSemaphore semaphore,VkFence fence,uint32_t *index){assert(device==fixture.handle&&swapchain==(VkSwapchainKHR)(uintptr_t)301&&timeout==123&&semaphore==(VkSemaphore)(uintptr_t)401&&fence==output_fence);if(next_result==VK_SUCCESS||next_result==VK_SUBOPTIMAL_KHR)*index=2;acquires++;return next_result;}
static VKAPI_ATTR VkResult VKAPI_CALL fake_image(VkDevice device,const VkImageCreateInfo *info,const VkAllocationCallbacks *allocator,VkImage *out){assert(device==fixture.handle&&info->extent.width==2048&&!allocator);if(next_result==VK_SUCCESS)*out=output_image;image_creates++;return next_result;}
static VKAPI_ATTR void VKAPI_CALL fake_destroy_image(VkDevice device,VkImage image,const VkAllocationCallbacks *allocator){assert(device==fixture.handle&&image==output_image&&!allocator);image_destroys++;if(recycle_image){VkImageCreateInfo info={.sType=VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,.extent={2048,2048,1},.format=VK_FORMAT_R8G8B8A8_UNORM,.usage=VK_IMAGE_USAGE_SAMPLED_BIT,.mipLevels=1,.arrayLayers=1};VkImage out;assert(trace_CreateImage(device,&info,allocator,&out)==VK_SUCCESS&&out==image);}}
static VKAPI_ATTR void VKAPI_CALL fake_copy(VkCommandBuffer buffer,VkBuffer source,VkImage target,VkImageLayout layout,uint32_t count,const VkBufferImageCopy *regions){assert(buffer==(VkCommandBuffer)&command_handle&&source==(VkBuffer)(uintptr_t)501&&target==output_image&&layout==VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL&&count==2&&regions==expected_regions);copies++;}
static VKAPI_ATTR VkResult VKAPI_CALL fake_submit2(VkQueue queue,uint32_t count,const VkSubmitInfo2 *infos,VkFence fence){assert(queue==(VkQueue)&queue_handle&&count==1&&infos==expected_submit2&&fence==output_fence);submit2_calls++;return next_result;}
static VKAPI_ATTR void VKAPI_CALL fake_queue2(VkDevice device,const VkDeviceQueueInfo2 *info,VkQueue *out){assert(device==fixture.handle&&info->queueFamilyIndex==7&&info->queueIndex==3&&info->flags==0);queue2_calls++;*out=(VkQueue)&queue_handle;}
static VKAPI_ATTR VkResult VKAPI_CALL fake_acquire2(VkDevice device,const VkAcquireNextImageInfoKHR *info,uint32_t *out){assert(device==fixture.handle&&info->swapchain==(VkSwapchainKHR)(uintptr_t)301&&info->timeout==123&&info->fence==output_fence&&info->deviceMask==1);acquire2_calls++;if(next_result==VK_SUCCESS)*out=3;return next_result;}
static VKAPI_ATTR VkResult VKAPI_CALL fake_allocate(VkDevice device,const VkCommandBufferAllocateInfo *info,VkCommandBuffer *out){assert(device==fixture.handle&&info->commandPool==(VkCommandPool)(uintptr_t)601&&info->commandBufferCount==1);allocate_calls++;if(next_result==VK_SUCCESS)*out=(VkCommandBuffer)&command_handle;return next_result;}
static VKAPI_ATTR VkResult VKAPI_CALL fake_begin(VkCommandBuffer buffer,const VkCommandBufferBeginInfo *info){assert(buffer==(VkCommandBuffer)&command_handle&&info->sType==VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO);begin_calls++;return next_result;}
static VKAPI_ATTR VkResult VKAPI_CALL fake_end(VkCommandBuffer buffer){assert(buffer==(VkCommandBuffer)&command_handle);end_calls++;return next_result;}
static VKAPI_ATTR VkResult VKAPI_CALL fake_reset_command(VkCommandBuffer buffer,VkCommandBufferResetFlags flags){assert(buffer==(VkCommandBuffer)&command_handle&&flags==VK_COMMAND_BUFFER_RESET_RELEASE_RESOURCES_BIT);reset_command_calls++;return next_result;}
static VKAPI_ATTR VkResult VKAPI_CALL fake_reset_pool(VkDevice device,VkCommandPool pool,VkCommandPoolResetFlags flags){assert(device==fixture.handle&&pool==(VkCommandPool)(uintptr_t)601&&flags==0);reset_pool_calls++;return next_result;}
static void reallocate_command(VkDevice device,VkCommandPool pool){VkCommandBufferAllocateInfo info={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,.commandPool=pool,.commandBufferCount=1};VkCommandBuffer out;assert(trace_AllocateCommandBuffers(device,&info,&out)==VK_SUCCESS&&out==(VkCommandBuffer)&command_handle);}
static VKAPI_ATTR void VKAPI_CALL fake_free(VkDevice device,VkCommandPool pool,uint32_t count,const VkCommandBuffer *buffers){assert(device==fixture.handle&&pool==(VkCommandPool)(uintptr_t)601&&count==1&&buffers[0]==(VkCommandBuffer)&command_handle);free_calls++;if(recycle_command)reallocate_command(device,pool);}
static VKAPI_ATTR void VKAPI_CALL fake_destroy_pool(VkDevice device,VkCommandPool pool,const VkAllocationCallbacks *allocator){assert(device==fixture.handle&&pool==(VkCommandPool)(uintptr_t)601&&!allocator);pool_destroy_calls++;if(recycle_command)reallocate_command(device,pool);}
static struct fence_record *fence_record(void){return SLOT(&fixture.track,fences,TRACK_FENCES,output_fence,0);}
struct worker {struct fake_handle queue;VkFence fence;};
static VKAPI_ATTR VkResult VKAPI_CALL thread_submit(VkQueue queue,uint32_t count,const VkSubmitInfo *infos,VkFence fence){assert(queue&&count==0&&!infos&&fence);return VK_SUCCESS;}
static void *worker_main(void *ptr){
    struct worker *w=ptr;struct tracker *t=&fixture.track;struct correlation created={0};VkFenceCreateInfo info={.sType=VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    got_queue(t,(VkQueue)&w->queue,2,0);created_fence(t,&created,&info,w->fence,VK_SUCCESS);
    for(int i=0;i<1000;i++){
        assert(trace_QueueSubmit((VkQueue)&w->queue,0,NULL,w->fence)==VK_SUCCESS);
        struct correlation wait={0};prepare_wait(t,&wait,1,&w->fence,VK_TRUE,100);
        assert(wait.fence_refs==1&&wait.fences[0].origin==1&&wait.fences[0].origin_id&&wait.fences[0].queue_id);
        reset_fences(t,1,&w->fence,VK_SUCCESS);
        prepare_wait(t,&wait,1,&w->fence,VK_TRUE,100);
    }
    return NULL;
}
int main(void){
    memset(&fixture,0,sizeof(fixture));fixture.handle=(VkDevice)&dev_handle;fixture.track.device_id=9;pthread_mutex_init(&fixture.track.mutex,NULL);devices=&fixture;
    fixture.QueueSubmit2=fixture.QueueSubmit2KHR=fake_submit2;fixture.AcquireNextImage2KHR=fake_acquire2;fixture.GetDeviceQueue2=fake_queue2;
    fixture.AllocateCommandBuffers=fake_allocate;fixture.BeginCommandBuffer=fake_begin;fixture.EndCommandBuffer=fake_end;fixture.ResetCommandBuffer=fake_reset_command;fixture.ResetCommandPool=fake_reset_pool;fixture.FreeCommandBuffers=fake_free;fixture.DestroyCommandPool=fake_destroy_pool;
    fixture.WaitForFences=fake_wait;fixture.GetDeviceQueue=fake_queue;fixture.CreateFence=fake_create_fence;fixture.ResetFences=fake_reset;fixture.DestroyFence=fake_destroy_fence;fixture.QueueSubmit=fake_submit;fixture.AcquireNextImageKHR=fake_acquire;fixture.CreateImage=fake_image;fixture.DestroyImage=fake_destroy_image;fixture.CmdCopyBufferToImage=fake_copy;
    VkQueue queue;trace_GetDeviceQueue(fixture.handle,7,3,&queue);assert(queue==(VkQueue)&queue_handle);
    VkDeviceQueueInfo2 queue_info={.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_INFO_2,.queueFamilyIndex=7,.queueIndex=3};VkQueue queue2;trace_GetDeviceQueue2(fixture.handle,&queue_info,&queue2);assert(queue2==queue);
    VkFenceCreateInfo info={.sType=VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};VkFence fence;
    assert(trace_CreateFence(fixture.handle,&info,NULL,&fence)==VK_SUCCESS&&fence==output_fence);
    uint64_t original_id=fence_record()->key.id;assert(fence_record()->generation==1&&fence_record()->origin==0);
    VkImageCreateInfo image_info={.sType=VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,.extent={2048,2048,1},.format=VK_FORMAT_R8G8B8A8_UNORM,.usage=VK_IMAGE_USAGE_TRANSFER_DST_BIT|VK_IMAGE_USAGE_SAMPLED_BIT,.mipLevels=1,.arrayLayers=1};VkImage image;
    assert(trace_CreateImage(fixture.handle,&image_info,NULL,&image)==VK_SUCCESS&&image==output_image);
    VkCommandBuffer buffer=(VkCommandBuffer)&command_handle;VkCommandBufferAllocateInfo allocation={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,.commandPool=(VkCommandPool)(uintptr_t)601,.commandBufferCount=1};assert(trace_AllocateCommandBuffers(fixture.handle,&allocation,&buffer)==VK_SUCCESS);
    VkCommandBufferBeginInfo begin_info={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};assert(trace_BeginCommandBuffer(buffer,&begin_info)==VK_SUCCESS);
    VkBufferImageCopy regions[2]={{0}};expected_regions=regions;trace_CmdCopyBufferToImage(buffer,(VkBuffer)(uintptr_t)501,image,VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,2,regions);assert(trace_EndCommandBuffer(buffer)==VK_SUCCESS);
    VkSubmitInfo submit={.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO,.commandBufferCount=1,.pCommandBuffers=&buffer,.waitSemaphoreCount=2,.signalSemaphoreCount=1};expected_submit=&submit;
    assert(trace_QueueSubmit(queue,1,&submit,fence)==VK_SUCCESS);
    assert(fence_record()->origin==1&&fence_record()->origin_id==1&&fence_record()->evidence.transfer==1&&fence_record()->evidence.width==2048&&fence_record()->evidence.height==2048);
    struct correlation queue_snapshot={0};prepare_queue(&fixture.track,&queue_snapshot,queue);assert(queue_snapshot.prior_queue_submit_id==1);
    struct correlation wait={0};prepare_wait(&fixture.track,&wait,1,&fence,VK_TRUE,321);
    assert(wait.fences[0].origin_id==1&&wait.fences[0].evidence.commands==1&&wait.timeout==321&&wait.wait_all);
    assert(trace_WaitForFences(fixture.handle,1,&fence,VK_TRUE,60000000ull)==VK_TIMEOUT);
    VkCommandBufferSubmitInfo command_submit={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_SUBMIT_INFO,.commandBuffer=buffer};VkSubmitInfo2 submit2={.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO_2,.commandBufferInfoCount=1,.pCommandBufferInfos=&command_submit};expected_submit2=&submit2;
    assert(trace_QueueSubmit2(queue,1,&submit2,fence)==VK_SUCCESS&&fence_record()->origin_id==2&&fence_record()->evidence.transfer==1);
    assert(trace_QueueSubmit2KHR(queue,1,&submit2,fence)==VK_SUCCESS&&fence_record()->origin_id==3);
    next_result=VK_ERROR_DEVICE_LOST;assert(trace_QueueSubmit(queue,1,&submit,fence)==next_result&&fence_record()->origin_id==3);
    assert(trace_ResetFences(fixture.handle,1,&fence)==next_result&&fence_record()->generation==1);
    assert(trace_AllocateCommandBuffers(fixture.handle,&allocation,(VkCommandBuffer *)(uintptr_t)1)==next_result);
    assert(trace_BeginCommandBuffer(buffer,&begin_info)==next_result);
    assert(trace_ResetCommandBuffer(buffer,VK_COMMAND_BUFFER_RESET_RELEASE_RESOURCES_BIT)==next_result);
    assert(trace_ResetCommandPool(fixture.handle,allocation.commandPool,0)==next_result);
    struct correlation failed_command={0};command_evidence(&fixture.track,&failed_command,buffer);assert(failed_command.transfer==1);
    /* Failed creates leave the caller's unreadable output pointer untouched. */
    assert(trace_CreateImage(fixture.handle,&image_info,NULL,(VkImage *)(uintptr_t)1)==next_result);
    assert(trace_CreateFence(fixture.handle,&info,NULL,(VkFence *)(uintptr_t)1)==next_result);
    next_result=VK_SUCCESS;assert(trace_ResetFences(fixture.handle,1,&fence)==VK_SUCCESS&&fence_record()->generation==2&&fence_record()->origin==4&&fence_record()->origin_id==0&&!fence_record()->evidence.transfer);
    uint32_t index=55;next_result=VK_TIMEOUT;assert(trace_AcquireNextImageKHR(fixture.handle,(VkSwapchainKHR)(uintptr_t)301,123,(VkSemaphore)(uintptr_t)401,fence,&index)==VK_TIMEOUT&&index==55&&fence_record()->origin==4);
    next_result=VK_SUBOPTIMAL_KHR;assert(trace_AcquireNextImageKHR(fixture.handle,(VkSwapchainKHR)(uintptr_t)301,123,(VkSemaphore)(uintptr_t)401,fence,&index)==VK_SUBOPTIMAL_KHR&&index==2&&fence_record()->origin==2&&fence_record()->origin_id==2);
    next_result=VK_SUCCESS;VkAcquireNextImageInfoKHR acquire_info={.sType=VK_STRUCTURE_TYPE_ACQUIRE_NEXT_IMAGE_INFO_KHR,.swapchain=(VkSwapchainKHR)(uintptr_t)301,.timeout=123,.fence=fence,.deviceMask=1};
    assert(trace_AcquireNextImage2KHR(fixture.handle,&acquire_info,&index)==VK_SUCCESS&&index==3&&fence_record()->origin_id==3);
    next_result=VK_SUCCESS;recycle_fence=1;trace_DestroyFence(fixture.handle,fence,NULL);recycle_fence=0;
    assert(fence_record()&&fence_record()->key.id!=original_id&&fence_record()->generation==1&&fence_record()->origin==0&&!fence_record()->origin_id&&!fence_record()->evidence.transfer);
    uint64_t image_id=((struct image_record *)SLOT(&fixture.track,images,TRACK_IMAGES,image,0))->key.id;
    recycle_image=1;trace_DestroyImage(fixture.handle,image,NULL);recycle_image=0;
    assert(SLOT(&fixture.track,images,TRACK_IMAGES,image,0)&&((struct image_record *)SLOT(&fixture.track,images,TRACK_IMAGES,image,0))->key.id!=image_id);
    trace_DestroyImage(fixture.handle,image,NULL);assert(!SLOT(&fixture.track,images,TRACK_IMAGES,image,0));assert(trace_ResetCommandBuffer(buffer,VK_COMMAND_BUFFER_RESET_RELEASE_RESOURCES_BIT)==VK_SUCCESS);struct correlation after_reset={0};command_evidence(&fixture.track,&after_reset,buffer);assert(!after_reset.transfer&&!after_reset.image_id);
    assert(trace_ResetCommandPool(fixture.handle,allocation.commandPool,0)==VK_SUCCESS);
    uint64_t command_id=((struct command_record *)SLOT(&fixture.track,commands,TRACK_COMMANDS,buffer,0))->key.id;
    recycle_command=1;trace_FreeCommandBuffers(fixture.handle,allocation.commandPool,1,&buffer);
    assert(SLOT(&fixture.track,commands,TRACK_COMMANDS,buffer,0)&&((struct command_record *)SLOT(&fixture.track,commands,TRACK_COMMANDS,buffer,0))->key.id!=command_id);
    command_id=((struct command_record *)SLOT(&fixture.track,commands,TRACK_COMMANDS,buffer,0))->key.id;
    trace_DestroyCommandPool(fixture.handle,allocation.commandPool,NULL);recycle_command=0;
    assert(SLOT(&fixture.track,commands,TRACK_COMMANDS,buffer,0)&&((struct command_record *)SLOT(&fixture.track,commands,TRACK_COMMANDS,buffer,0))->key.id!=command_id);
    trace_FreeCommandBuffers(fixture.handle,allocation.commandPool,1,&buffer);assert(!SLOT(&fixture.track,commands,TRACK_COMMANDS,buffer,0));
    VkFence many[TRACK_FENCES+1];for(unsigned i=0;i<TRACK_FENCES+1;i++){many[i]=(VkFence)(uintptr_t)(1000+i);struct correlation c={0};created_fence(&fixture.track,&c,&info,many[i],VK_SUCCESS);}
    assert(fixture.track.overflow>=2);struct correlation missing={0};prepare_wait(&fixture.track,&missing,1,&many[TRACK_FENCES],VK_FALSE,4);assert(missing.missing==1&&!missing.fences[0].id);
    struct correlation clipped={0};prepare_wait(&fixture.track,&clipped,20,many,VK_FALSE,4);assert(clipped.fence_refs==TRACK_REFS&&clipped.refs_omitted==12&&!clipped.wait_all);
    reset_fences(&fixture.track,65,many,VK_SUCCESS);assert(fence_record()->origin==5&&!fence_record()->origin_id&&!fence_record()->generation);
    reset_fences(&fixture.track,1,&fence,VK_SUCCESS);assert(!fence_record()->generation);
    VkSubmitInfo clipped_submits[TRACK_SCAN+1];for(unsigned i=0;i<TRACK_SCAN+1;i++)clipped_submits[i]=(VkSubmitInfo){.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO,.commandBufferCount=1,.pCommandBuffers=&buffer};
    struct correlation clipped_submission={0};prepare_submit(&fixture.track,&clipped_submission,queue,TRACK_SCAN+1,clipped_submits,fence);
    assert(clipped_submission.batch_count==TRACK_SCAN+1&&clipped_submission.command_count==TRACK_SCAN&&clipped_submission.uncertain&&clipped_submission.missing==TRACK_SCAN);
    uint64_t origin_start=clock_ns(CLOCK_MONOTONIC);complete_origin(&fixture.track,&clipped_submission,fence,VK_SUCCESS,origin_start,clock_ns(CLOCK_MONOTONIC),1);
    assert(fence_record()->origin==1&&!fence_record()->generation&&fence_record()->evidence.uncertain);
    for(unsigned i=0;i<TRACK_FENCES+1;i++)forget_object(&fixture.track,1,(uint64_t)(uintptr_t)many[i]);
    fixture.QueueSubmit=thread_submit;struct worker workers[4];pthread_t threads[4];
    for(int i=0;i<4;i++){workers[i]=(struct worker){.queue={&table},.fence=(VkFence)(uintptr_t)(2000+i)};assert(!pthread_create(&threads[i],NULL,worker_main,&workers[i]));}
    for(int i=0;i<4;i++)assert(!pthread_join(threads[i],NULL));
    assert(submit2_calls==2&&queue2_calls==1&&acquire2_calls==1&&allocate_calls==4&&begin_calls==2&&end_calls==1&&reset_command_calls==2&&reset_pool_calls==2&&free_calls==2&&pool_destroy_calls==1);
    assert(waits==1&&fence_creates==3&&fence_resets==2&&fence_destroys==1&&submits==2&&acquires==2&&image_creates==3&&image_destroys==2&&copies==1&&queue_gets==1);
    pthread_mutex_destroy(&fixture.track.mutex);devices=NULL;
    puts("VULKAN_CORRELATION_OK calls_once=true exact_args=true failures_preserved=true fence_reuse_reset_acquire=true concurrent_reuse=true aliases=true command_failures=true image_extent=true bounded_missing=true multithread=true");return 0;
}
