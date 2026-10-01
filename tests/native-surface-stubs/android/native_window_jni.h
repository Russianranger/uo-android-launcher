#ifndef MEMENTO_TEST_NATIVE_WINDOW_H
#define MEMENTO_TEST_NATIVE_WINDOW_H
#include <jni.h>
#include <stdint.h>
typedef struct ANativeWindow ANativeWindow;
typedef struct {int32_t left,top,right,bottom;} ARect;
typedef struct {int32_t width,height,stride,format;void *bits;uint32_t reserved[6];} ANativeWindow_Buffer;
#define WINDOW_FORMAT_RGBA_8888 1
ANativeWindow *ANativeWindow_fromSurface(JNIEnv *,jobject);
int32_t ANativeWindow_getWidth(ANativeWindow *);
int32_t ANativeWindow_getHeight(ANativeWindow *);
int32_t ANativeWindow_getFormat(ANativeWindow *);
int32_t ANativeWindow_setBuffersGeometry(ANativeWindow *,int32_t,int32_t,int32_t);
int32_t ANativeWindow_lock(ANativeWindow *,ANativeWindow_Buffer *,ARect *);
int32_t ANativeWindow_unlockAndPost(ANativeWindow *);
void ANativeWindow_release(ANativeWindow *);
#endif
