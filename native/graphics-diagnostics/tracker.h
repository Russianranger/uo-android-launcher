/* Fixed-capacity correlation only. Never queries Vulkan or owns GPU resources.
 * A missing record means unknown, not an inferred submission or GPU completion. */
#define TRACK_QUEUES 16u
#define TRACK_FENCES 256u
#define TRACK_COMMANDS 512u
#define TRACK_IMAGES 512u
#define TRACK_REFS 8u
#define TRACK_SCAN 64u
struct object_key { uint64_t handle, id; unsigned state; };
struct queue_record { struct object_key key; uint32_t family, index; uint64_t latest_submit; };
struct submit_evidence { uint64_t transfer, draw, dispatch, render_pass, secondary, image_id; uint32_t batches, commands, uncertain, missing, width, height; uint64_t wall_ns; };
struct fence_record { struct object_key key; uint64_t generation, origin_id, queue_id, origin_end; unsigned origin; struct submit_evidence evidence; };
struct command_record {
    struct object_key key; uint64_t pool, generation, transfer, draw, dispatch, render_pass, secondary, first_image;
    uint32_t image_width, image_height; unsigned recording, uncertain;
};
struct image_record { struct object_key key; uint32_t width, height, depth, format, usage, levels, layers; };
struct tracker {
    pthread_mutex_t mutex; uint64_t device_id, next_id, next_submit, next_acquire, overflow, missing, truncated;
    struct queue_record queues[TRACK_QUEUES]; struct fence_record fences[TRACK_FENCES];
    struct command_record commands[TRACK_COMMANDS]; struct image_record images[TRACK_IMAGES];
};
struct fence_reference { uint64_t id, generation, origin_id, queue_id, origin_end; unsigned origin; struct submit_evidence evidence; };
struct correlation {
    uint64_t device_id, queue_id, submit_id, prior_queue_submit_id, acquire_id, object_id;
    uint64_t transfer, draw, dispatch, render_pass, secondary, image_id;
    uint32_t queue_family, queue_index, batch_count, command_count, wait_semaphores, signal_semaphores;
    uint32_t fence_count, fence_refs, refs_omitted, missing, uncertain, width, height, depth, format, usage, levels, layers;
    uint64_t timeout, allocation_bytes; uint32_t memory_type; unsigned wait_all;
    struct fence_reference fences[TRACK_REFS];
};
/* All record types start with object_key. Open addressing has bounded work,
 * tombstones preserve lookup chains, and new IDs distinguish handle reuse. */
static void *track_slot(struct tracker *t,void *base,size_t stride,unsigned capacity,uint64_t handle,int create) {
    if(!handle)return NULL;
    uint64_t mixed=handle; mixed^=mixed>>33; mixed*=0xff51afd7ed558ccdull; mixed^=mixed>>33;
    unsigned first=capacity,slot=(unsigned)mixed&(capacity-1);
    for(unsigned n=0;n<capacity;n++,slot=(slot+1)&(capacity-1)) {
        struct object_key *key=(struct object_key *)((char *)base+slot*stride);
        if(key->state==1&&key->handle==handle)return key;
        if(key->state==2&&first==capacity)first=slot;
        if(key->state==0) { if(first==capacity)first=slot;break; }
    }
    if(!create)return NULL;
    if(first==capacity){t->overflow++;return NULL;}
    struct object_key *key=(struct object_key *)((char *)base+first*stride);
    memset(key,0,stride); key->handle=handle;key->id=++t->next_id;key->state=1;return key;
}
#define SLOT(t,field,capacity,handle,create) track_slot(t,(t)->field,sizeof((t)->field[0]),capacity,(uint64_t)(uintptr_t)(handle),create)
static void forget_slot(struct tracker *t,void *base,size_t stride,unsigned capacity,uint64_t handle) {
    struct object_key *key=track_slot(t,base,stride,capacity,handle,0);if(key)key->state=2;
}
#define FORGET(t,field,capacity,handle) forget_slot(t,(t)->field,sizeof((t)->field[0]),capacity,(uint64_t)(uintptr_t)(handle))
static struct queue_record *queue_lookup(struct tracker *t,VkQueue queue,struct correlation *c) {
    struct queue_record *q=SLOT(t,queues,TRACK_QUEUES,queue,0);
    if(q){c->queue_id=q->key.id;c->queue_family=q->family;c->queue_index=q->index;c->prior_queue_submit_id=q->latest_submit;}
    else{c->missing++;t->missing++;}return q;
}
static void fence_snapshot(struct tracker *t,struct correlation *c,VkFence fence) {
    if(!fence)return;
    if(c->fence_refs>=TRACK_REFS){c->refs_omitted++;return;}
    struct fence_reference *ref=&c->fences[c->fence_refs++];
    struct fence_record *f=SLOT(t,fences,TRACK_FENCES,fence,0);
    if(f){ref->id=f->key.id;ref->generation=f->generation;ref->origin=f->origin;ref->origin_id=f->origin_id;ref->queue_id=f->queue_id;ref->origin_end=f->origin_end;ref->evidence=f->evidence;}
    else{c->missing++;t->missing++;}
}
static void command_evidence(struct tracker *t,struct correlation *c,VkCommandBuffer buffer) {
    struct command_record *b=SLOT(t,commands,TRACK_COMMANDS,buffer,0);
    if(!b){c->missing++;t->missing++;return;}
    c->transfer+=b->transfer;c->draw+=b->draw;c->dispatch+=b->dispatch;c->render_pass+=b->render_pass;c->secondary+=b->secondary;
    c->uncertain+=b->uncertain||b->recording;
    if(!c->image_id&&b->first_image){c->image_id=b->first_image;c->width=b->image_width;c->height=b->image_height;}
}
static void prepare_submit(struct tracker *t,struct correlation *c,VkQueue queue,uint32_t count,const VkSubmitInfo *infos,VkFence fence) {
    pthread_mutex_lock(&t->mutex);queue_lookup(t,queue,c);c->submit_id=++t->next_submit;c->batch_count=count;c->fence_count=fence?1:0;fence_snapshot(t,c,fence);
    uint32_t n=count<TRACK_SCAN?count:TRACK_SCAN;unsigned scanned=0;
    if(count>n){c->uncertain++;t->truncated++;}
    for(uint32_t i=0;i<n;i++) {
        c->command_count+=infos[i].commandBufferCount;c->wait_semaphores+=infos[i].waitSemaphoreCount;c->signal_semaphores+=infos[i].signalSemaphoreCount;
        for(uint32_t j=0;j<infos[i].commandBufferCount;j++) {
            if(scanned++>=TRACK_SCAN){c->uncertain++;t->truncated++;break;}
            command_evidence(t,c,infos[i].pCommandBuffers[j]);
        }
    }
    pthread_mutex_unlock(&t->mutex);
}
static void prepare_submit2(struct tracker *t,struct correlation *c,VkQueue queue,uint32_t count,const VkSubmitInfo2 *infos,VkFence fence) {
    pthread_mutex_lock(&t->mutex);queue_lookup(t,queue,c);c->submit_id=++t->next_submit;c->batch_count=count;c->fence_count=fence?1:0;fence_snapshot(t,c,fence);
    uint32_t n=count<TRACK_SCAN?count:TRACK_SCAN;unsigned scanned=0;
    if(count>n){c->uncertain++;t->truncated++;}
    for(uint32_t i=0;i<n;i++) {
        c->command_count+=infos[i].commandBufferInfoCount;c->wait_semaphores+=infos[i].waitSemaphoreInfoCount;c->signal_semaphores+=infos[i].signalSemaphoreInfoCount;
        for(uint32_t j=0;j<infos[i].commandBufferInfoCount;j++) {
            if(scanned++>=TRACK_SCAN){c->uncertain++;t->truncated++;break;}
            command_evidence(t,c,infos[i].pCommandBufferInfos[j].commandBuffer);
        }
    }
    pthread_mutex_unlock(&t->mutex);
}
static void complete_origin(struct tracker *t,struct correlation *c,VkFence fence,VkResult result,uint64_t start,uint64_t end,unsigned origin) {
    if(result!=VK_SUCCESS&&!(origin==2&&result==VK_SUBOPTIMAL_KHR))return;
    pthread_mutex_lock(&t->mutex);
    if(origin==1){struct queue_record *q=NULL;for(unsigned i=0;i<TRACK_QUEUES;i++)if(t->queues[i].key.state==1&&t->queues[i].key.id==c->queue_id){q=&t->queues[i];break;}if(q)q->latest_submit=c->submit_id;}
    struct fence_record *f=SLOT(t,fences,TRACK_FENCES,fence,0);
    if(f){f->origin=origin;f->origin_id=origin==1?c->submit_id:c->acquire_id;f->queue_id=c->queue_id;f->origin_end=end;
        f->evidence=(struct submit_evidence){.transfer=c->transfer,.draw=c->draw,.dispatch=c->dispatch,.render_pass=c->render_pass,.secondary=c->secondary,.image_id=c->image_id,.batches=c->batch_count,.commands=c->command_count,.uncertain=c->uncertain,.missing=c->missing,.width=c->width,.height=c->height,.wall_ns=end-start};}
    else if(fence){t->missing++;c->missing++;}
    pthread_mutex_unlock(&t->mutex);
}
static void prepare_wait(struct tracker *t,struct correlation *c,uint32_t count,const VkFence *fences,VkBool32 all,uint64_t timeout) {
    c->fence_count=count;c->wait_all=all;c->timeout=timeout;
    pthread_mutex_lock(&t->mutex);for(uint32_t i=0;i<count&&i<TRACK_REFS;i++)fence_snapshot(t,c,fences[i]);
    if(count>TRACK_REFS){c->refs_omitted=count-TRACK_REFS;t->truncated++;}pthread_mutex_unlock(&t->mutex);
}
static void prepare_acquire(struct tracker *t,struct correlation *c,VkFence fence,uint64_t timeout) {
    c->timeout=timeout;c->fence_count=fence?1:0;pthread_mutex_lock(&t->mutex);c->acquire_id=++t->next_acquire;fence_snapshot(t,c,fence);pthread_mutex_unlock(&t->mutex);
}
static void created_fence(struct tracker *t,struct correlation *c,const VkFenceCreateInfo *info,VkFence fence,VkResult result) {
    if(result!=VK_SUCCESS)return;
    pthread_mutex_lock(&t->mutex);struct fence_record *f=SLOT(t,fences,TRACK_FENCES,fence,1);
    if(f){c->object_id=f->key.id;f->generation=1;f->origin=(info->flags&VK_FENCE_CREATE_SIGNALED_BIT)?3:0;}else c->missing++;
    pthread_mutex_unlock(&t->mutex);
}
static void reset_fences(struct tracker *t,uint32_t count,const VkFence *fences,VkResult result) {
    if(result!=VK_SUCCESS)return;
    pthread_mutex_lock(&t->mutex);for(uint32_t i=0;i<count&&i<TRACK_SCAN;i++) {
        struct fence_record *f=SLOT(t,fences,TRACK_FENCES,fences[i],0);
        if(f){if(f->generation)f->generation++;f->origin=4;f->origin_id=f->queue_id=f->origin_end=0;memset(&f->evidence,0,sizeof(f->evidence));}else t->missing++;
    }
    /* Unknown omitted fences must not retain stale origins. */
    if(count>TRACK_SCAN){t->truncated++;for(unsigned i=0;i<TRACK_FENCES;i++)if(t->fences[i].key.state==1){t->fences[i].generation=0;t->fences[i].origin=5;t->fences[i].origin_id=t->fences[i].queue_id=t->fences[i].origin_end=0;memset(&t->fences[i].evidence,0,sizeof(t->fences[i].evidence));}}
    pthread_mutex_unlock(&t->mutex);
}
static void created_image(struct tracker *t,struct correlation *c,const VkImageCreateInfo *info,VkImage image,VkResult result) {
    c->width=info->extent.width;c->height=info->extent.height;c->depth=info->extent.depth;c->format=info->format;c->usage=info->usage;c->levels=info->mipLevels;c->layers=info->arrayLayers;
    if(result!=VK_SUCCESS)return;
    pthread_mutex_lock(&t->mutex);struct image_record *im=SLOT(t,images,TRACK_IMAGES,image,1);
    if(im){c->object_id=im->key.id;im->width=c->width;im->height=c->height;im->depth=c->depth;im->format=c->format;im->usage=c->usage;im->levels=c->levels;im->layers=c->layers;}else c->missing++;
    pthread_mutex_unlock(&t->mutex);
}
static void allocate_commands(struct tracker *t,const VkCommandBufferAllocateInfo *info,VkCommandBuffer *buffers,VkResult result) {
    if(result!=VK_SUCCESS)return;
    pthread_mutex_lock(&t->mutex);uint32_t n=info->commandBufferCount<TRACK_SCAN?info->commandBufferCount:TRACK_SCAN;
    if(n<info->commandBufferCount)t->truncated++;
    for(uint32_t i=0;i<n;i++){struct command_record *b=SLOT(t,commands,TRACK_COMMANDS,buffers[i],1);if(b){b->pool=(uint64_t)(uintptr_t)info->commandPool;b->generation=1;b->uncertain=1;}}
    pthread_mutex_unlock(&t->mutex);
}
static void change_command(struct tracker *t,VkCommandBuffer buffer,VkResult result,unsigned action) {
    if(result!=VK_SUCCESS)return;
    pthread_mutex_lock(&t->mutex);struct command_record *b=SLOT(t,commands,TRACK_COMMANDS,buffer,0);
    if(b){if(action==0||action==1){b->generation++;b->transfer=b->draw=b->dispatch=b->render_pass=b->secondary=b->first_image=0;b->image_width=b->image_height=0;b->uncertain=0;b->recording=action==1;}else b->recording=0;}else t->missing++;
    pthread_mutex_unlock(&t->mutex);
}
static void record_command(struct tracker *t,VkCommandBuffer buffer,unsigned type,VkImage image) {
    pthread_mutex_lock(&t->mutex);struct command_record *b=SLOT(t,commands,TRACK_COMMANDS,buffer,0);
    if(b){if(!b->recording)b->uncertain=1;
        if(type==1)b->transfer++;
        if(type==2)b->draw++;
        if(type==3)b->dispatch++;
        if(type==4)b->render_pass++;
        if(type==5){b->secondary++;b->uncertain=1;}
        if(image&&!b->first_image){struct image_record *im=SLOT(t,images,TRACK_IMAGES,image,0);if(im){b->first_image=im->key.id;b->image_width=im->width;b->image_height=im->height;}else{b->uncertain=1;t->missing++;}}
    }else t->missing++;
    pthread_mutex_unlock(&t->mutex);
}
static void got_queue(struct tracker *t,VkQueue queue,uint32_t family,uint32_t index) {
    pthread_mutex_lock(&t->mutex);struct queue_record *q=SLOT(t,queues,TRACK_QUEUES,queue,1);if(q){q->family=family;q->index=index;}pthread_mutex_unlock(&t->mutex);
}
static void forget_object(struct tracker *t,unsigned type,uint64_t handle) {
    pthread_mutex_lock(&t->mutex);if(type==1)FORGET(t,fences,TRACK_FENCES,handle);if(type==2)FORGET(t,images,TRACK_IMAGES,handle);
    if(type==3)for(unsigned i=0;i<TRACK_COMMANDS;i++)if(t->commands[i].key.state==1&&t->commands[i].pool==handle)t->commands[i].key.state=2;
    pthread_mutex_unlock(&t->mutex);
}
static void free_commands(struct tracker *t,uint32_t count,const VkCommandBuffer *buffers) {
    pthread_mutex_lock(&t->mutex);for(uint32_t i=0;i<count&&i<TRACK_SCAN;i++)FORGET(t,commands,TRACK_COMMANDS,buffers[i]);
    if(count>TRACK_SCAN){t->truncated++;for(unsigned i=0;i<TRACK_COMMANDS;i++)t->commands[i].key.state=2;}pthread_mutex_unlock(&t->mutex);
}
static void reset_pool(struct tracker *t,VkCommandPool pool,VkResult result) {
    if(result!=VK_SUCCESS)return;
    pthread_mutex_lock(&t->mutex);for(unsigned i=0;i<TRACK_COMMANDS;i++)if(t->commands[i].key.state==1&&t->commands[i].pool==(uint64_t)(uintptr_t)pool){struct command_record *b=&t->commands[i];b->generation++;b->transfer=b->draw=b->dispatch=b->render_pass=b->secondary=b->first_image=0;b->uncertain=1;b->recording=0;}
    pthread_mutex_unlock(&t->mutex);
}

static void prepare_queue(struct tracker *t,struct correlation *c,VkQueue queue){pthread_mutex_lock(&t->mutex);queue_lookup(t,queue,c);pthread_mutex_unlock(&t->mutex);}
