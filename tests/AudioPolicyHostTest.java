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
        AudioBufferPolicy.configure(t,3840,true);
        check(t.buffer==3840&&t.threshold==960,"80 ms ring primes 20 ms before playback");
        AudioBufferPolicy.configure(t,480,true);
        check(t.threshold==480,"Small producers must not deadlock waiting for more frames");
        AudioBufferPolicy.configure(t,3840,false);
        check(t.buffer==3840,"Older Android start watermark stays within producer capacity");
        try{AudioBufferPolicy.configure(t,63,true);throw new AssertionError("Invalid capacity accepted");}catch(IOException expected){}
        try{AudioBufferPolicy.configure(new AudioBufferPolicy.Track(){public int resize(int n){return n*2;}public int startThreshold(int n){return n;}},3840,false);throw new AssertionError("Unreachable watermark accepted");}catch(IOException expected){}
        System.out.println("Audio priming, bounded watermark and older Android checks passed");
    }
}
