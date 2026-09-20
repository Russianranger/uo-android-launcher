"""Verify a mapped GLX drawable, its real driver and a rendered pixel.

Mesa's virpipe front-buffer read can raise X_GetImage BadMatch on glxinfo's
unmapped window. Use the same mapped-window path as Wine instead.
"""
import ctypes as C
import struct


def main():
    ptr=C.c_void_p; integer=C.c_int; ulong=C.c_ulong
    class VisualInfo(C.Structure):
        _fields_=[('visual',ptr),('visualid',ulong),('screen',integer),('depth',integer),
                  ('visual_class',integer),('red_mask',ulong),('green_mask',ulong),
                  ('blue_mask',ulong),('colormap_size',integer),('bits_per_rgb',integer)]
    class Attributes(C.Structure):
        _fields_=[('background_pixmap',ulong),('background_pixel',ulong),('border_pixmap',ulong),
                  ('border_pixel',ulong),('bit_gravity',integer),('win_gravity',integer),
                  ('backing_store',integer),('backing_planes',ulong),('backing_pixel',ulong),
                  ('save_under',integer),('event_mask',C.c_long),('do_not_propagate_mask',C.c_long),
                  ('override_redirect',integer),('colormap',ulong),('cursor',ulong)]
    x=C.CDLL('libX11.so.6'); gl=C.CDLL('libGL.so.1')
    def bind(lib,name,result,args):
        f=getattr(lib,name);f.restype=result;f.argtypes=args;return f
    open_display=bind(x,'XOpenDisplay',ptr,[C.c_char_p])
    root_window=bind(x,'XRootWindow',ulong,[ptr,integer])
    choose=bind(gl,'glXChooseVisual',C.POINTER(VisualInfo),[ptr,integer,C.POINTER(integer)])
    create_map=bind(x,'XCreateColormap',ulong,[ptr,ulong,ptr,integer])
    create_window=bind(x,'XCreateWindow',ulong,[ptr,ulong,integer,integer,C.c_uint,C.c_uint,C.c_uint,integer,C.c_uint,ptr,ulong,C.POINTER(Attributes)])
    map_window=bind(x,'XMapWindow',integer,[ptr,ulong])
    sync=bind(x,'XSync',integer,[ptr,integer])
    create_context=bind(gl,'glXCreateContext',ptr,[ptr,C.POINTER(VisualInfo),ptr,integer])
    make_current=bind(gl,'glXMakeCurrent',integer,[ptr,ulong,ptr])
    get_string=bind(gl,'glGetString',C.c_char_p,[C.c_uint])
    clear_color=bind(gl,'glClearColor',None,[C.c_float]*4)
    clear=bind(gl,'glClear',None,[C.c_uint])
    read=bind(gl,'glReadPixels',None,[integer,integer,integer,integer,C.c_uint,C.c_uint,ptr])
    error=bind(gl,'glGetError',C.c_uint,[])
    swap=bind(gl,'glXSwapBuffers',None,[ptr,ulong])
    display=open_display(None)
    if not display: raise RuntimeError('Cannot open private X display')
    # A double-buffered RGB drawable, matching the WineD3D window path.
    visual=choose(display,0,(integer*10)(4,5,8,8,9,8,10,8,0,0))
    if not visual: raise RuntimeError('No RGB GLX visual')
    root=root_window(display,visual.contents.screen)
    attributes=Attributes();attributes.colormap=create_map(display,root,visual.contents.visual,0)
    attributes.override_redirect=1
    window=create_window(display,root,0,0,32,32,0,visual.contents.depth,1,visual.contents.visual,
                         (1<<13)|(1<<9),C.byref(attributes))
    map_window(display,window);sync(display,0)
    context=create_context(display,visual,None,1)
    if not context or not make_current(display,window,context): raise RuntimeError('GLX context creation failed')
    for label,key in [('vendor',0x1F00),('renderer',0x1F01),('version',0x1F02)]:
        value=get_string(key)
        if not value: raise RuntimeError('Missing OpenGL '+label)
        print('OpenGL '+label+' string: '+value.decode(errors='replace'),flush=True)
    clear_color(1,0,0,1);clear(0x4000)
    pixel=(C.c_ubyte*4)();read(0,0,1,1,0x1908,0x1401,pixel)
    gl_error=error()
    if gl_error or list(pixel)[:3]!=[255,0,0]:
        raise RuntimeError(f'GLX render/readback failed: error={gl_error}, pixel={list(pixel)}')
    verify_textures(gl, bind, read, error)
    swap(display,window);sync(display,0)
    print('PASS: mapped GLX drawable rendered and read back the expected pixel',flush=True)
    make_current(display,0,None)
    bind(gl,'glXDestroyContext',None,[ptr,ptr])(display,context)
    bind(x,'XDestroyWindow',integer,[ptr,ulong])(display,window)
    bind(x,'XFreeColormap',integer,[ptr,ulong])(display,attributes.colormap)
    bind(x,'XFree',integer,[ptr])(visual)
    bind(x,'XCloseDisplay',integer,[ptr])(display)


def verify_textures(gl, bind, read, error):
    """Sample real BC textures, including mip/subrect updates and alpha.

    The old GLES bridge passed clear/readback yet corrupted these operations.
    Use GLSL 1.20-compatible fixed function draws; no inflated version override.
    """
    u=C.c_uint; i=C.c_int; p=C.c_void_p; f=C.c_float
    enable=bind(gl,'glEnable',None,[u]);disable=bind(gl,'glDisable',None,[u])
    gen=bind(gl,'glGenTextures',None,[i,C.POINTER(u)])
    delete=bind(gl,'glDeleteTextures',None,[i,C.POINTER(u)])
    texture=bind(gl,'glBindTexture',None,[u,u])
    param=bind(gl,'glTexParameteri',None,[u,u,i])
    texenv=bind(gl,'glTexEnvi',None,[u,u,i])
    upload=bind(gl,'glCompressedTexImage2D',None,[u,i,u,i,i,i,i,p])
    sub=bind(gl,'glCompressedTexSubImage2D',None,[u,i,i,i,i,i,u,i,p])
    begin=bind(gl,'glBegin',None,[u]);end=bind(gl,'glEnd',None,[])
    uv=bind(gl,'glTexCoord2f',None,[f,f]);vertex=bind(gl,'glVertex2f',None,[f,f])
    clear=bind(gl,'glClear',None,[u]);cc=bind(gl,'glClearColor',None,[f]*4)
    blend=bind(gl,'glBlendFunc',None,[u,u])
    disable(0x0BD0) # dither
    enable(0x0DE1);texenv(0x2300,0x2200,0x1E01) # texture replace
    def block(kind, color, alpha=255):
        color_block=struct.pack('<HHI',color,0,0)
        if kind in (1,2):return color_block
        if kind==3:return bytes([((alpha//17)<<4)|(alpha//17)])*8+color_block
        return bytes([alpha,0])+bytes(6)+color_block
    def draw():
        cc(1,1,1,1);clear(0x4000);begin(7)
        for a,b,x,y in [(0,0,-1,-1),(1,0,1,-1),(1,1,1,1),(0,1,-1,1)]:uv(a,b);vertex(x,y)
        end()
    def check(label,x,y,expected):
        pixel=(C.c_ubyte*4)();read(x,y,1,1,0x1908,0x1401,pixel)
        e=error()
        if e or any(abs(pixel[k]-expected[k])>3 for k in range(3)):
            raise RuntimeError(f'Texture check {label} failed: GL={e:#x}, RGB={list(pixel)[:3]}, expected={expected}. Try Software graphics and export logs.')
    for fmt,kind in [(0x83F0,1),(0x83F1,2),(0x83F2,3),(0x83F3,5),
                     (0x8C4C,1),(0x8C4D,2),(0x8C4E,3),(0x8C4F,5)]:
        tex=u();gen(1,C.byref(tex));texture(0x0DE1,tex)
        try:
            param(0x0DE1,0x2801,0x2600);param(0x0DE1,0x2800,0x2600)
            param(0x0DE1,0x813D,3)
            for level,w in enumerate((8,4,2,1)):
                data=block(kind,0xF800 if level==0 else 0x001F)*(((w+3)//4)**2)
                upload(0x0DE1,level,fmt,w,w,0,len(data),data)
            draw();check(f'{fmt:#x} base',8,8,[255,0,0])
            data=block(kind,0x07E0);sub(0x0DE1,0,4,0,4,4,fmt,len(data),data)
            draw();check(f'{fmt:#x} preserved area',8,8,[255,0,0]);check(f'{fmt:#x} subrectangle',24,8,[0,255,0])
            for level in (1,2,3):
                param(0x0DE1,0x813C,level);param(0x0DE1,0x813D,level)
                draw();check(f'{fmt:#x} mip {level}',16,16,[0,0,255])
            param(0x0DE1,0x813C,0);param(0x0DE1,0x813D,3)
            data=block(kind,0x8410)*4;sub(0x0DE1,0,0,0,8,8,fmt,len(data),data)
            draw();check(f'{fmt:#x} color space',16,16,[59,57,59] if fmt>=0x8C00 else [132,130,132])
            # Alpha is observed by compositing over white, independent of X visual alpha depth.
            if kind in (3,5):
                a=136 if kind==3 else 128;data=block(kind,0xF800,a)*4
                sub(0x0DE1,0,0,0,8,8,fmt,len(data),data)
                enable(0x0BE2);blend(0x0302,0x0303)
                draw();check(f'{fmt:#x} alpha',16,16,[255,255-a,255-a]);disable(0x0BE2)
            print(f'PASS: texture {fmt:#x} upload, subrectangle, mipmaps, color and alpha',flush=True)
        finally:delete(1,C.byref(tex))
    disable(0x0DE1)


if __name__=='__main__': main()
