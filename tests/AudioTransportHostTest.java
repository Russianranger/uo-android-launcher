package io.github.russianranger.trasc;

import java.io.*;
import java.net.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicReference;

/** Exact protocol equivalence and real request/reply socket progress. */
public final class AudioTransportHostTest {
    static void check(boolean ok,String text){if(!ok)throw new AssertionError(text);}
    static void word(DataOutputStream out,int n)throws IOException{out.writeInt(Integer.reverseBytes(n));}
    static int word(DataInputStream in)throws IOException{return Integer.reverseBytes(in.readInt());}
    static void header(DataOutputStream out)throws IOException{for(int n:new int[]{0x50414c54,1,48000,2,1920})word(out,n);}
    static final class Sink implements AudioPcmSession.Sink {
        final ByteArrayOutputStream accepted=new ByteArrayOutputStream();
        final StringBuilder events=new StringBuilder();
        final boolean partial;
        int writes;boolean closed;
        Sink(boolean partial){this.partial=partial;}
        public void configure(int frames){check(frames==1920,"Capacity changed");events.append('C');}
        public void start(){events.append('S');}public void stop(){events.append('T');}public void reset(){events.append('R');}
        public int position(){events.append('P');return accepted.size()/4;}
        public int write(byte[] data,int length){
            int n=partial?(writes++%3==0?0:Math.min(length,148)):length;
            accepted.write(data,0,n);events.append('W');return n;
        }
        public void close(){closed=true;}
    }
    static final class Result {
        final Sink sink;final AudioPcmSession session=new AudioPcmSession();final ByteArrayOutputStream replies=new ByteArrayOutputStream();
        Result(byte[] data,boolean buffered,int fragment,boolean partial)throws IOException{
            sink=new Sink(partial);
            InputStream input=new ByteArrayInputStream(data){
                public synchronized int read(byte[] b,int off,int len){return super.read(b,off,Math.min(len,fragment));}
            };
            session.run(input,replies,sink,buffered);
        }
    }
    static void equivalence()throws Exception {
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();DataOutputStream out=new DataOutputStream(bytes);header(out);word(out,1);
        for(int count:new int[]{1,37,480,4096,37,480}){
            word(out,4);word(out,count);
            for(int i=0;i<count*4;i++)out.writeByte(i*31);
            word(out,3);
        }
        word(out,2);word(out,5);word(out,1);word(out,3);
        for(int fragment:new int[]{1,3,7,1928,Integer.MAX_VALUE}){
            Result plain=new Result(bytes.toByteArray(),false,fragment,true),buffered=new Result(bytes.toByteArray(),true,fragment,true);
            check(Arrays.equals(plain.replies.toByteArray(),buffered.replies.toByteArray()),"Replies changed");
            check(Arrays.equals(plain.sink.accepted.toByteArray(),buffered.sink.accepted.toByteArray()),"PCM changed");
            check(plain.sink.events.toString().equals(buffered.sink.events.toString()),"Lifecycle order changed");
            check(plain.session.frames==buffered.session.frames&&plain.sink.closed&&buffered.sink.closed,"Frame accounting/EOF cleanup");
            check(buffered.session.inputBytes==bytes.size(),"Socket-byte accounting");
            if(fragment==Integer.MAX_VALUE){
                check(buffered.session.inputReadCalls<plain.session.inputReadCalls/4,"Coalesced reads did not reduce underlying calls");
                System.out.println("Coalesced fixture input reads: baseline="+plain.session.inputReadCalls+" buffered="+buffered.session.inputReadCalls);
            }
        }
    }
    static void invalidFrames()throws Exception{
        for(boolean buffered:new boolean[]{false,true})for(int size:new int[]{0,-1,4097,8}){
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();DataOutputStream out=new DataOutputStream(bytes);header(out);word(out,4);word(out,size);
            if(size==8)out.write(new byte[7]); // Incomplete body must never reach the sink.
            Sink sink=new Sink(false);
            try{new AudioPcmSession().run(new ByteArrayInputStream(bytes.toByteArray()),new ByteArrayOutputStream(),sink,buffered);throw new AssertionError("Invalid payload accepted");}
            catch(IOException expected){}
            check(sink.closed&&sink.accepted.size()==0,"Failed body cleanup/atomic delivery");
        }
    }
    static void roundTrip(boolean buffered)throws Exception{
        // The producer waits for every reply and sends less than the input
        // buffer. Filling a buffer before replying would deadlock this test.
        try(ServerSocket server=new ServerSocket(0,1,InetAddress.getLoopbackAddress())){
            AtomicReference<Throwable> failure=new AtomicReference<>();Sink sink=new Sink(false);
            Thread worker=new Thread(()->{
                try(Socket connection=server.accept()){
                    connection.setSoTimeout(2000);
                    new AudioPcmSession().run(connection.getInputStream(),connection.getOutputStream(),sink,buffered);
                }catch(Throwable error){failure.set(error);}
            });worker.setDaemon(true);worker.start();
            try(Socket client=new Socket(InetAddress.getLoopbackAddress(),server.getLocalPort())){
                client.setSoTimeout(2000);
                DataOutputStream out=new DataOutputStream(client.getOutputStream());DataInputStream in=new DataInputStream(client.getInputStream());
                header(out);out.flush();check(word(in)==0,"Header reply blocked");
                word(out,1);out.flush();check(word(in)==0,"Start reply blocked");
                word(out,4);word(out,37);out.flush(); // Header arrives separately from PCM.
                byte[] pcm=new byte[148];for(int i=0;i<pcm.length;i++)pcm[i]=(byte)(i*17);
                out.write(pcm);out.flush();check(word(in)==37,"Short sound waits for a full buffer");
                word(out,3);out.flush();check(word(in)==37,"Playback clock reply changed");
                check(Arrays.equals(pcm,sink.accepted.toByteArray()),"Duplex PCM changed");
                word(out,2);out.flush();check(word(in)==0,"Stop reply blocked");
                word(out,5);out.flush();check(word(in)==0,"Reset reply blocked");
                client.shutdownOutput();
            }
            worker.join(3000);check(!worker.isAlive(),"Socket EOF failed to release worker");
            if(failure.get()!=null)throw new AssertionError("Socket protocol failure",failure.get());
            check(sink.closed,"Socket sink not released");
        }
    }
    public static void main(String[] args)throws Exception{
        equivalence();invalidFrames();roundTrip(false);roundTrip(true);
        System.out.println("Buffered/unbuffered PCM, partial acceptance, fragmentation, short sounds, reset, EOF and duplex replies passed");
    }
}
