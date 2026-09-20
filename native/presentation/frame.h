#ifndef TRASC_FRAME_H
#define TRASC_FRAME_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define TRASC_MAGIC 0x54524631u
#define TRASC_MAX_PIXELS (1280u*720u)
/* Eight network-order uint32 values: magic,w,h,stride,capture_us,sequence,bytes,flags (bit0 SHM; bit1 unchanged). */
static inline int trasc_frame_valid(const uint32_t *h) {
    return h[0]==TRASC_MAGIC && h[1]>0 && h[2]>0 && h[1]<=1280 && h[2]<=768 &&
        (uint64_t)h[1]*h[2]<=TRASC_MAX_PIXELS && h[3]==h[1]*4 && h[7]<=3 && ((h[7]&2)?h[6]==0:h[6]==h[3]*h[2]);
}
static inline void trasc_bgra_rgba(uint32_t *dst,const uint32_t *src,size_t count) {
    for(size_t i=0;i<count;i++){uint32_t p=src[i];dst[i]=0xff000000u|((p&0xff)<<16)|(p&0xff00)|((p>>16)&0xff);}
}
#endif
