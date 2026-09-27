package io.github.russianranger.trasc;

import java.io.IOException;
import java.util.concurrent.locks.ReentrantLock;

/** Shared across Activity recreation; reads remain available during long startup work. */
final class SessionActions {
    private final ReentrantLock lock=new ReentrantLock();
    private volatile boolean cancel;
    volatile boolean busy;
    volatile String status="";

    void begin(String message)throws IOException {
        if(cancel)throw new IOException("Wait for the session to finish closing");
        if(!lock.tryLock())throw new IOException("Finish the current launch or setup task first");
        if(cancel){lock.unlock();throw new IOException("Wait for the session to finish closing");}
        cancel=false;busy=true;status=message;
    }
    void beginShutdown()throws InterruptedException {
        cancel=true;
        lock.lockInterruptibly();
        cancel=false;busy=true;status="Saving and closing the session…";
    }
    void checkCancelled()throws IOException {
        if(cancel)throw new IOException("Launch cancelled. Saving and closing the session…");
    }
    void progress(String message)throws IOException {checkCancelled();status=message;}
    void finish(){busy=false;lock.unlock();}
}
