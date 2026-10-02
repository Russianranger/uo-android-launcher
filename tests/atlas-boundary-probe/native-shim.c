/* Exact native signatures for the checksum-pinned FNA fixture. This shim
 * records arguments and a small texture image; it implements no graphics.
 * Run against a fresh process so the actual managed P/Invokes are exercised. */
#include <stdint.h>
#include <string.h>
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif
static int count;
static int ids[8192];
static uint64_t args[8192][12];
static uint32_t pixels[16][64*64];
static int nargs[8192];
#define V(p) ((uint64_t)(uintptr_t)(p))
#define REC(id, ...) do { uint64_t a[]={__VA_ARGS__}; int n=(int)(sizeof(a)/sizeof(a[0])); if(count<8192){ids[count]=id;nargs[count]=n;memcpy(args[count],a,sizeof(a));count++;} } while(0)
static uint32_t fb(float x){uint32_t n;memcpy(&n,&x,4);return n;}
EXPORT void TestReset(void){count=0;}
EXPORT int TestCount(void){return count;}
EXPORT int TestId(int e){return ids[e];}
EXPORT uint64_t TestArg(int e,int a){return args[e][a];}
EXPORT uint32_t TestPixel(int t,int x,int y){return pixels[t][y*64+x];}
EXPORT void TestClearPixels(void){memset(pixels,0,sizeof(pixels));}
EXPORT void FNA3D_DrawIndexedPrimitives(void*d,int p,int b,int m,int n,int s,int c,void*i,int z){REC(1,V(d),p,b,m,n,s,c,V(i),z);}
EXPORT void FNA3D_DrawInstancedPrimitives(void*d,int p,int b,int m,int n,int s,int c,int q,void*i,int z){REC(2,V(d),p,b,m,n,s,c,q,V(i),z);}
EXPORT void FNA3D_DrawPrimitives(void*d,int p,int s,int c){REC(3,V(d),p,s,c);}
EXPORT void FNA3D_SetTextureData2D(void*d,void*t,int x,int y,int w,int h,int l,void*p,int n){
 REC(4,V(d),V(t),x,y,w,h,l,V(p),n);
 uintptr_t k=(uintptr_t)t-0x5000;
 if(k<16 && x>=0&&y>=0&&w>=0&&h>=0&&x+w<=64&&y+h<=64&&l==0&&n>=w*h*4&&p)
  for(int row=0;row<h;row++)memcpy(&pixels[k][(y+row)*64+x],(char*)p+row*w*4,w*4);
}
EXPORT void FNA3D_SetTextureData3D(void*d,void*t,int x,int y,int z,int w,int h,int q,int l,void*p,int n){REC(5,V(d),V(t),x,y,z,w,h,q,l,V(p),n);}
EXPORT void FNA3D_SetTextureDataCube(void*d,void*t,int x,int y,int w,int h,int f,int l,void*p,int n){REC(6,V(d),V(t),x,y,w,h,f,l,V(p),n);}
EXPORT void FNA3D_SetTextureDataYUV(void*d,void*y,void*u,void*v,int w,int h,int q,int r,void*p,int n){REC(7,V(d),V(y),V(u),V(v),w,h,q,r,V(p),n);}
EXPORT void FNA3D_GetTextureData2D(void*d,void*t,int x,int y,int w,int h,int l,void*p,int n){REC(8,V(d),V(t),x,y,w,h,l,V(p),n);}
EXPORT void FNA3D_GetTextureData3D(void*d,void*t,int x,int y,int z,int w,int h,int q,int l,void*p,int n){REC(9,V(d),V(t),x,y,z,w,h,q,l,V(p),n);}
EXPORT void FNA3D_GetTextureDataCube(void*d,void*t,int x,int y,int w,int h,int f,int l,void*p,int n){REC(10,V(d),V(t),x,y,w,h,f,l,V(p),n);}
EXPORT void FNA3D_ReadBackbuffer(void*d,int x,int y,int w,int h,void*p,int n){REC(11,V(d),x,y,w,h,V(p),n);}
EXPORT void FNA3D_ResolveTarget(void*d,int*r){REC(12,V(d),(uint32_t)*r);*r=24680;}
EXPORT void FNA3D_ResetBackbuffer(void*d,int*r){REC(13,V(d),(uint32_t)*r);*r=24680;}
/* Four managed overloads map to this one ABI. Ref rectangles are exercised
 * through real managed storage, pointer overloads retain their exact value. */
static uint64_t swaparg(void*p){if((uintptr_t)p>0x20000){uint64_t v=(uint32_t)*(int*)p;*(int*)p=24680;return v;}return V(p);}
EXPORT void FNA3D_SwapBuffers(void*d,void*s,void*t,void*w){uint64_t source=swaparg(s),destination=swaparg(t);REC(14,V(d),source,destination,V(w));}
EXPORT void FNA3D_AddDisposeTexture(void*d,void*t){REC(15,V(d),V(t));}
EXPORT void FNA3D_SetRenderTargets(void*d,void*r,int n,void*b,int f,uint8_t p){REC(16,V(d),V(r),n,V(b),f,p);}
EXPORT void FNA3D_Clear(void*d,int o,int*c,float z,int s){REC(17,V(d),o,(uint32_t)*c,fb(z),s);*c=24680;}
EXPORT void FNA3D_DestroyDevice(void*d){REC(18,V(d));}
EXPORT void FNA3D_GetVertexBufferData(void*d,void*b,int o,void*p,int n,int s,int z){REC(19,V(d),V(b),o,V(p),n,s,z);}
#ifndef OMIT_TEST_ENTRY
EXPORT void FNA3D_GetIndexBufferData(void*d,void*b,int o,void*p,int n){REC(20,V(d),V(b),o,V(p),n);}
#endif
EXPORT void FNA3D_SetVertexBufferData(void*d,void*b,int o,void*p,int n,int s,int z,int q){REC(21,V(d),V(b),o,V(p),n,s,z,q);}
EXPORT void FNA3D_SetIndexBufferData(void*d,void*b,int o,void*p,int n,int q){REC(22,V(d),V(b),o,V(p),n,q);}
