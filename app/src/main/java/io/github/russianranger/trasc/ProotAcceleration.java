package io.github.russianranger.trasc;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** Select only a mode whose isolated preflight completed on this device. */
final class ProotAcceleration {
    static final String OBSERVED="TRASC PRoot: seccomp acceleration observed";
    static void configure(Map<String,String> env,boolean accelerated) {
        // PRoot tests presence, not value: setting this variable to "0" also disables it.
        if(accelerated)env.remove("PROOT_NO_SECCOMP");else env.put("PROOT_NO_SECCOMP","1");
        env.put("TRASC_PROOT_REPORT","1");
    }
    static boolean preflight(List<String> command,Map<String,String> environment,File log,long timeoutMillis)throws Exception {
        ProcessBuilder builder=new ProcessBuilder(command);
        builder.environment().clear();builder.environment().putAll(environment);
        configure(builder.environment(),true);
        builder.redirectErrorStream(true);builder.redirectOutput(log);
        Process child=builder.start();
        boolean finished;
        try {finished=child.waitFor(timeoutMillis,TimeUnit.MILLISECONDS);}
        finally {
            if(child.isAlive()){child.destroy();if(!child.waitFor(3,TimeUnit.SECONDS)){child.destroyForcibly();if(!child.waitFor(3,TimeUnit.SECONDS))throw new IOException("Runtime preflight did not stop");}}
        }
        if(!finished)throw new IOException("Runtime preflight timed out; select Compatibility to retry");
        String output;
        try(InputStream in=new FileInputStream(log)){
            byte[] bytes=new byte[65536];int count=0,n;
            while(count<bytes.length&&(n=in.read(bytes,count,bytes.length-count))>0)count+=n;
            output=new String(bytes,0,count,StandardCharsets.UTF_8);
        }
        boolean passed=child.exitValue()==0&&output.contains(OBSERVED)&&output.contains("TRASC runtime probe passed");
        if(!passed)Files.write(log.toPath(),"\nTRASC: acceleration preflight unavailable; using Compatibility.\n".getBytes(StandardCharsets.UTF_8),StandardOpenOption.APPEND);
        return passed;
    }
}
