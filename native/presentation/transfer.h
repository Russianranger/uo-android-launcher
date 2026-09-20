#ifndef TRASC_TRANSFER_H
#define TRASC_TRANSFER_H
#include <sys/socket.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#ifndef TRASC_SEND
#define TRASC_SEND send
#endif
/* Counts actual send attempts, including interruptions/partial writes. */
static inline int trasc_send_all(int fd,const void *data,size_t size,uint64_t *calls){
    const unsigned char *p=data;
    while(size){
        ++*calls;ssize_t n=TRASC_SEND(fd,p,size,MSG_NOSIGNAL);
        if(n<0&&errno==EINTR)continue;
        if(n<=0)return -1;
        p+=n;size-=(size_t)n;
    }
    return 0;
}
/* XImage is normally already packed. Allocate reusable scratch only for padded rows. */
static inline int trasc_send_pixels(int fd,const void *data,size_t row,size_t stride,size_t height,unsigned char **scratch,size_t *capacity,uint64_t *calls){
    if(!row||!height||stride<row||height>SIZE_MAX/stride)return -1;
    size_t size=row*height;const void *pixels=data;
    if(stride!=row){
        if(*capacity<size){void *next=realloc(*scratch,size);if(!next)return -1;*scratch=next;*capacity=size;}
        for(size_t y=0;y<height;y++)memcpy(*scratch+y*row,(const unsigned char *)data+y*stride,row);
        pixels=*scratch;
    }
    return trasc_send_all(fd,pixels,size,calls);
}
#endif
