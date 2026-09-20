package io.github.russianranger.trasc;

import java.io.*;
import java.nio.charset.StandardCharsets;

/** Small RFB 3.8 client for the app-private Unix display socket (raw/copy/resize). */
final class RfbConnection {
    interface Screen {
        void resize(int width,int height);
        void pixels(int x,int y,int width,int height,int[] argb);
        void copy(int x,int y,int width,int height,int sourceX,int sourceY);
        void updated();
    }
    final DataInputStream in;
    private final DataOutputStream out;
    private final Screen screen;
    int width,height;
    // Borrowed only during Screen.pixels(); grow to the largest rectangle seen.
    // An 800x600 moving scene no longer allocates another 1.8 MiB per update.
    private int[] pixelBuffer=new int[0];
    private byte[] rowBuffer=new byte[0];
    final ClientFrameStats stats=new ClientFrameStats();
    RfbConnection(InputStream in,OutputStream out,Screen screen) {
        this.in=new DataInputStream(new BufferedInputStream(in,65536));
        this.out=new DataOutputStream(out);this.screen=screen;
    }
    private byte[] bytes(int count)throws IOException {if(count<0||count>1048576)throw new IOException("Display message exceeds limits");byte[] b=new byte[count];in.readFully(b);return b;}
    void handshake()throws IOException {handshake(true);}
    void handshake(boolean frames)throws IOException {
        if(!new String(bytes(12),StandardCharsets.US_ASCII).equals("RFB 003.008\n"))throw new IOException("Unsupported client display protocol");
        synchronized(out){out.write("RFB 003.008\n".getBytes(StandardCharsets.US_ASCII));out.flush();}
        int count=in.readUnsignedByte();if(count==0)throw new IOException("Display refused connection: "+new String(bytes(in.readInt()),StandardCharsets.UTF_8));
        boolean local=false;for(int i=0;i<count;i++)if(in.readUnsignedByte()==1)local=true;
        if(!local)throw new IOException("Unexpected display authentication; use the bundled private socket runtime");
        synchronized(out){out.writeByte(1);out.flush();}
        if(in.readInt()!=0)throw new IOException("Display authentication failed");
        synchronized(out){out.writeByte(1);out.flush();}
        int w=in.readUnsignedShort(),h=in.readUnsignedShort();bytes(16);bytes(in.readInt());resize(w,h);
        synchronized(out) {
            out.writeInt(0); // SetPixelFormat and three padding bytes.
            out.write(new byte[]{32,24,0,1,0,(byte)255,0,(byte)255,0,(byte)255,16,8,0,0,0,0});
            out.writeByte(2);out.writeByte(0);out.writeShort(3);out.writeInt(0);out.writeInt(1);out.writeInt(-223);out.flush();
        }
        if(frames)request(false);
    }
    private void resize(int w,int h)throws IOException {
        if(w<1||h<1||w>4096||h>2160||(long)w*h>4_194_304)throw new IOException("Unsupported client display dimensions");
        width=w;height=h;screen.resize(w,h);
    }
    private void rectangle(int x,int y,int w,int h)throws IOException {
        if(w<1||h<1||x<0||y<0||(long)x+w>width||(long)y+h>height)throw new IOException("Display rectangle is outside the framebuffer");
    }
    void readUpdate()throws IOException {
        int message=in.readUnsignedByte();
        if(message==2)return; // Bell.
        if(message==3){bytes(3);bytes(in.readInt());return;} // No clipboard integration.
        if(message!=0)throw new IOException("Unexpected display message: "+message);
        long started=System.nanoTime(),decode=0,pixelCount=0;
        in.readUnsignedByte();int count=in.readUnsignedShort();
        for(int i=0;i<count;i++) {
            int x=in.readUnsignedShort(),y=in.readUnsignedShort(),w=in.readUnsignedShort(),h=in.readUnsignedShort(),encoding=in.readInt();
            if(encoding==-223){resize(w,h);continue;}
            rectangle(x,y,w,h);
            if(encoding==0) {
                if(pixelBuffer.length<w*h)pixelBuffer=new int[w*h];
                int rows=Math.max(1,65536/(w*4));
                if(rowBuffer.length<rows*w*4)rowBuffer=new byte[rows*w*4];
                for(int iy=0;iy<h;) {
                    int rowCount=Math.min(rows,h-iy),length=rowCount*w;
                    in.readFully(rowBuffer,0,length*4);
                    long convert=System.nanoTime();
                    for(int ix=0;ix<length;ix++){int at=ix*4;pixelBuffer[iy*w+ix]=0xff000000|((rowBuffer[at+2]&255)<<16)|((rowBuffer[at+1]&255)<<8)|(rowBuffer[at]&255);}
                    long cost=System.nanoTime()-convert;decode+=cost;stats.stages(cost,0);iy+=rowCount;
                }
                long apply=System.nanoTime();screen.pixels(x,y,w,h,pixelBuffer);long cost=System.nanoTime()-apply;decode+=cost;stats.stages(0,cost);
                pixelCount+=(long)w*h;
            } else if(encoding==1) {
                int sx=in.readUnsignedShort(),sy=in.readUnsignedShort();rectangle(sx,sy,w,h);
                long apply=System.nanoTime();screen.copy(x,y,w,h,sx,sy);long cost=System.nanoTime()-apply;decode+=cost;stats.stages(0,cost);
            } else throw new IOException("Unsupported display encoding: "+encoding);
        }
        if(count>0){stats.received(System.nanoTime(),System.nanoTime()-started,decode,pixelCount);screen.updated();}
        request(true);
    }
    void request(boolean incremental)throws IOException {
        synchronized(out){out.writeByte(3);out.writeByte(incremental?1:0);out.writeShort(0);out.writeShort(0);out.writeShort(width);out.writeShort(height);out.flush();}
    }
    void key(int keysym,boolean down)throws IOException {
        synchronized(out){out.writeByte(4);out.writeByte(down?1:0);out.writeShort(0);out.writeInt(keysym);out.flush();}
    }
    void pointer(int x,int y,int mask)throws IOException {
        synchronized(out){out.writeByte(5);out.writeByte(mask&31);out.writeShort(Math.max(0,Math.min(width-1,x)));out.writeShort(Math.max(0,Math.min(height-1,y)));out.flush();}
    }
}
