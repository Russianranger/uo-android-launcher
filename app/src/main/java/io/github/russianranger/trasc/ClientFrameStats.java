package io.github.russianranger.trasc;

/** Transport/display counters. Neither redraws nor RFB updates measure game FPS. */
final class ClientFrameStats {
    private long since,updates,draws,receiveNs,decodeNs,drawNs,pixels;
    private long conversionNs,applyNs;
    synchronized void stages(long conversion,long apply){conversionNs+=conversion;applyNs+=apply;}
    private long generation,drawnGeneration,lastReceived;
    ClientFrameStats(){this(System.nanoTime());}
    ClientFrameStats(long now){since=now;}
    synchronized void received(long now,long receive,long decode,long rawPixels){
        updates++;generation++;lastReceived=now;receiveNs+=receive;decodeNs+=decode;pixels+=rawPixels;
    }
    synchronized void drawn(long nanos){
        // UI invalidation/focus changes may redraw the same bitmap. Count once.
        if(drawnGeneration!=generation){draws++;drawNs+=nanos;drawnGeneration=generation;}
    }
    synchronized double[] sample(long now){
        double seconds=(now-since)/1e9;
        if(seconds<=0)return null;
        double[] result={seconds,updates/seconds,draws/seconds,
            updates==0?0:receiveNs/1e6/updates,updates==0?0:decodeNs/1e6/updates,
            draws==0?0:drawNs/1e6/draws,pixels/seconds,
            lastReceived==0?-1:(now-lastReceived)/1e9,
            updates==0?0:conversionNs/1e6/updates,updates==0?0:applyNs/1e6/updates,pixels*4/seconds};
        since=now;updates=draws=receiveNs=decodeNs=drawNs=pixels=conversionNs=applyNs=0;return result;
    }
}
