package io.github.russianranger.trasc;

/** Interval counters only: no sample copying, timers, or per-write logging. */
final class AudioDeliveryStats {
    private boolean playing;
    private long lastDelivery;
    long writes,zeroWrites,partialWrites,maxWriteNs,maxGapNs,gapsOver40ms,gapsOver80ms;
    void playing(boolean value){playing=value;lastDelivery=0;}
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
            " gaps_over_40ms="+gapsOver40ms+" gaps_over_80ms="+gapsOver80ms;
        writes=zeroWrites=partialWrites=maxWriteNs=maxGapNs=gapsOver40ms=gapsOver80ms=0;
        return result;
    }
}
