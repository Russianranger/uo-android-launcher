package io.github.russianranger.trasc;

import java.io.IOException;

/** Keep Android's start watermark within the amount the ALSA producer can queue. */
final class AudioBufferPolicy {
    interface Track {
        int resize(int frames);
        int startThreshold(int frames);
    }
    static int configure(Track track,int producerFrames,boolean hasStartThreshold)throws IOException {
        if(producerFrames<64||producerFrames>48000)throw new IOException("Invalid producer audio capacity");
        int actual=track.resize(producerFrames);
        if(actual<1)throw new IOException("Could not size Android audio buffer: "+actual);
        // API 31+ permits immediate startup even for a partially filled Wine buffer.
        // The larger hardware allocation remains intact; only the write/start limits change.
        int threshold=hasStartThreshold?track.startThreshold(1):actual;
        if(threshold<1||threshold>producerFrames)
            throw new IOException("Android audio start threshold exceeds producer capacity: "+threshold+" > "+producerFrames);
        return actual;
    }
}
