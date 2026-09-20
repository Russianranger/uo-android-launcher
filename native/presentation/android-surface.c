#define _POSIX_C_SOURCE 200809L
#include "frame.h"
#include <jni.h>
#include <android/native_window_jni.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <errno.h>
#include <time.h>
static uint64_t now_ns(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
static int receive(int fd,void *data,size_t size){char *p=data;while(size){ssize_t n=recv(fd,p,size,0);if(n<0&&errno==EINTR)continue;if(n<=0)return -1;p+=n;size-=(size_t)n;}return 0;}
JNIEXPORT jint JNICALL Java_io_github_russianranger_trasc_NativePresentation_frame(JNIEnv *env,jclass cls,jobject surface,jint fd,jobject storage,jlongArray measures){
    (void)cls;uint32_t header[8];unsigned char request=1;uint64_t start=now_ns();
    if(send(fd,&request,1,MSG_NOSIGNAL)!=1||receive(fd,header,sizeof(header)))return -1;
    for(int i=0;i<8;i++)header[i]=ntohl(header[i]);
    if(!trasc_frame_valid(header)||(*env)->GetArrayLength(env,measures)<9)return -2;
    if(header[7]&2)return 1; /* Retain the last Surface buffer; no pixel read/copy/post. */
    void *pixels=(*env)->GetDirectBufferAddress(env,storage);jlong capacity=(*env)->GetDirectBufferCapacity(env,storage);
    if(!pixels||capacity<header[6]||receive(fd,pixels,header[6]))return -3;
    uint64_t received=now_ns();ANativeWindow *window=ANativeWindow_fromSurface(env,surface);if(!window)return -4;
    int error=0;
    if(ANativeWindow_getWidth(window)!=(int32_t)header[1]||ANativeWindow_getHeight(window)!=(int32_t)header[2]||ANativeWindow_getFormat(window)!=WINDOW_FORMAT_RGBA_8888)error=ANativeWindow_setBuffersGeometry(window,(int32_t)header[1],(int32_t)header[2],WINDOW_FORMAT_RGBA_8888);
    ANativeWindow_Buffer buffer;uint64_t locking=now_ns();
    if(!error)error=ANativeWindow_lock(window,&buffer,NULL);
    uint64_t locked=now_ns(),copied=locked,posted=locked;
    if(!error){
        if(buffer.width!=(int32_t)header[1]||buffer.height!=(int32_t)header[2]||buffer.stride<buffer.width||buffer.format!=WINDOW_FORMAT_RGBA_8888)error=-5;
        else for(uint32_t y=0;y<header[2];y++)trasc_bgra_rgba((uint32_t *)buffer.bits+(size_t)y*buffer.stride,(const uint32_t *)pixels+(size_t)y*header[1],header[1]);
        copied=now_ns();int post_error=ANativeWindow_unlockAndPost(window);posted=now_ns();if(!error)error=post_error;
    }
    ANativeWindow_release(window);if(error)return -6;
    jlong out[9]={(jlong)header[1],(jlong)header[2],(jlong)header[4]*1000,(jlong)(received-start),(jlong)(locked-locking),(jlong)(copied-locked),(jlong)(posted-copied),(jlong)header[6],(jlong)header[7]};
    (*env)->SetLongArrayRegion(env,measures,0,9,out);return 0;
}
