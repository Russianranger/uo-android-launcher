package io.github.russianranger.trasc;

import android.content.Context;
import android.net.*;
import android.os.ParcelFileDescriptor;
import android.view.*;
import org.json.JSONObject;
import java.io.*;
import java.nio.ByteBuffer;

/** Optional X11 readback -> native Android Surface. No RFB pixel decoder or Bitmap. */
final class NativePresentation extends SurfaceView implements SurfaceHolder.Callback {
    interface Events {void failed(String reason);void size(int width,int height);}
    private static final int CAPACITY=1280*720*4+16;
    private final File path;
    private final Events events;
    private final boolean regionsRequested;
    private volatile boolean regionsActive;
    private volatile LocalSocket socket;
    private volatile Thread worker;
    private Thread lastWorker;
    private volatile boolean closed;
    private long since=System.nanoTime(),frames,unchanged,readNs,captureNs,lockNs,copyNs,postNs,bytes,shmFrames,lastFrame;
    private long regionFrames,fullBytes,redrawnPixels,fullPixels,receiveCalls,expandedFrames,reconfigurations,wireBytes;
    private int width,height;
    NativePresentation(Context context,File path,boolean regionsRequested,Events events){super(context);this.path=path;this.regionsRequested=regionsRequested;this.events=events;getHolder().addCallback(this);}
    private static native int capabilities(int fd);
    private static native int frame(Surface surface,int fd,ByteBuffer pixels,long[] measures,boolean regions);
    private LocalSocket connect()throws IOException {
        LocalSocket local=new LocalSocket();socket=local;
        try{
            if(worker!=Thread.currentThread()||closed)throw new IOException("Surface reader stopped");
            local.connect(new LocalSocketAddress(path.getPath(),LocalSocketAddress.Namespace.FILESYSTEM));local.setSoTimeout(5000);
            return local;
        }catch(IOException failure){local.close();throw failure;}
    }
    @Override public void surfaceCreated(SurfaceHolder holder){start(holder.getSurface());}
    @Override public void surfaceChanged(SurfaceHolder holder,int format,int w,int h){}
    @Override public void surfaceDestroyed(SurfaceHolder holder){stopWorker();}
    private synchronized void start(Surface surface){
        if(closed)return;
        Thread old=lastWorker;
        Thread next=new Thread(()->{
            // Never run two frame readers when Android recreates the Surface.
            if(old!=null)try{old.join(5500);}catch(InterruptedException e){Thread.currentThread().interrupt();return;}
            if(worker!=Thread.currentThread()||closed)return;
            if(old!=null&&old.isAlive()){Thread waiting=Thread.currentThread();post(()->{if(worker==waiting&&!closed)events.failed("Previous Surface reader did not stop");});return;}
            try{
                System.loadLibrary("trasc-presentation");
                regionsActive=false;
                if(regionsRequested){
                    // Older helpers close on an unknown request. Probe on its own
                    // connection, then reconnect using their original full protocol.
                    try(LocalSocket probe=connect();ParcelFileDescriptor fd=ParcelFileDescriptor.dup(probe.getFileDescriptor())){
                        regionsActive=capabilities(fd.getFd())==1;
                    }
                }
                if(worker!=Thread.currentThread()||closed)return;
                try(LocalSocket local=connect()){
                    try(ParcelFileDescriptor fd=ParcelFileDescriptor.dup(local.getFileDescriptor())){
                        ByteBuffer pixels=ByteBuffer.allocateDirect(CAPACITY);long[] times=new long[15];
                        while(worker==Thread.currentThread()&&!closed&&surface.isValid()){
                            int result=frame(surface,fd.getFd(),pixels,times,regionsActive);
                            if(result==1){synchronized(this){unchanged++;}continue;}
                            if(result!=0)throw new IOException("Native frame delivery failed ("+result+")");
                            synchronized(this){
                                frames++;width=(int)times[0];height=(int)times[1];captureNs+=times[2];readNs+=times[3];lockNs+=times[4];copyNs+=times[5];postNs+=times[6];bytes+=times[7];
                                shmFrames+=(times[8]&1)!=0?1:0;regionFrames+=(times[8]&4)!=0?1:0;
                                redrawnPixels+=times[9];fullPixels+=times[10];fullBytes+=times[10]*4;receiveCalls+=times[11];expandedFrames+=times[12];reconfigurations+=times[13];wireBytes+=times[14];lastFrame=System.nanoTime();
                            }
                            final int w=(int)times[0],h=(int)times[1];if(w!=reportedWidth||h!=reportedHeight){reportedWidth=w;reportedHeight=h;post(()->events.size(w,h));}
                        }
                    }
                }
            }catch(Exception|UnsatisfiedLinkError failure){if(worker==Thread.currentThread()&&!closed){Thread failed=Thread.currentThread();post(()->{if(worker==failed&&!closed)events.failed(failure.getMessage());});}}
        },"TRASC native Surface");worker=next;lastWorker=next;next.start();
    }
    private int reportedWidth,reportedHeight;
    private synchronized void stopWorker(){worker=null;LocalSocket local=socket;socket=null;if(local!=null)try{local.shutdownInput();local.shutdownOutput();local.close();}catch(IOException ignored){}}
    void close(){closed=true;stopWorker();}
    synchronized JSONObject sample(long now)throws org.json.JSONException {
        double seconds=(now-since)/1e9;if(seconds<=0)return new JSONObject();
        JSONObject result=new JSONObject().put("window_seconds",seconds).put("surface_posts_per_second",frames/seconds)
            .put("dirty_regions_requested",regionsRequested).put("dirty_regions_active",regionsActive).put("transport",regionsActive?"regions-v3":"batched-v2")
            .put("capture_ms_per_frame",frames==0?0:captureNs/1e6/frames).put("request_receive_ms_per_frame",frames==0?0:readNs/1e6/frames)
            .put("surface_lock_ms_per_frame",frames==0?0:lockNs/1e6/frames).put("native_copy_ms_per_frame",frames==0?0:copyNs/1e6/frames)
            .put("surface_post_ms_per_frame",frames==0?0:postNs/1e6/frames).put("bytes_per_second",bytes/seconds)
            .put("unchanged_responses",unchanged).put("shm_frames",shmFrames).put("frames",frames).put("frame_width",width).put("frame_height",height)
            .put("region_frames",regionFrames).put("full_frames",frames-regionFrames).put("pixel_bytes",bytes).put("full_frame_bytes",fullBytes).put("pixel_bytes_saved",fullBytes-bytes)
            .put("delivered_pixel_fraction",fullBytes==0?0:(double)bytes/fullBytes).put("surface_redraw_fraction",fullPixels==0?0:(double)redrawnPixels/fullPixels)
            .put("surface_expanded_frames",expandedFrames).put("receive_calls_per_frame",frames==0?0:(double)receiveCalls/frames).put("wire_bytes_per_second",wireBytes/seconds).put("buffer_reconfigurations",reconfigurations)
            .put("last_update_age_seconds",lastFrame==0?-1:Math.max(0,now-lastFrame)/1e9);
        since=now;frames=unchanged=readNs=captureNs=lockNs=copyNs=postNs=bytes=shmFrames=0;
        regionFrames=fullBytes=redrawnPixels=fullPixels=receiveCalls=expandedFrames=reconfigurations=wireBytes=0;return result;
    }
}
