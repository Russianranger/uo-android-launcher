#define _POSIX_C_SOURCE 200809L
#include <X11/Xlib.h>
#include <X11/extensions/Xfixes.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>
#include <arpa/inet.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <errno.h>
#include "../native/presentation/frame.h"
static pid_t child;
static void cleanup(void){if(child>0){kill(child,SIGTERM);waitpid(child,NULL,0);}}
static void check(int ok,const char *why){if(!ok){fprintf(stderr,"FAIL: %s\n",why);exit(1);}}
static void pause_ms(int ms){struct timespec t={ms/1000,(ms%1000)*1000000L};nanosleep(&t,NULL);}
static void receive(int fd,void *data,size_t n){unsigned char *p=data;while(n){ssize_t r=read(fd,p,n);check(r>0,"frame EOF");p+=r;n-=(size_t)r;}}
static uint32_t frame[1280*720],width,height,flags;static int regions;
static uint64_t bytes,full_bytes,region_frames,frames;
static void capture(int fd){unsigned char request=regions?TRASC_REQUEST_REGIONS:TRASC_REQUEST_FULL;check(write(fd,&request,1)==1,"request");uint32_t h[8];receive(fd,h,sizeof(h));for(int i=0;i<8;i++)h[i]=ntohl(h[i]);
    check(trasc_frame_valid(h),"header");
    if(h[7]&TRASC_REGION){
        uint32_t r[4];receive(fd,r,sizeof(r));for(int i=0;i<4;i++)r[i]=ntohl(r[i]);
        check(regions&&width==h[1]&&height==h[2]&&trasc_region_valid(h,r),"region baseline/bounds");
        for(uint32_t y=r[1];y<r[1]+r[3];y++)receive(fd,frame+(size_t)y*width+r[0],r[2]*4);
        region_frames++;
    }else if(h[6])receive(fd,frame,h[6]);
    width=h[1];height=h[2];flags=h[7];
    if(h[6]){frames++;bytes+=h[6];full_bytes+=(uint64_t)width*height*4;}
}
static uint32_t pixel(unsigned x,unsigned y){return frame[y*width+x]&0xffffff;}
static int connect_bridge(const char *path){struct sockaddr_un a={.sun_family=AF_UNIX};snprintf(a.sun_path,sizeof(a.sun_path),"%s",path);int fd=-1;
    for(int i=0;i<300;i++){fd=socket(AF_UNIX,SOCK_STREAM,0);if(connect(fd,(struct sockaddr *)&a,sizeof(a))==0)return fd;close(fd);pause_ms(10);}check(0,"connect");return -1;}
int main(int argc,char **argv){
    check(argc==6,"bridge socket mode transport fps");regions=!strcmp(argv[4],"regions");atexit(cleanup);Display *d=XOpenDisplay(NULL);check(d!=NULL,"display");Window root=DefaultRootWindow(d);
    XSetWindowBackground(d,root,0x112233);XClearWindow(d,root);
    const char bits[4]={15,15,15,15};Pixmap bitmap=XCreateBitmapFromData(d,root,bits,4,4);
    XColor red={.red=65535},green={.green=65535};
    Cursor first=XCreatePixmapCursor(d,bitmap,bitmap,&red,&red,1,1);
    Cursor second=XCreatePixmapCursor(d,bitmap,bitmap,&green,&green,1,1);
    XDefineCursor(d,root,first);XWarpPointer(d,None,root,0,0,0,0,10,10);XSync(d,False);
    child=fork();check(child>=0,"fork");if(child==0){if(!strcmp(argv[3],"fallback"))execl(argv[1],argv[1],argv[2],argv[5],"--no-shm",NULL);else execl(argv[1],argv[1],argv[2],argv[5],NULL);_exit(127);}
    int fd=connect_bridge(argv[2]);unsigned char capability=TRASC_REQUEST_CAPABILITIES;uint32_t answer=0;
    check(write(fd,&capability,1)==1,"capability request");receive(fd,&answer,sizeof(answer));check(ntohl(answer)==TRASC_REGIONS_MAGIC,"region capability");
    capture(fd);check(width==1280&&height==720,"initial size");check(!(flags&(TRASC_UNCHANGED|TRASC_REGION)),"first frame is full");
    check((flags&1)==(strcmp(argv[3],"fallback")!=0),"capture mode");
    check(pixel(10,10)==0xff0000&&pixel(100,100)==0x112233,"initial cursor/background");
    for(int i=0;i<20;i++){capture(fd);check(flags&2,"idle exact frame suppression");}
    XWarpPointer(d,None,root,0,0,0,0,25,30);XSync(d,False);capture(fd);
    check(!(flags&2)&&pixel(25,30)==0xff0000&&pixel(10,10)==0x112233,"cached shape follows pointer");
    check(!regions||(flags&TRASC_REGION),"cursor movement uses region");
    XDefineCursor(d,root,second);XSync(d,False);capture(fd);check(pixel(25,30)==0x00ff00,"shape notification refresh");
    XWarpPointer(d,None,root,0,0,0,0,0,0);XSync(d,False);capture(fd);check(pixel(0,0)==0x00ff00,"cursor clipping");
    GC gc=XCreateGC(d,root,0,NULL);XSetForeground(d,gc,0xabcdef);XFillRectangle(d,root,gc,300,200,16,8);XSync(d,False);capture(fd);
    check(pixel(300,200)==0xabcdef&&pixel(299,200)==0x112233,"small UI update");check(!regions||(flags&TRASC_REGION),"small UI region");
    XSetForeground(d,gc,0x778899);XFillRectangle(d,root,gc,1100,600,20,15);XSync(d,False);capture(fd);
    check(pixel(300,200)==0xabcdef&&pixel(1100,600)==0x778899,"disjoint updates retain previous patches");
    XFillRectangle(d,root,gc,20,20,20,20);XFillRectangle(d,root,gc,1250,690,20,20);XSync(d,False);capture(fd);
    check(!(flags&TRASC_REGION)&&pixel(20,20)==0x778899&&pixel(1250,690)==0x778899,"broad damage uses full frame");
    XSetWindowBackground(d,root,0x445566);XClearWindow(d,root);XSync(d,False);capture(fd);check(pixel(100,100)==0x445566,"damage refresh");
    check(system("xrandr -s 800x600 >/dev/null")==0,"resize request");pause_ms(50);capture(fd);check(width==800&&height==600&&!(flags&2),"resize refresh");
    check(system("xrandr -s 1280x720 >/dev/null")==0,"restore size");pause_ms(50);capture(fd);check(width==1280&&height==720&&!(flags&2),"resize back");
    pause_ms(2100);capture(fd);check(flags&2,"periodic refresh preserves unchanged protocol");
    close(fd);pause_ms(50);fd=connect_bridge(argv[2]);capture(fd);check(!(flags&(TRASC_UNCHANGED|TRASC_REGION))&&width==1280,"reconnect owns fresh full baseline");close(fd);
    check(regions?region_frames>=4&&bytes<full_bytes:region_frames==0&&bytes==full_bytes,"transport byte accounting");
    XFreeGC(d,gc);XFreeCursor(d,first);XFreeCursor(d,second);XFreePixmap(d,bitmap);XCloseDisplay(d);pause_ms(50);
    printf("PRESENTATION_CACHE_OK mode=%s frames=%llu regions=%llu pixel_bytes=%llu full_frame_bytes=%llu fraction=%.6f cursor_move=true cursor_shape=true clipping=true resize=true reconnect=true idle=true\n",argv[4],(unsigned long long)frames,(unsigned long long)region_frames,(unsigned long long)bytes,(unsigned long long)full_bytes,(double)bytes/full_bytes);return 0;
}
