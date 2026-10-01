#ifndef TRASC_FRAME_H
#define TRASC_FRAME_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define TRASC_MAGIC 0x54524631u
#define TRASC_MAX_PIXELS (1280u*720u)
#define TRASC_MAX_HEIGHT 768u
#define TRASC_REGIONS_MAGIC 0x54524632u
#define TRASC_REQUEST_FULL 1u
#define TRASC_REQUEST_REGIONS 2u
#define TRASC_REQUEST_CAPABILITIES 3u
#define TRASC_SHM 1u
#define TRASC_UNCHANGED 2u
#define TRASC_REGION 4u
/* Eight network-order uint32 values: magic,w,h,stride,capture_us,sequence,bytes,flags.
 * Region packets append four network-order values: x,y,w,h, then packed XRGB pixels.
 * Request 1 retains the original full-frame protocol; request 2 permits regions.
 * Request 3 replies with REGIONS_MAGIC, without capturing or changing the baseline. */
static inline int trasc_frame_valid(const uint32_t *h) {
    return h[0]==TRASC_MAGIC && h[1]>0 && h[2]>0 && h[1]<=1280 && h[2]<=768 &&
        (uint64_t)h[1]*h[2]<=TRASC_MAX_PIXELS && h[3]==h[1]*4 && h[7]<=7 &&
        !((h[7]&TRASC_UNCHANGED)&&(h[7]&TRASC_REGION)) &&
        ((h[7]&TRASC_UNCHANGED)?h[6]==0:(h[7]&TRASC_REGION)?
            h[6]>0&&h[6]<=h[3]*h[2]:h[6]==h[3]*h[2]);
}
static inline int trasc_region_valid(const uint32_t *h,const uint32_t *r) {
    return r[0]<h[1] && r[1]<h[2] && r[2]>0 && r[3]>0 &&
        r[2]<=h[1]-r[0] && r[3]<=h[2]-r[1] && (uint64_t)r[2]*r[3]*4==h[6];
}
/* Exact pixel bounds, including the composited cursor. Broad damage uses a full
 * frame early; legacy mode retains the original first-difference fast path. */
static inline int trasc_changed_region(const unsigned char *previous,const unsigned char *pixels,
        size_t stride,uint32_t width,uint32_t height,int regions,uint32_t *r) {
    uint32_t left=width,right=0,top=height,bottom=0;
    for(uint32_t y=0;y<height;y++){
        const uint32_t *old=(const uint32_t *)(previous+(size_t)y*width*4);
        const uint32_t *next=(const uint32_t *)(pixels+(size_t)y*stride);
        if(!memcmp(old,next,(size_t)width*4))continue;
        if(!regions){r[0]=r[1]=0;r[2]=width;r[3]=height;return 1;}
        uint32_t first=0,last=width;
        while(first<width&&old[first]==next[first])first++;
        while(last>first&&old[last-1]==next[last-1])last--;
        if(first<left)left=first;
        if(last>right)right=last;
        if(y<top)top=y;
        bottom=y+1;
        if((uint64_t)(right-left)*(bottom-top)*100>=(uint64_t)width*height*60){
            r[0]=r[1]=0;r[2]=width;r[3]=height;return 1;
        }
    }
    if(!right)return 0;
    r[0]=left;r[1]=top;r[2]=right-left;r[3]=bottom-top;return 1;
}
static inline void trasc_bgra_rgba(uint32_t *dst,const uint32_t *src,size_t count) {
    for(size_t i=0;i<count;i++){uint32_t p=src[i];dst[i]=0xff000000u|((p&0xff)<<16)|(p&0xff00)|((p>>16)&0xff);}
}
#endif
