package io.github.russianranger.trasc;

import java.io.*;
import java.nio.file.Files;
import java.util.concurrent.TimeUnit;

/** Native GLES server belongs to one client launch and never enters the Linux rootfs. */
final class GraphicsBridge {
    private final Process process;
    private final File socket;
    private final Thread reader;
    private GraphicsBridge(Process process,File socket,File log){
        this.process=process;this.socket=socket;
        reader=new Thread(()->{
            final long limit=8*1024*1024;long written=0;OutputStream output=null;
            try(InputStream input=process.getInputStream()) {
                output=new BufferedOutputStream(new FileOutputStream(log));byte[] bytes=new byte[65536];int count;
                while((count=input.read(bytes))!=-1) {
                    if(written+count>limit) {
                        output.close();Files.move(log.toPath(),new File(log.getParentFile(),"client-gpu.overflow.log").toPath(),java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                        output=new BufferedOutputStream(new FileOutputStream(log));written=0;
                    }
                    output.write(bytes,0,count);output.flush();written+=count;
                }
            } catch(IOException error){process.destroy();}
            finally{if(output!=null)try{output.close();}catch(IOException ignored){}}
        },"client-gpu-log");reader.setDaemon(true);reader.start();
    }
    boolean alive(){return process.isAlive();}
    static GraphicsBridge start(File executable,File socket,File log)throws Exception {
        if(!executable.canExecute())throw new IOException("GPU bridge is missing from this APK; choose Software graphics");
        if(socket.getAbsolutePath().getBytes(java.nio.charset.StandardCharsets.UTF_8).length>=108)
            throw new IOException("The private GPU socket path is too long; choose Software graphics");
        socket.getParentFile().mkdirs();log.getParentFile().mkdirs();Files.deleteIfExists(socket.toPath());
        if(log.exists())Files.move(log.toPath(),new File(log.getParentFile(),"client-gpu.previous.log").toPath(),java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        Files.deleteIfExists(new File(log.getParentFile(),"client-gpu.overflow.log").toPath());
        ProcessBuilder builder=new ProcessBuilder(executable.getAbsolutePath(),"--use-egl-surfaceless","--use-gles","--multi-clients","--socket-path",socket.getAbsolutePath());
        builder.directory(socket.getParentFile());builder.redirectErrorStream(true);
        // Android's native EGL loader must use its own graphics driver.
        for(String key:new String[]{"GALLIUM_DRIVER","LIBGL_ALWAYS_SOFTWARE","LD_PRELOAD"})builder.environment().remove(key);
        GraphicsBridge bridge=new GraphicsBridge(builder.start(),socket,log);
        try {
            long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(20);
            while(System.nanoTime()<deadline) {
                if(!bridge.alive())throw new IOException("GPU bridge exited during driver setup; see client-gpu.log or choose Software graphics");
                if(socket.exists())return bridge;
                Thread.sleep(100);
            }
            throw new IOException("GPU driver setup timed out; see client-gpu.log or choose Software graphics");
        } catch(Exception error){bridge.stop();throw error;}
    }
    synchronized void stop()throws Exception {
        if(process.isAlive()) {
            process.destroy();
            if(!process.waitFor(3,TimeUnit.SECONDS)) {
                process.destroyForcibly();
                if(!process.waitFor(3,TimeUnit.SECONDS))throw new IOException("GPU bridge did not stop; wait before backing up");
            }
        }
        reader.join(2000);
        Files.deleteIfExists(socket.toPath());
    }
}
