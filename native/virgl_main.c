#include <epoxy/egl.h>
#include <epoxy/gl.h>
#include <stdio.h>
#include <signal.h>
#include <errno.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#include "vtest_server.h"

/* Query the real host driver before accepting any guest rendering commands. */
static int probe_driver(void) {
#ifdef __ANDROID__
    EGLDisplay display=eglGetDisplay(EGL_DEFAULT_DISPLAY);
#else
    EGLDisplay display=eglGetPlatformDisplayEXT(EGL_PLATFORM_SURFACELESS_MESA,EGL_DEFAULT_DISPLAY,NULL);
#endif
    EGLint major,minor,count;
    if(display==EGL_NO_DISPLAY||!eglInitialize(display,&major,&minor))goto fail;
    if(!eglBindAPI(EGL_OPENGL_ES_API))goto fail;
    const EGLint attributes[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES3_BIT,EGL_NONE};
    EGLConfig config;
    if(!eglChooseConfig(display,attributes,&config,1,&count)||count!=1)goto fail;
    const EGLint context_attributes[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    EGLContext context=eglCreateContext(display,config,EGL_NO_CONTEXT,context_attributes);
    const EGLint surface_attributes[]={EGL_WIDTH,1,EGL_HEIGHT,1,EGL_NONE};
    EGLSurface surface=eglCreatePbufferSurface(display,config,surface_attributes);
    if(context==EGL_NO_CONTEXT||surface==EGL_NO_SURFACE||!eglMakeCurrent(display,surface,surface,context))goto fail;
    printf("TRASC GPU vendor: %s\n",glGetString(GL_VENDOR));
    printf("TRASC GPU renderer: %s\n",glGetString(GL_RENDERER));
    printf("TRASC GPU version: %s\n",glGetString(GL_VERSION));
    eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroySurface(display,surface);eglDestroyContext(display,context);eglTerminate(display);
    return 0;
fail:
    fprintf(stderr,"Android graphics driver initialization failed: EGL error 0x%x\n",eglGetError());
    return 1;
}
int main(int argc,char **argv) {
    umask(0077);setvbuf(stdout,NULL,_IOLBF,0);setvbuf(stderr,NULL,_IOLBF,0);
    pid_t parent=getppid();
    if(prctl(PR_SET_PDEATHSIG,SIGTERM)!=0||getppid()!=parent)return 1;
    /* Keep Android driver threads out of the parent that forks vtest workers. */
    pid_t launcher=getpid(),probe=fork();
    if(probe<0)return 1;
    if(probe==0) {
        if(prctl(PR_SET_PDEATHSIG,SIGKILL)!=0||getppid()!=launcher)_exit(1);
        _exit(probe_driver());
    }
    int status;
    while(waitpid(probe,&status,0)<0){if(errno!=EINTR)return 1;}
    if(!WIFEXITED(status)||WEXITSTATUS(status)!=0)return 1;
    return vtest_main(argc,argv);
}
