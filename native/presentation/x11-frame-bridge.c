#define _POSIX_C_SOURCE 200809L
#include "frame.h"
#include "transfer.h"
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/XShm.h>
#include <X11/extensions/Xfixes.h>
#include <X11/extensions/Xdamage.h>
#include <sys/ipc.h>
#include <sys/shm.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <sys/time.h>
#include "input.h"
static int xerror;
static int error_handler(Display *d,XErrorEvent *e){(void)d;xerror=e->error_code;return 0;}
static uint64_t now_ns(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
struct frame_stats {uint64_t since,frames,capture_ns,send_ns,pace_ns,calls,bytes,requests,captures,idle,duplicates;};
static void report(struct frame_stats *s,int final){
    uint64_t now=now_ns();if(!s->requests||(!final&&now-s->since<5000000000ull))return;
    double frames=s->frames?(double)s->frames:1,requests=(double)s->requests,captures=s->captures?(double)s->captures:1;
    fprintf(stderr,"{\"transport\":\"batched-v2\",\"frames\":%llu,\"seconds\":%.3f,\"capture_ms_per_frame\":%.3f,\"send_ms_per_frame\":%.3f,\"pacing_ms_per_request\":%.3f,\"send_calls_per_frame\":%.3f,\"bytes_per_frame\":%.0f,\"requests\":%llu,\"captures\":%llu,\"idle_skips\":%llu,\"duplicate_skips\":%llu}\n",
        (unsigned long long)s->frames,(now-s->since)/1e9,s->capture_ns/1e6/captures,s->send_ns/1e6/frames,s->pace_ns/1e6/requests,s->calls/frames,s->bytes/frames,
        (unsigned long long)s->requests,(unsigned long long)s->captures,(unsigned long long)s->idle,(unsigned long long)s->duplicates);fflush(stderr);
    memset(s,0,sizeof(*s));s->since=now;
}
static int unchanged(int fd,uint32_t *header,int shared,struct frame_stats *stats){
    uint32_t wire[8];header[4]=0;header[6]=0;header[7]=2u|(unsigned)shared;
    for(int i=0;i<8;i++)wire[i]=htonl(header[i]);
    uint64_t calls=0;int result=trasc_send_all(fd,wire,sizeof(wire),&calls);report(stats,0);return result;
}
static void cursor(Display *d,XImage *image){
    XFixesCursorImage *c=XFixesGetCursorImage(d);if(!c)return;
    int left=(int)c->x-c->xhot,top=(int)c->y-c->yhot;
    for(unsigned y=0;y<c->height;y++)for(unsigned x=0;x<c->width;x++){
        int px=left+(int)x,py=top+(int)y;if(px<0||py<0||px>=image->width||py>=image->height)continue;
        uint32_t p=(uint32_t)c->pixels[y*c->width+x],alpha=p>>24;if(!alpha)continue;
        uint32_t *dst=(uint32_t *)(image->data+py*image->bytes_per_line)+px,v=*dst,result=0;
        for(unsigned shift=0;shift<24;shift+=8){unsigned value=((p>>shift)&255)+(((v>>shift)&255)*(255-alpha)+127)/255;result|=(value>255?255:value)<<shift;}
        *dst=result;
    }XFree(c);
}
int main(int argc,char **argv){
    signal(SIGPIPE,SIG_IGN);
    if(argc==3&&!strcmp(argv[1],"--input"))return input_server(argv[2]);
    if(argc!=3&&(argc!=4||strcmp(argv[3],"--no-shm"))){fprintf(stderr,"Usage: x11-frame-bridge socket fps [--no-shm]\n");return 2;}
    int no_shm=argc==4;
    int fps=atoi(argv[2]);if(fps!=30&&fps!=60)return 2;
    signal(SIGPIPE,SIG_IGN);XSetErrorHandler(error_handler);
    Display *d=XOpenDisplay(NULL);if(!d){fprintf(stderr,"No X display\n");return 3;}
    int fixes_event,fixes_error;if(!XFixesQueryExtension(d,&fixes_event,&fixes_error)){fprintf(stderr,"XFixes cursor capture required\n");return 3;}
    struct sockaddr_un addr={.sun_family=AF_UNIX};if(strlen(argv[1])>=sizeof(addr.sun_path))return 2;strcpy(addr.sun_path,argv[1]);
    int listener=socket(AF_UNIX,SOCK_STREAM,0);if(listener<0)return 4;
    umask(0077);unlink(argv[1]);if(bind(listener,(struct sockaddr *)&addr,sizeof(addr))||listen(listener,1))return 4;
    int damage_event=0,damage_error=0,damage_ready=XDamageQueryExtension(d,&damage_event,&damage_error);
    Damage damage=damage_ready?XDamageCreate(d,DefaultRootWindow(d),XDamageReportNonEmpty):0;
    XFixesSelectCursorInput(d,DefaultRootWindow(d),XFixesDisplayCursorNotifyMask);
    fprintf(stderr,"Change tracking: %s; exact pixel comparison enabled\n",damage_ready?"XDamage":"periodic capture fallback");
    uint32_t sequence=0;fprintf(stderr,"TRASC native Surface bridge ready, cap=%d; X11 readback retained\n",fps);fflush(stderr);
    for(;;){
        int fd=accept(listener,NULL,NULL);if(fd<0){if(errno==EINTR)continue;break;}
        struct timeval timeout={.tv_sec=5};setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout));
        XImage *image=NULL;XShmSegmentInfo shm={.shmid=-1};int shared=0,lastw=0,lasth=0;uint64_t last=0;
        unsigned char *packed=NULL,*previous=NULL;size_t packed_capacity=0,previous_size=0;
        uint64_t last_capture=0;int pointer_x=-1,pointer_y=-1;struct frame_stats stats={.since=now_ns()};
        unsigned char request;
        while(recv(fd,&request,1,0)==1&&request==1){
            uint64_t elapsed=now_ns()-last,interval=1000000000u/(unsigned)fps;
            uint64_t pacing=now_ns();if(last&&elapsed<interval){struct timespec wait={.tv_nsec=(long)(interval-elapsed)};while(nanosleep(&wait,&wait)&&errno==EINTR){}}stats.pace_ns+=now_ns()-pacing;last=now_ns();
            stats.requests++;
            XWindowAttributes a;if(!XGetWindowAttributes(d,DefaultRootWindow(d),&a))break;
            uint32_t header[8]={TRASC_MAGIC,(uint32_t)a.width,(uint32_t)a.height,(uint32_t)a.width*4,0,++sequence,(uint32_t)a.width*a.height*4,0};
            if(!trasc_frame_valid(header))break;
            Window root,child;int rx=0,ry=0,wx=0,wy=0;unsigned mask=0;
            XQueryPointer(d,DefaultRootWindow(d),&root,&child,&rx,&ry,&wx,&wy,&mask);
            int resized=a.width!=lastw||a.height!=lasth;
            int dirty=!previous||resized||rx!=pointer_x||ry!=pointer_y;
            pointer_x=rx;pointer_y=ry;
            while(XPending(d)){XEvent event;XNextEvent(d,&event);if((damage_ready&&event.type==damage_event+XDamageNotify)||event.type==fixes_event+XFixesCursorNotify)dirty=1;}
            if(damage_ready&&!dirty&&now_ns()-last_capture<2000000000ull){stats.idle++;if(unchanged(fd,header,shared,&stats))break;continue;}
            if(damage_ready)XDamageSubtract(d,damage,None,None);

            if(image&&(a.width!=lastw||a.height!=lasth)){if(shared){XShmDetach(d,&shm);XSync(d,False);shmdt(shm.shmaddr);image->data=NULL;}XDestroyImage(image);image=NULL;shared=0;}
            if(!image){
                lastw=a.width;lasth=a.height;xerror=0;
                const char *reason=no_shm?"disabled by diagnostic --no-shm":"MIT-SHM extension unavailable";int reason_errno=0,reason_xerror=0;
                if(!no_shm&&XShmQueryExtension(d)){
                    reason="XShmCreateImage failed";
                    image=XShmCreateImage(d,a.visual,(unsigned)a.depth,ZPixmap,NULL,&shm,(unsigned)a.width,(unsigned)a.height);
                    if(image){
                        shm.shmid=shmget(IPC_PRIVATE,(size_t)image->bytes_per_line*image->height,IPC_CREAT|0600);
                        if(shm.shmid<0){reason="shmget failed";reason_errno=errno;}
                        else{
                            shm.shmaddr=shmat(shm.shmid,NULL,0);shm.readOnly=False;
                            if(shm.shmaddr==(char *)-1){reason="shmat failed";reason_errno=errno;}
                            else{
                                image->data=shm.shmaddr;shared=XShmAttach(d,&shm);XSync(d,False);
                                if(xerror)shared=0;
                                if(!shared){reason="XShmAttach failed";reason_xerror=xerror;shmdt(shm.shmaddr);image->data=NULL;}
                            }
                            shmctl(shm.shmid,IPC_RMID,NULL);
                        }
                        if(!shared){image->data=NULL;XDestroyImage(image);image=NULL;}
                    }
                }
                fprintf(stderr,"Capture mode: %s; %dx%d; reason=%s; errno=%d; xerror=%d\n",shared?"MIT-SHM":"XGetImage",a.width,a.height,shared?"shared memory attached":reason,reason_errno,reason_xerror);fflush(stderr);
            }
            uint64_t capture=now_ns();last_capture=capture;stats.captures++;xerror=0;
            if(shared){if(!XShmGetImage(d,DefaultRootWindow(d),image,0,0,AllPlanes))break;}
            else {if(image)XDestroyImage(image);image=XGetImage(d,DefaultRootWindow(d),0,0,(unsigned)a.width,(unsigned)a.height,AllPlanes,ZPixmap);}
            if(!image||xerror||image->bits_per_pixel!=32||image->byte_order!=LSBFirst||image->red_mask!=0xff0000||image->green_mask!=0xff00||image->blue_mask!=0xff)break;
            cursor(d,image);if(xerror)break;
            uint64_t captured=now_ns();header[4]=(uint32_t)((captured-capture)/1000);header[7]=(uint32_t)shared;
            uint32_t wire[8];for(int i=0;i<8;i++)wire[i]=htonl(header[i]);
            stats.capture_ns+=captured-capture;
            int identical=!resized&&previous&&previous_size==header[6];
            if(identical)for(uint32_t y=0;y<header[2];y++)if(memcmp(previous+(size_t)y*header[3],image->data+(size_t)y*image->bytes_per_line,header[3])){identical=0;break;}
            if(identical){stats.duplicates++;if(unchanged(fd,header,shared,&stats))break;continue;}
            if(previous_size!=header[6]){unsigned char *next=realloc(previous,header[6]);if(!next)break;previous=next;previous_size=header[6];}
            for(uint32_t y=0;y<header[2];y++)memcpy(previous+(size_t)y*header[3],image->data+(size_t)y*image->bytes_per_line,header[3]);
            uint64_t sending=now_ns(),calls=0;
            if(trasc_send_all(fd,wire,sizeof(wire),&calls)||trasc_send_pixels(fd,image->data,header[3],(size_t)image->bytes_per_line,header[2],&packed,&packed_capacity,&calls))break;
            stats.frames++;stats.send_ns+=now_ns()-sending;stats.calls+=calls;stats.bytes+=header[6];report(&stats,0);
        }
        if(image){if(shared){XShmDetach(d,&shm);XSync(d,False);shmdt(shm.shmaddr);image->data=NULL;}XDestroyImage(image);}
        report(&stats,1);free(packed);free(previous);close(fd);
    }
    if(damage_ready)XDamageDestroy(d,damage);
    close(listener);unlink(argv[1]);XCloseDisplay(d);return 0;
}
