package io.github.russianranger.trasc;
import java.io.*;

public final class AudioPolicyHostTest {
    static void check(boolean ok,String text){if(!ok)throw new AssertionError(text);}
    static final class Track implements AudioBufferPolicy.Track {
        int buffer,threshold;
        public int resize(int frames){return buffer=frames;}
        public int startThreshold(int frames){return threshold=frames;}
    }
    public static void main(String[] args)throws Exception {
        Track t=new Track();
        AudioBufferPolicy.configure(t,1920,true);
        check(t.buffer==1920&&t.threshold==1,"40 ms ring delegates priming to Wine");
        AudioBufferPolicy.configure(t,480,true);
        check(t.threshold==1,"Short sounds can drain without reaching a second watermark");
        AudioBufferPolicy.configure(t,1920,false);
        check(t.buffer==1920,"Older Android start watermark stays within producer capacity");
        try{AudioBufferPolicy.configure(t,63,true);throw new AssertionError("Invalid capacity accepted");}catch(IOException expected){}
        try{AudioBufferPolicy.configure(new AudioBufferPolicy.Track(){public int resize(int n){return n*2;}public int startThreshold(int n){return n;}},1920,false);throw new AssertionError("Unreachable watermark accepted");}catch(IOException expected){}
        System.out.println("Audio start, bounded watermark and older Android checks passed");
    }
}
