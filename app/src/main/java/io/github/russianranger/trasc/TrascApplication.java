package io.github.russianranger.trasc;

import android.app.Application;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Preserve a bounded Java crash record before Android's normal crash handler. */
public final class TrascApplication extends Application {
    @Override public void onCreate(){
        super.onCreate();
        Thread.UncaughtExceptionHandler original=Thread.getDefaultUncaughtExceptionHandler();
        AtomicBoolean recording=new AtomicBoolean();
        Thread.setDefaultUncaughtExceptionHandler((thread,error)->{
            if(recording.compareAndSet(false,true))try{
                File work=new File(getFilesDir(),"work");
                Path path=LocalLogs.checked(work.toPath(),"logs/android-crash.log");Files.createDirectories(path.getParent());
                // Do not acquire runtime/log-rotation locks in a dying process.
                StringBuilder text=new StringBuilder(java.time.Instant.now()+" version="+BuildConfig.VERSION_NAME+" thread="+thread.getName()+"\n");
                Set<Throwable> seen=Collections.newSetFromMap(new IdentityHashMap<>());
                Throwable cause=error;
                for(int depth=0;cause!=null&&depth<8&&seen.add(cause);depth++,cause=cause.getCause()){
                    String message=String.valueOf(cause);text.append(message,0,Math.min(message.length(),2048)).append('\n');
                    StackTraceElement[] stack=cause.getStackTrace();
                    for(int i=0;i<Math.min(stack.length,96);i++)text.append("  at ").append(stack[i]).append('\n');
                }
                try(OutputStream out=Files.newOutputStream(path,StandardOpenOption.CREATE,StandardOpenOption.TRUNCATE_EXISTING,LinkOption.NOFOLLOW_LINKS)){
                    out.write(text.toString().getBytes(StandardCharsets.UTF_8));
                }
            }catch(Throwable ignored){}
            finally{recording.set(false);}
            if(original!=null)original.uncaughtException(thread,error);
            else{android.os.Process.killProcess(android.os.Process.myPid());System.exit(10);}
        });
    }
}
