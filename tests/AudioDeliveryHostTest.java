package io.github.russianranger.trasc;
import java.io.*;
import java.util.*;

public final class AudioDeliveryHostTest {
    static void check(boolean ok,String text){if(!ok)throw new AssertionError(text);}
    static final class Sink implements AudioPcmSession.Sink {
        int calls,commands,pcmReads,replies;boolean closed;byte[] received;
        public void configure(int n){check(n==1920,"Producer capacity changed");}
        public void start(){}public void stop(){}public void reset(){}public int position(){return 1;}
        public int write(byte[] bytes,int length){received=Arrays.copyOf(bytes,length);return ++calls==1?4:0;}
        public void close(){closed=true;}
        public void transport(int stage,long nanos){check(nanos>=0,"Monotonic transport duration");if(stage==1)commands++;if(stage==2)pcmReads++;if(stage==3)replies++;}
    }
    static void put(DataOutputStream out,int n)throws IOException{out.writeInt(Integer.reverseBytes(n));}
    public static void main(String[] args)throws Exception{
        AudioDeliveryStats stats=new AudioDeliveryStats();stats.playing(true);
        stats.write(1000000,2000000,8,4);stats.write(52000000,53000000,8,0);
        stats.write(92000000,93000000,8,8);
        check(stats.partialWrites==1&&stats.zeroWrites==1,"Backpressure accounting");
        check(stats.maxGapNs==91000000&&stats.gapsOver40ms==1&&stats.gapsOver80ms==1,"Accepted-delivery gaps");
        check(stats.maxWriteNs==1000000,"Write duration");stats.take();
        stats.write(102000000,103000000,8,8);
        check(stats.maxGapNs==10000000&&stats.writes==1,"Report retains last delivery and resets counters");
        stats.playing(false);stats.write(900000000,901000000,8,8);stats.playing(true);stats.take();
        stats.write(999000000,1000000000,8,8);
        check(stats.maxGapNs==0,"Pause/start must not count idle time as starvation");
        stats.transport(1,45000000);stats.transport(2,2500000);stats.transport(3,1100000);
        check(stats.maxCommandWaitNs==45000000&&stats.commandWaitsOver40ms==1&&stats.maxPcmReadNs==2500000&&stats.maxReplyNs==1100000,"Separate protocol waits");
        check(stats.take().contains("max_command_wait_us=45000")&&stats.maxCommandWaitNs==0,"Transport report/reset");
        stats.playing(false);stats.transport(1,1000000000);check(stats.maxCommandWaitNs==0,"Paused command waits excluded");
        stats.queue(0);check(stats.queueSamples==0,"Paused queue samples excluded");
        stats.playing(true);for(long n:new long[]{960,479,0,-1,480})stats.queue(n);
        check(stats.queueSamples==5&&stats.emptyQueueSamples==2&&stats.lowQueueSamples==3,"Queue safety margin samples");
        check(stats.minQueuedFrames==0&&stats.maxQueuedFrames==960,"Queue min/max clamps stale heads");
        check(stats.underruns(4)==4&&stats.underruns(7)==3,"Cumulative underruns become interval deltas");
        String queue=stats.take();check(queue.contains("min_queued_frames=0")&&queue.contains("below_10ms_samples=3"),"Queue summary");
        check(stats.take().contains("min_queued_frames=-1"),"No samples distinguished from an empty queue");
        check(stats.underruns(8)==1,"Report reset retains underrun baseline");
        stats.resetTrack();check(stats.underruns(2)==2,"New track resets underrun baseline");
        check(stats.underruns(0)==0,"Counter reset cannot produce a negative delta");
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();DataOutputStream out=new DataOutputStream(bytes);
        for(int n:new int[]{0x50414c54,1,48000,2,1920,1,4,2})put(out,n);
        byte[] pcm={1,0,2,0,3,0,4,0};out.write(pcm);put(out,4);put(out,2);out.write(pcm);put(out,3);
        InputStream shortReads=new ByteArrayInputStream(bytes.toByteArray()){
            public synchronized int read(byte[] b,int o,int n){return super.read(b,o,Math.min(n,1));}
        };
        Sink sink=new Sink();AudioPcmSession session=new AudioPcmSession();ByteArrayOutputStream reply=new ByteArrayOutputStream();
        session.run(shortReads,reply,sink);
        check(sink.closed&&session.frames==1&&Arrays.equals(sink.received,pcm),"PCM/partial acceptance/EOF");
        check(sink.commands==4&&sink.pcmReads==2&&sink.replies==5,"All protocol boundaries observed without changing replies");
        DataInputStream response=new DataInputStream(new ByteArrayInputStream(reply.toByteArray()));
        for(int expected:new int[]{0,0,1,0,1})check(Integer.reverseBytes(response.readInt())==expected,"Protocol replies");
        System.out.println("PCM exact bytes, partial writes, short reads and delivery-gap counters passed");
    }
}
