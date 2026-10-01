package io.github.russianranger.trasc;

import java.io.IOException;
import java.util.concurrent.locks.ReentrantLock;
import java.util.concurrent.atomic.AtomicBoolean;

/** Shared across Activity recreation; reads remain available during long startup work. */
final class SessionActions {
    private final ReentrantLock lock=new ReentrantLock();
    private volatile boolean cancel;
    private final AtomicBoolean closing=new AtomicBoolean();
    private boolean shutdownOwner;
    volatile boolean busy;
    volatile boolean cancellable;
    private volatile long startedNanos;
    volatile String status="";

    void begin(String message)throws IOException {
        if(closing.get())throw new IOException("Wait for the session to finish closing");
        if(!lock.tryLock())throw new IOException("Finish the current launch or setup task first");
        if(closing.get()){lock.unlock();throw new IOException("Wait for the session to finish closing");}
        cancel=false;busy=true;status=message;startedNanos=System.nanoTime();
    }
    void beginShutdown()throws InterruptedException,IOException {
        if(!closing.compareAndSet(false,true))throw new IOException("The session is already closing");
        cancel=true;
        try{lock.lockInterruptibly();}catch(InterruptedException error){cancel=false;closing.set(false);throw error;}
        shutdownOwner=true;cancel=false;busy=true;cancellable=false;startedNanos=System.nanoTime();status="Saving and closing the session…";
    }
    void checkCancelled()throws IOException {
        if(cancel)throw new IOException("Launch cancelled. Saving and closing the session…");
    }
    void progress(String message)throws IOException {checkCancelled();status=message;}
    boolean closing(){return closing.get();}
    long elapsedSeconds(){return busy?Math.max(0,(System.nanoTime()-startedNanos)/1000000000):0;}
    void finish(){busy=false;cancellable=false;if(shutdownOwner){shutdownOwner=false;closing.set(false);}lock.unlock();}
}
