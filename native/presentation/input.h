/* Relative XTest motion retains deltas for Wine raw/DirectInput, including
 * beyond the visible desktop and across game-initiated cursor warps. */
#include <X11/extensions/XTest.h>
static int read_input(int fd,void *data,size_t size){
    char *p=data;while(size){ssize_t n=recv(fd,p,size,0);if(n<0&&errno==EINTR)continue;if(n<=0)return -1;p+=n;size-=(size_t)n;}return 0;
}
static void input_buttons(Display *d,unsigned previous,unsigned next){
    const unsigned bits[]={1,2,4,8,16};
    for(unsigned i=0;i<5;i++)if((previous^next)&bits[i])XTestFakeButtonEvent(d,i+1,(next&bits[i])!=0,CurrentTime);
}
static int input_server(const char *path){
    Display *d=XOpenDisplay(NULL);int event,error,major,minor;
    if(!d||!XTestQueryExtension(d,&event,&error,&major,&minor)){fprintf(stderr,"XTest relative input unavailable\n");return 3;}
    struct sockaddr_un address={.sun_family=AF_UNIX};if(strlen(path)>=sizeof(address.sun_path))return 2;strcpy(address.sun_path,path);
    int listener=socket(AF_UNIX,SOCK_STREAM,0);if(listener<0)return 4;
    umask(0077);unlink(path);if(bind(listener,(struct sockaddr *)&address,sizeof(address))||listen(listener,1))return 4;
    fprintf(stderr,"TRASC XTest relative input ready\n");fflush(stderr);
    for(;;){
        int fd=accept(listener,NULL,NULL);if(fd<0){if(errno==EINTR)continue;break;}
        unsigned buttons=0;uint32_t wire[4];unsigned long relative_count=0,absolute_count=0,button_count=0;
        fprintf(stderr,"Input consumer connected\n");fflush(stderr);
        if(send(fd,"TRASCIN1",8,MSG_NOSIGNAL)==8)while(!read_input(fd,wire,sizeof(wire))){
            unsigned type=ntohl(wire[0]),next=ntohl(wire[3]);int32_t x=(int32_t)ntohl(wire[1]),y=(int32_t)ntohl(wire[2]);
            if(type>2||next>31||x < -4096||x>4096||y < -4096||y>4096)break;
            if(type==0)absolute_count++;
            if(type==1)relative_count++;
            if(type==2)button_count++;
            if(type==0)XTestFakeMotionEvent(d,DefaultScreen(d),x<0?0:x,y<0?0:y,CurrentTime);
            if(type==1)XTestFakeRelativeMotionEvent(d,x,y,CurrentTime);
            input_buttons(d,buttons,next);buttons=next;XFlush(d);
        }
        input_buttons(d,buttons,0);XSync(d,False);close(fd);
        fprintf(stderr,"Input consumer disconnected: relative=%lu absolute=%lu buttons=%lu\n",relative_count,absolute_count,button_count);fflush(stderr);
    }
    close(listener);unlink(path);XCloseDisplay(d);return 0;
}
