#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>
#include "../native/presentation/android-surface.c"

/* Exercise the actual JNI receiver against fragmented Unix socket packets and
 * a three-buffer Surface model. Expansion deliberately returns an unpreserved
 * buffer, requiring the receiver's complete retained image. */
struct ANativeWindow {int width,height,format,current,posted,posts,locks,expand,bad;uint32_t buffers[3][64*48];};
static struct ANativeWindow window;
_Alignas(uint32_t) static unsigned char storage[CACHE_BYTES+sizeof(struct frame_cache)];
static jlong storage_capacity=sizeof(storage);
struct measures {jlong values[15];jsize length;};
static struct measures timing={.length=15};
static void check(int ok,const char *why){if(!ok){fprintf(stderr,"FAIL: %s\n",why);exit(1);}}
static void *address(JNIEnv *env,jobject object){(void)env;return (void *)object;}
static jlong capacity(JNIEnv *env,jobject object){(void)env;(void)object;return storage_capacity;}
static jsize length(JNIEnv *env,jarray object){(void)env;return ((struct measures *)object)->length;}
static void output(JNIEnv *env,jlongArray object,jsize start,jsize count,const jlong *values){(void)env;memcpy(((struct measures *)object)->values+start,values,(size_t)count*sizeof(jlong));}
static const struct JNINativeInterface_ table={.GetDirectBufferAddress=address,.GetDirectBufferCapacity=capacity,.GetArrayLength=length,.SetLongArrayRegion=output};
static JNIEnv environment=&table;
ANativeWindow *ANativeWindow_fromSurface(JNIEnv *env,jobject object){(void)env;return (ANativeWindow *)object;}
int32_t ANativeWindow_getWidth(ANativeWindow *w){return w->width;}
int32_t ANativeWindow_getHeight(ANativeWindow *w){return w->height;}
int32_t ANativeWindow_getFormat(ANativeWindow *w){return w->format;}
int32_t ANativeWindow_setBuffersGeometry(ANativeWindow *w,int32_t x,int32_t y,int32_t format){w->width=x;w->height=y;w->format=format;return 0;}
int32_t ANativeWindow_lock(ANativeWindow *w,ANativeWindow_Buffer *buffer,ARect *dirty){
    w->locks++;w->current=(w->posted+1)%3;
    check(dirty!=NULL,"Surface dirty bounds supplied");
    if(w->expand){*dirty=(ARect){0,0,w->width,w->height};for(size_t i=0;i<64*48;i++)w->buffers[w->current][i]=0xdeadbeef;}
    else memcpy(w->buffers[w->current],w->buffers[w->posted],sizeof(w->buffers[0]));
    *buffer=(ANativeWindow_Buffer){.width=w->width+w->bad,.height=w->height,.stride=64,.format=w->format,.bits=w->buffers[w->current]};return 0;
}
int32_t ANativeWindow_unlockAndPost(ANativeWindow *w){w->posted=w->current;w->posts++;return 0;}
void ANativeWindow_release(ANativeWindow *w){(void)w;}
static void write_packet(int fd,const void *data,size_t size){
    const unsigned char *p=data;size_t chunk=1;
    while(size){size_t next=chunk<size?chunk:size;ssize_t sent=write(fd,p,next);if(sent<0&&(errno==EPIPE||errno==ECONNRESET))return;if(sent<=0)_exit(2);p+=sent;size-=(size_t)sent;chunk=chunk%19+1;}
}
static int deliver(uint32_t *header,uint32_t *region,const uint32_t *pixels,size_t size,int regions){
    int pair[2];check(socketpair(AF_UNIX,SOCK_STREAM,0,pair)==0,"socket pair");pid_t child=fork();check(child>=0,"fork");
    if(!child){
        close(pair[0]);unsigned char request=0;if(read(pair[1],&request,1)!=1||request!=(regions?2:1))_exit(3);
        uint32_t wire[8];for(int i=0;i<8;i++)wire[i]=htonl(header[i]);write_packet(pair[1],wire,sizeof(wire));
        if(header[7]&TRASC_REGION){uint32_t bounds[4];for(int i=0;i<4;i++)bounds[i]=htonl(region[i]);write_packet(pair[1],bounds,sizeof(bounds));}
        if(size)write_packet(pair[1],pixels,size);
        close(pair[1]);_exit(0);
    }
    close(pair[1]);int result=Java_io_github_russianranger_trasc_NativePresentation_frame(&environment,NULL,(jobject)&window,pair[0],(jobject)storage,(jlongArray)&timing,(jboolean)regions);
    close(pair[0]);int status;waitpid(child,&status,0);check(WIFEXITED(status)&&WEXITSTATUS(status)==0,"packet writer");return result;
}
static void full(uint32_t sequence,uint32_t width,uint32_t height,uint32_t color,int regions){
    uint32_t pixels[32*24];check(width*height<=32*24,"test frame capacity");for(uint32_t i=0;i<width*height;i++)pixels[i]=color;
    uint32_t header[8]={TRASC_MAGIC,width,height,width*4,50,sequence,width*height*4,TRASC_SHM};
    check(deliver(header,NULL,pixels,header[6],regions)==0,"full frame delivery");
}
static void patch(uint32_t sequence,uint32_t x,uint32_t y,uint32_t width,uint32_t height,uint32_t color){
    uint32_t pixels[32*24];for(uint32_t i=0;i<width*height;i++)pixels[i]=color;
    uint32_t header[8]={TRASC_MAGIC,16,12,64,50,sequence,width*height*4,TRASC_SHM|TRASC_REGION},region[4]={x,y,width,height};
    check(deliver(header,region,pixels,header[6],1)==0,"region delivery");
}
static uint32_t pixel(int x,int y){return window.buffers[window.posted][y*64+x];}
static void baseline(void){memset(storage,0,sizeof(storage));memset(&window,0,sizeof(window));for(int b=0;b<3;b++)for(int i=0;i<64*48;i++)window.buffers[b][i]=0xdeadbeef;full(1,16,12,0x00112233,1);}
static void capability(int legacy){
    int pair[2];check(socketpair(AF_UNIX,SOCK_STREAM,0,pair)==0,"capability socket");pid_t child=fork();check(child>=0,"capability fork");
    if(!child){close(pair[0]);unsigned char request=0;if(read(pair[1],&request,1)!=1||request!=TRASC_REQUEST_CAPABILITIES)_exit(1);
        if(!legacy){uint32_t value=htonl(TRASC_REGIONS_MAGIC);write_packet(pair[1],&value,sizeof(value));}close(pair[1]);_exit(0);}
    close(pair[1]);check(Java_io_github_russianranger_trasc_NativePresentation_capabilities(&environment,NULL,pair[0])==!legacy,"capability/legacy negotiation");close(pair[0]);int status;waitpid(child,&status,0);check(status==0,"capability writer");
}
static void tall_region(void){
    uint32_t image[TRASC_MAX_HEIGHT][3],packed[TRASC_MAX_HEIGHT];
    for(unsigned y=0;y<TRASC_MAX_HEIGHT;y++){image[y][0]=image[y][1]=image[y][2]=0xdeadbeef;packed[y]=y+1;}
    int pair[2];check(socketpair(AF_UNIX,SOCK_STREAM,0,pair)==0,"tall region socket");pid_t child=fork();check(child>=0,"tall region fork");
    if(!child){close(pair[0]);write_packet(pair[1],packed,sizeof(packed));close(pair[1]);_exit(0);}
    close(pair[1]);uint64_t calls=0;check(trasc_receive_pixels(pair[0],&image[0][1],4,12,TRASC_MAX_HEIGHT,&calls)==0,"maximum-height scatter receive");
    close(pair[0]);int status;waitpid(child,&status,0);check(status==0&&calls>0,"tall region writer/calls");
    for(unsigned y=0;y<TRASC_MAX_HEIGHT;y++)check(image[y][1]==y+1&&image[y][0]==0xdeadbeef&&image[y][2]==0xdeadbeef,"fragmented scatter preserves all row gaps");
    check(trasc_receive_pixels(-1,image,4,12,TRASC_MAX_HEIGHT+1,&calls)==-1,"oversized scatter height rejected");
}
int main(void){
    signal(SIGPIPE,SIG_IGN);capability(0);capability(1);tall_region();baseline();
    check(pixel(15,11)==0xff332211&&pixel(16,11)==0xdeadbeef,"full frame color/stride/padding");
    patch(2,2,3,4,2,0x00ff0000);check(timing.values[9]==8&&timing.values[10]==192&&timing.values[7]==32,"region timing areas/bytes");
    check(pixel(2,3)==0xff0000ff&&pixel(1,3)==0xff332211&&pixel(16,11)==0xdeadbeef,"localized conversion preserves other pixels");
    window.expand=1;patch(3,12,8,2,3,0x0000ff00);
    check(timing.values[9]==192&&timing.values[12]==1,"expanded Surface records actual redraw");
    for(int y=0;y<12;y++)for(int x=0;x<16;x++){
        uint32_t expected=(x>=2&&x<6&&y>=3&&y<5)?0xff0000ff:(x>=12&&x<14&&y>=8&&y<11)?0xff00ff00:0xff332211;
        check(pixel(x,y)==expected,"buffer-age expansion redraws complete canonical image");
    }
    uint32_t idle[8]={TRASC_MAGIC,16,12,64,0,4,0,TRASC_UNCHANGED};int posts=window.posts,locks=window.locks;
    check(deliver(idle,NULL,NULL,0,1)==1&&window.posts==posts&&window.locks==locks,"unchanged never locks/posts");
    full(5,8,6,0x000000ff,1);check(window.width==8&&window.height==6&&pixel(7,5)==0xffff0000&&timing.values[13]==1,"resized full frame");
    baseline();uint32_t header[8]={TRASC_MAGIC,16,12,64,0,2,4,TRASC_REGION},bounds[4]={2,2,1,1},red=0x00ff0000;posts=window.posts;
    bounds[0]=UINT32_MAX;check(deliver(header,bounds,&red,4,1)==-2&&window.posts==posts,"overflowing rectangle rejected");bounds[0]=2;
    header[6]=8;check(deliver(header,bounds,&red,4,1)==-2,"rectangle byte mismatch rejected");header[6]=4;
    header[5]=3;check(deliver(header,bounds,&red,4,1)==-2,"missed sequence rejected");header[5]=2;
    check(deliver(header,bounds,&red,4,0)==-2,"unsolicited region rejected");
    header[1]=8;header[3]=32;check(deliver(header,bounds,&red,4,1)==-2,"region cannot resize baseline");header[1]=16;header[3]=64;
    memset(storage,0,sizeof(storage));check(deliver(header,bounds,&red,4,1)==-2,"region requires initial full frame");
    baseline();check(deliver(header,bounds,NULL,0,1)==-3&&window.posts==1,"truncated payload never posted");
    storage_capacity=CACHE_BYTES;check(deliver(header,bounds,&red,4,1)==-3,"undersized cache rejected");storage_capacity=sizeof(storage);
    baseline();window.bad=1;check(deliver(header,bounds,&red,4,1)==-6,"bad Surface buffer rejected");
    memset(storage,0,sizeof(storage));window.bad=0;full(77,16,12,0x0000ff00,0);check(pixel(15,11)==0xff00ff00,"fresh legacy stream uses full baseline");
    uint32_t invalid[8]={TRASC_MAGIC,1280,768,1280*4,0,1,1280*768*4,0};check(!trasc_frame_valid(invalid),"maximum pixel count enforced");
    invalid[1]=1024;invalid[3]=4096;invalid[6]=1024*768*4;check(trasc_frame_valid(invalid),"supported 1024x768 frame");
    invalid[7]=8;check(!trasc_frame_valid(invalid),"unknown flags rejected");
    puts("NATIVE_SURFACE_REGIONS_OK fragmented=true cursor_colors=true buffer_age=true resize=true reconnect=true legacy=true invalid_packets=true no_patch_copy=true");return 0;
}
