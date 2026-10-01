#define _POSIX_C_SOURCE 200809L
#include "frame.h"
#include "transfer.h"
#include <jni.h>
#include <android/native_window_jni.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <errno.h>
#include <time.h>
static uint64_t now_ns(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
#define CACHE_BYTES (TRASC_MAX_PIXELS*4u)
struct frame_cache {uint32_t magic,width,height,sequence;};
JNIEXPORT jint JNICALL Java_io_github_russianranger_trasc_NativePresentation_capabilities(JNIEnv *env,jclass cls,jint fd){
    (void)env;(void)cls;unsigned char request=TRASC_REQUEST_CAPABILITIES;uint32_t capability=0;uint64_t calls=0;
    if(trasc_send_all(fd,&request,1,&calls)||trasc_receive_all(fd,&capability,sizeof(capability),&calls))return 0;
    return ntohl(capability)==TRASC_REGIONS_MAGIC;
}
JNIEXPORT jint JNICALL Java_io_github_russianranger_trasc_NativePresentation_frame(JNIEnv *env,jclass cls,jobject surface,jint fd,jobject storage,jlongArray measures,jboolean regions){
    (void)cls;uint32_t header[8];unsigned char request=regions?TRASC_REQUEST_REGIONS:TRASC_REQUEST_FULL;uint64_t start=now_ns(),calls=0,sent_calls=0;
    if(trasc_send_all(fd,&request,1,&sent_calls)||trasc_receive_all(fd,header,sizeof(header),&calls))return -1;
    for(int i=0;i<8;i++)header[i]=ntohl(header[i]);
    if(!trasc_frame_valid(header)||(*env)->GetArrayLength(env,measures)<15||(!regions&&(header[7]&TRASC_REGION)))return -2;
    unsigned char *pixels=(*env)->GetDirectBufferAddress(env,storage);jlong capacity=(*env)->GetDirectBufferCapacity(env,storage);
    if(!pixels||capacity<(jlong)(CACHE_BYTES+sizeof(struct frame_cache)))return -3;
    struct frame_cache *cache=(struct frame_cache *)(pixels+CACHE_BYTES);
    int baseline=cache->magic==TRASC_REGIONS_MAGIC;
    if(baseline&&header[5]!=(uint32_t)(cache->sequence+1u))return -2;
    if(header[7]&(TRASC_REGION|TRASC_UNCHANGED)){
        if(!baseline||cache->width!=header[1]||cache->height!=header[2])return -2;
    }
    if(header[7]&TRASC_UNCHANGED){cache->sequence=header[5];return 1;}
    uint32_t region[4]={0,0,header[1],header[2]};
    if(header[7]&TRASC_REGION){
        if(trasc_receive_all(fd,region,sizeof(region),&calls))return -3;
        for(int i=0;i<4;i++)region[i]=ntohl(region[i]);
        if(!trasc_region_valid(header,region))return -2;
    }
    if(trasc_receive_pixels(fd,pixels+(size_t)region[1]*header[3]+region[0]*4,
            region[2]*4,header[3],region[3],&calls))return -3;
    uint64_t received=now_ns();ANativeWindow *window=ANativeWindow_fromSurface(env,surface);if(!window)return -4;
    /* This cache belongs to one Java Surface reader and is fresh on Surface
     * recreation. Its dimensions are committed only after a successful post.
     * Window queries may report the onscreen view size, not our buffer size;
     * comparing them would repeat setup and force a full redraw every frame. */
    int error=0,geometry=!baseline||cache->width!=header[1]||cache->height!=header[2];
    if(geometry)error=ANativeWindow_setBuffersGeometry(window,(int32_t)header[1],(int32_t)header[2],WINDOW_FORMAT_RGBA_8888);
    ARect requested={(int32_t)region[0],(int32_t)region[1],(int32_t)(region[0]+region[2]),(int32_t)(region[1]+region[3])},dirty=requested;
    if(geometry)dirty=(ARect){0,0,(int32_t)header[1],(int32_t)header[2]};
    ANativeWindow_Buffer buffer;uint64_t locking=now_ns();
    if(!error)error=ANativeWindow_lock(window,&buffer,&dirty);
    uint64_t locked=now_ns(),copied=locked,posted=locked;
    if(!error){
        if(!buffer.bits||buffer.width!=(int32_t)header[1]||buffer.height!=(int32_t)header[2]||buffer.stride<buffer.width||buffer.format!=WINDOW_FORMAT_RGBA_8888||
            dirty.left<0||dirty.top<0||dirty.right>(int32_t)header[1]||dirty.bottom>(int32_t)header[2]||
            dirty.left>requested.left||dirty.top>requested.top||dirty.right<requested.right||dirty.bottom<requested.bottom)error=-5;
        else for(int32_t y=dirty.top;y<dirty.bottom;y++)trasc_bgra_rgba((uint32_t *)buffer.bits+(size_t)y*buffer.stride+dirty.left,
            (const uint32_t *)pixels+(size_t)y*header[1]+dirty.left,(size_t)(dirty.right-dirty.left));
        copied=now_ns();int post_error=ANativeWindow_unlockAndPost(window);posted=now_ns();if(!error)error=post_error;
    }
    ANativeWindow_release(window);if(error)return -6;
    cache->magic=TRASC_REGIONS_MAGIC;cache->width=header[1];cache->height=header[2];cache->sequence=header[5];
    jlong redrawn=(jlong)(dirty.right-dirty.left)*(dirty.bottom-dirty.top);
    jlong out[15]={(jlong)header[1],(jlong)header[2],(jlong)header[4]*1000,(jlong)(received-start),(jlong)(locked-locking),(jlong)(copied-locked),(jlong)(posted-copied),
        (jlong)header[6],(jlong)header[7],redrawn,(jlong)header[1]*header[2],(jlong)calls,
        redrawn>(jlong)region[2]*region[3],geometry,(jlong)header[6]+sizeof(header)+((header[7]&TRASC_REGION)?sizeof(region):0)};
    (*env)->SetLongArrayRegion(env,measures,0,15,out);return 0;
}
