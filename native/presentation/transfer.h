#ifndef TRASC_TRANSFER_H
#define TRASC_TRANSFER_H
#include <sys/socket.h>
#include <sys/uio.h>
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "frame.h"
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
static inline int trasc_receive_all(int fd,void *data,size_t size,uint64_t *calls){
    unsigned char *p=data;
    while(size){
        ++*calls;ssize_t n=recv(fd,p,size,0);
        if(n<0&&errno==EINTR)continue;
        if(n<=0)return -1;
        p+=n;size-=(size_t)n;
    }
    return 0;
}
/* Scatter packed region rows directly into the retained full image. Partial
 * socket reads advance the iovecs; no patch allocation or merge copy is needed. */
static inline int trasc_receive_pixels(int fd,void *data,size_t row,size_t stride,size_t height,uint64_t *calls){
    if(!row||!height||height>TRASC_MAX_HEIGHT||stride<row||height>SIZE_MAX/stride)return -1;
    if(row==stride)return trasc_receive_all(fd,data,row*height,calls);
    struct iovec rows[TRASC_MAX_HEIGHT];
    for(size_t y=0;y<height;y++){rows[y].iov_base=(unsigned char *)data+y*stride;rows[y].iov_len=row;}
    size_t first=0;
    while(first<height){
        struct msghdr message={.msg_iov=rows+first,.msg_iovlen=height-first};
        ++*calls;ssize_t n=recvmsg(fd,&message,0);
        if(n<0&&errno==EINTR)continue;
        if(n<=0)return -1;
        size_t left=(size_t)n;
        while(left){
            if(left>=rows[first].iov_len){left-=rows[first].iov_len;first++;}
            else{rows[first].iov_base=(unsigned char *)rows[first].iov_base+left;rows[first].iov_len-=left;left=0;}
        }
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
