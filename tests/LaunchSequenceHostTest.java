package io.github.russianranger.trasc;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class LaunchSequenceHostTest {
    private static final long TIMEOUT_SECONDS=10;
    private static void check(boolean condition,String message){if(!condition)throw new AssertionError(message);}
    private static void await(CountDownLatch latch,String message)throws InterruptedException {
        check(latch.await(TIMEOUT_SECONDS,TimeUnit.SECONDS),message);
    }
    private static void join(Thread thread,AtomicReference<Throwable> failure)throws Exception {
        thread.join(TimeUnit.SECONDS.toMillis(TIMEOUT_SECONDS));
        check(!thread.isAlive(),"Worker did not complete: "+thread.getName());
        if(failure.get()!=null)throw new AssertionError("Worker failed: "+thread.getName(),failure.get());
    }
    private interface Task {void run()throws Exception;}
    private static Thread worker(String name,AtomicReference<Throwable> failure,Task task){
        Thread thread=new Thread(()->{try{task.run();}catch(Throwable error){failure.compareAndSet(null,error);}},name);
        thread.setDaemon(true);thread.start();return thread;
    }
    private static class RecordingHost implements LaunchSequence.Host {
        final List<String> events=Collections.synchronizedList(new ArrayList<>());
        final List<String> messages=new ArrayList<>();
        final IOException failure=new IOException("Expected stage failure");
        String failStage="";
        int failProgress;
        boolean requestedClient;
        void stage(String name)throws IOException {events.add(name);if(name.equals(failStage))throw failure;}
        public void checkSetup(boolean withClient)throws Exception {requestedClient=withClient;stage("setup");}
        public void progress(String message)throws Exception {messages.add(message);if(messages.size()==failProgress)throw failure;}
        public void openRuntime()throws Exception {stage("runtime");}
        public void awaitServer()throws Exception {stage("server");}
        public void awaitClient()throws Exception {stage("client");}
    }
    private static void successfulLaunches()throws Exception {
        RecordingHost full=new RecordingHost();LaunchSequence.run(full,true);
        check(full.events.equals(Arrays.asList("setup","runtime","server","client")),"Full launch was out of order");
        check(full.requestedClient,"Client prerequisites were skipped");
        check(full.messages.size()==4&&full.messages.get(3).contains("ready"),"Full launch did not report ready");
        RecordingHost server=new RecordingHost();LaunchSequence.run(server,false);
        check(server.events.equals(Arrays.asList("setup","runtime","server")),"Server-only launch started a client");
        check(!server.requestedClient,"Server-only launch required a client");
        check(server.messages.size()==3&&server.messages.get(2).contains("Server ready"),"Server-only launch did not report ready");
    }
    private static void waitForEachStage()throws Exception {
        CountDownLatch runtimeEntered=new CountDownLatch(1),runtimeReady=new CountDownLatch(1);
        CountDownLatch serverEntered=new CountDownLatch(1),serverReady=new CountDownLatch(1);
        AtomicReference<Throwable> failure=new AtomicReference<>();
        RecordingHost host=new RecordingHost(){
            public void openRuntime()throws Exception {
                super.openRuntime();runtimeEntered.countDown();await(runtimeReady,"Runtime was never released");
            }
            public void awaitServer()throws Exception {
                super.awaitServer();serverEntered.countDown();await(serverReady,"Server was never released");
            }
        };
        Thread launch=worker("ordered-launch",failure,()->LaunchSequence.run(host,true));
        try {
            await(runtimeEntered,"Runtime did not start");
            check(host.events.equals(Arrays.asList("setup","runtime")),"Server ran before runtime was ready");
            runtimeReady.countDown();await(serverEntered,"Server did not start");
            check(host.events.equals(Arrays.asList("setup","runtime","server")),"Client ran before server was ready");
            serverReady.countDown();join(launch,failure);
            check(host.events.equals(Arrays.asList("setup","runtime","server","client")),"Client did not run after server readiness");
        } finally {runtimeReady.countDown();serverReady.countDown();}
    }
    private static void failedStagesStopLaunch()throws Exception {
        List<String> stages=Arrays.asList("setup","runtime","server","client");
        for(int i=0;i<stages.size();i++){
            RecordingHost host=new RecordingHost();host.failStage=stages.get(i);
            try {LaunchSequence.run(host,true);throw new AssertionError("Failure was swallowed: "+host.failStage);}
            catch(IOException expected){check(expected==host.failure,"Original stage failure was replaced");}
            check(host.events.equals(stages.subList(0,i+1)),"Launch continued after "+host.failStage+" failed");
            check(host.messages.size()==i,"Launch reported progress or success after "+host.failStage+" failed");
        }
        // Cancellation is checked through progress between expensive stages.
        for(int progress=1;progress<=3;progress++){
            RecordingHost host=new RecordingHost();host.failProgress=progress;
            try {LaunchSequence.run(host,true);throw new AssertionError("Progress cancellation was swallowed");}
            catch(IOException expected){check(expected==host.failure,"Cancellation cause was replaced");}
            check(host.events.equals(stages.subList(0,progress)),"Cancelled launch ran another stage");
        }
    }
    private static void rejectsParallelActionsAndReleasesAfterErrors()throws Exception {
        SessionActions actions=new SessionActions();CountDownLatch begun=new CountDownLatch(1),failNow=new CountDownLatch(1);
        AtomicReference<Throwable> failure=new AtomicReference<>();IOException expected=new IOException("Setup failed");
        Thread first=worker("failing-action",failure,()->{
            actions.begin("Preparing runtime");
            try {begun.countDown();await(failNow,"Failure was never released");throw expected;}
            catch(IOException error){check(error==expected,"Unexpected action failure");}
            finally {actions.finish();}
        });
        try {
            await(begun,"First action did not begin");check(actions.busy,"Running action was not busy");
            try {actions.begin("Duplicate launch");throw new AssertionError("Parallel action was accepted");}
            catch(IOException expectedBusy){check(actions.status.equals("Preparing runtime"),"Rejected action overwrote active status");}
        } finally {failNow.countDown();}
        join(first,failure);check(!actions.busy,"Error left the session busy");
        actions.begin("Retry");try {actions.checkCancelled();check(actions.busy,"Retry was not accepted");}finally {actions.finish();}
    }
    private static void shutdownCancelsAndWaitsForLaunch()throws Exception {
        SessionActions actions=new SessionActions();AtomicReference<Throwable> failure=new AtomicReference<>();
        CountDownLatch begun=new CountDownLatch(1),cancelled=new CountDownLatch(1),releaseLaunch=new CountDownLatch(1);
        CountDownLatch shutdownAcquired=new CountDownLatch(1),releaseShutdown=new CountDownLatch(1);
        Thread launch=worker("cancellable-launch",failure,()->{
            actions.begin("Starting server");
            try {
                begun.countDown();
                long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(TIMEOUT_SECONDS);
                while(true){
                    try {actions.checkCancelled();}
                    catch(IOException expected){cancelled.countDown();break;}
                    check(System.nanoTime()<deadline,"Shutdown did not signal launch cancellation");
                    Thread.yield();
                }
                try {actions.progress("This must not overwrite status");throw new AssertionError("Cancelled progress was accepted");}
                catch(IOException expected){check(actions.status.equals("Starting server"),"Cancelled progress overwrote status");}
                await(releaseLaunch,"Launch was never released");
            } finally {actions.finish();}
        });
        await(begun,"Cancellable launch did not start");
        Thread shutdown=worker("session-shutdown",failure,()->{
            actions.beginShutdown();
            try {shutdownAcquired.countDown();actions.checkCancelled();await(releaseShutdown,"Shutdown was never released");}
            finally {actions.finish();}
        });
        try {
            await(cancelled,"Launch did not observe cancellation");
            check(shutdownAcquired.getCount()==1,"Shutdown overlapped the active launch");
            check(actions.busy,"Session became idle before launch released it");
            releaseLaunch.countDown();await(shutdownAcquired,"Shutdown did not start after launch released the session");
            check(actions.busy,"Shutdown was not busy");
            check(actions.status.contains("Saving and closing"),"Shutdown did not publish its status");
            try {actions.begin("New launch during shutdown");throw new AssertionError("Launch overlapped shutdown");}
            catch(IOException expectedBusy){/* Stop retains exclusive ownership until it finishes. */}
        } finally {releaseLaunch.countDown();releaseShutdown.countDown();}
        join(launch,failure);join(shutdown,failure);check(!actions.busy,"Shutdown left the session busy");
        actions.begin("Fresh launch");
        try {actions.checkCancelled();actions.progress("Ready again");check(actions.status.equals("Ready again"),"Fresh action could not report progress");}
        finally {actions.finish();}
    }
    public static void main(String[] args)throws Exception {
        successfulLaunches();waitForEachStage();failedStagesStopLaunch();
        rejectsParallelActionsAndReleasesAfterErrors();shutdownCancelsAndWaitsForLaunch();
        System.out.println("Launch sequence: ordered readiness, server-only startup, failure/cancellation gates, exclusive actions and shutdown handoff passed");
    }
}
