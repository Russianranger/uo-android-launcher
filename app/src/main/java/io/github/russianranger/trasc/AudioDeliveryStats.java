package io.github.russianranger.trasc;

/** Interval counters only: no sample copying, timers, or per-write logging. */
final class AudioDeliveryStats {
    private boolean playing;
    private long lastDelivery;
    long writes,zeroWrites,partialWrites,maxWriteNs,maxGapNs,gapsOver40ms,gapsOver80ms;
    long maxCommandWaitNs,maxPcmReadNs,maxReplyNs,commandWaitsOver40ms;
    void playing(boolean value){playing=value;lastDelivery=0;}
    void transport(int stage,long nanos){
        if(!playing)return;
        nanos=Math.max(0,nanos);
        if(stage==1){maxCommandWaitNs=Math.max(maxCommandWaitNs,nanos);if(nanos>40000000L)commandWaitsOver40ms++;}
        else if(stage==2)maxPcmReadNs=Math.max(maxPcmReadNs,nanos);
        else if(stage==3)maxReplyNs=Math.max(maxReplyNs,nanos);
    }
    void write(long began,long ended,int requested,int accepted){
        writes++;maxWriteNs=Math.max(maxWriteNs,Math.max(0,ended-began));
        if(accepted==0)zeroWrites++;
        if(accepted>0&&accepted<requested)partialWrites++;
        if(accepted>0&&playing){
            if(lastDelivery!=0){
                long gap=Math.max(0,ended-lastDelivery);maxGapNs=Math.max(maxGapNs,gap);
                if(gap>40000000L)gapsOver40ms++;
                if(gap>80000000L)gapsOver80ms++;
            }
            lastDelivery=ended;
        }
    }
    String take(){
        String result=" write_calls="+writes+" zero_writes="+zeroWrites+" partial_writes="+partialWrites+
            " max_write_us="+maxWriteNs/1000+" max_delivery_gap_us="+maxGapNs/1000+
            " gaps_over_40ms="+gapsOver40ms+" gaps_over_80ms="+gapsOver80ms+
            " max_command_wait_us="+maxCommandWaitNs/1000+" max_pcm_read_us="+maxPcmReadNs/1000+
            " max_reply_us="+maxReplyNs/1000+" command_waits_over_40ms="+commandWaitsOver40ms;
        writes=zeroWrites=partialWrites=maxWriteNs=maxGapNs=gapsOver40ms=gapsOver80ms=0;
        maxCommandWaitNs=maxPcmReadNs=maxReplyNs=commandWaitsOver40ms=0;
        return result;
    }
}
