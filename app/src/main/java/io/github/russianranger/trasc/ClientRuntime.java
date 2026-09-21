package io.github.russianranger.trasc;

import android.content.Context;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** Wine desktop and TazUO run in a separate rootfs and prefix. */
final class ClientRuntime {
    static final String RUNTIME_ID="fex-arm64ec-1";
    static final String RELEASE="https://github.com/Russianranger/uo-android-launcher/releases/download/v0.2.0/";
    private static ClientRuntime instance;
    static synchronized ClientRuntime get(Context c){if(instance==null)instance=new ClientRuntime(c.getApplicationContext());return instance;}
    final Context context;
    final RuntimeManager server;
    final File root,client,prefix,run,tmp,dotnet;
    volatile boolean busy;
    volatile String status="Install the FEX client runtime to use the new engine.";
    private volatile Process process;
    private GraphicsBridge graphics;
    private AudioBridge audio;
    ClientRuntime(Context c){context=c;server=RuntimeManager.get(c);root=new File(server.work,"client/runtime-fex-v1");client=new File(server.work,"client/current");prefix=new File(server.work,"client/prefix-fex-v1");run=new File(server.home,"tmp/client/session");tmp=new File(server.home,"tmp/client/tmp");dotnet=new File(server.work,"client/dotnet");if(installed())status="FEX / ARM64EC runtime ready.";}
    boolean installed(){try{return validMarker(json(new File(root,"etc/memento-client-runtime.json")));}catch(Exception e){return false;}}
    static boolean validMarker(JSONObject marker){return marker.optInt("format")==2&&marker.optString("architecture").equals("arm64")&&marker.optString("runtime").equals(RUNTIME_ID);}
    boolean alive(){return process!=null&&process.isAlive();}
    File frameSocket(){return new File(run,"frames.sock");}
    File displaySocket(){return new File(run,"display.sock");}
    static JSONObject json(File f)throws Exception{if(f.length()>131072)throw new IOException("Metadata exceeds limits");return new JSONObject(new String(Files.readAllBytes(f.toPath()),StandardCharsets.UTF_8));}
    JSONObject state()throws Exception{
        boolean running=alive();
        JSONObject out=new JSONObject().put("runtime_backend",RUNTIME_ID).put("installed",installed()).put("alive",running).put("busy",busy).put("status",status).put("display_ready",false);
        File f=new File(run,"status.json");
        if(f.isFile())try{
            JSONObject launch=json(f);
            if(RUNTIME_ID.equals(launch.optString("runtime_backend"))){out.put("launch",launch);
            out.put("display_ready",ClientReadiness.ready(running,launch.optBoolean("display_ready"),launch.has("error"),
                displaySocket().exists(),launch.optString("presentation_active"),frameSocket().exists(),
                launch.optString("pointer_transport"),new File(run,"input.sock").exists()));
            }
        }catch(Exception ignored){}
        File options=new File(server.work,"client/launch-options.json");if(options.isFile())out.put("launch_options",json(options));return out;
    }
    synchronized JSONObject installOnline()throws Exception{
        if(alive()||busy)throw new IOException("Stop the client and finish its current task first");busy=true;
        File archive=new File(context.getCacheDir(),"client-runtime.tar.gz"),manifest=new File(context.getCacheDir(),"client-runtime-manifest.json");
        try{server.download(RELEASE+manifest.getName(),manifest,t->status=t);JSONObject info=json(manifest);
            if(!validMarker(info)||!info.getString("file").equals("client-runtime-arm64.tar.gz"))throw new IOException("Unsupported client runtime manifest");
            server.download(RELEASE+info.getString("file"),archive,t->status=t);if(!RuntimeManager.sha256(archive).equalsIgnoreCase(info.getString("sha256")))throw new IOException("Client runtime checksum failed");activate(archive);return state();
        }finally{busy=false;archive.delete();manifest.delete();}
    }
    synchronized JSONObject installOffline(File archive)throws Exception{if(alive()||busy)throw new IOException("Stop the client first");busy=true;try{activate(archive);return state();}finally{busy=false;}}
    private void activate(File archive)throws Exception{
        File staging=new File(server.home,"client-runtime-fex-install"),previous=new File(root.getParentFile(),"runtime-fex-v1.previous");
        if(!root.exists()&&previous.exists()&&!previous.renameTo(root))throw new IOException("Cannot recover previous runtime");
        TarExtractor.remove(staging);staging.mkdirs();
        try{TarExtractor.extract(archive,staging,n->status="Unpacking client runtime · "+n+" files");JSONObject marker=json(new File(staging,"etc/memento-client-runtime.json"));
            if(!validMarker(marker))throw new IOException("Unsupported client runtime");
            for(String n:new String[]{"usr/bin/python3.11","usr/bin/Xtigervnc","opt/wine/bin/wine","opt/wine/bin/wineserver","opt/wine/lib/wine/aarch64-windows/libarm64ecfex.dll","opt/wine/lib/wine/aarch64-windows/libwow64fex.dll"})if(!new File(staging,n).isFile())throw new IOException("Incomplete client runtime: "+n);
            for(String name:new String[]{"wine","wineserver"})try(InputStream in=new FileInputStream(new File(staging,"opt/wine/bin/"+name))){
                byte[] header=new byte[20];TarExtractor.full(in,header,header.length);
                if(header[0]!=0x7f||header[1]!='E'||header[2]!='L'||header[3]!='F'||header[4]!=2||header[5]!=1||(header[18]&255)!=183||header[19]!=0)
                    throw new IOException("FEX runtime requires native ARM64 Wine");
            }
            root.getParentFile().mkdirs();TarExtractor.remove(previous);if(root.exists()&&!root.renameTo(previous))throw new IOException("Cannot preserve client runtime");if(!staging.renameTo(root)){previous.renameTo(root);throw new IOException("Cannot activate client runtime");}status="FEX / ARM64EC runtime installed. Ready to launch.";
        }finally{TarExtractor.remove(staging);}
    }
    synchronized JSONObject start(JSONObject options)throws Exception{
        if(alive()||busy)throw new IOException("Client is already open or busy");
        if(!installed())throw new IOException("Install the FEX client runtime in the Client tab first");
        if(server.alive()){
            JSONArray jobs=server.request("state",new JSONObject()).getJSONObject("result").getJSONArray("jobs");
            for(int i=0;i<jobs.length();i++){JSONObject job=jobs.getJSONObject(i);if(Arrays.asList("queued","running").contains(job.optString("status")))throw new IOException("Wait for the current realm/import task to finish");}
        }
        busy=true;
        try{
            String mode=options.optString("mode","client"),renderer=options.optString("renderer","turnip"),resolution=options.optString("resolution","1280x720"),presentation=options.optString("presentation_mode","native_surface");
            int fps=options.optInt("display_fps",30);
            boolean gumpSpace=options.optBoolean("gump_space",resolution.equals("1280x720"));
            if(gumpSpace&&!resolution.equals("1280x720"))throw new IOException("The 1098x720 world viewport requires a 1280x720 display");
            if(!Arrays.asList("client","desktop").contains(mode)||!Arrays.asList("turnip","virgl","software").contains(renderer)||!Arrays.asList("800x600","1024x768","1280x720").contains(resolution)||!Arrays.asList("rfb","native_surface").contains(presentation)||(fps!=30&&fps!=60))throw new IOException("Unsupported client options");
            JSONObject request=new JSONObject().put("mode",mode).put("renderer",renderer).put("resolution",resolution).put("presentation_mode",presentation).put("display_fps",fps).put("audio",options.optBoolean("audio",true));
            String audioDriver=options.optString("audio_driver","wasapi");
            if(!audioDriver.equals("wasapi")&&!audioDriver.equals("directsound"))throw new IOException("Invalid audio driver");
            request.put("audio_driver",audioDriver).put("proot_acceleration",options.optBoolean("proot_acceleration",true));
            request.put("gump_space",gumpSpace);
            request.put("music_cache",options.optBoolean("music_cache",true));
            boolean fexOptions=RUNTIME_ID.equals(options.optString("runtime_backend"));
            request.put("runtime_backend",RUNTIME_ID);
            request.put("managed_diagnostics",fexOptions&&options.optBoolean("managed_diagnostics",false));
            request.put("render_trace",fexOptions&&options.optBoolean("render_trace",false));
            request.put("sdl_graphics_fixes",fexOptions&&options.optBoolean("sdl_graphics_fixes",false));
            if(mode.equals("client")){
                JSONObject info=json(new File(client,"memento-client.json"));
                if(!info.optBoolean("self_contained")&&!new File(dotnet,"dotnet.exe").isFile())throw new IOException("Prepare the required .NET runtime in the Client tab first");
                request.put("client",info);
            }
            TarExtractor.remove(run);TarExtractor.remove(tmp);run.mkdirs();tmp.mkdirs();prefix.mkdirs();client.mkdirs();dotnet.mkdirs();
            File backend=new File(server.home,"client-backend");backend.mkdirs();
            for(String name:ClientRuntimeAssets.FILES)try(InputStream in=context.getAssets().open(name)){RuntimeManager.copy(in,new File(backend,name));}
            new File(backend,"x11-frame-bridge").setExecutable(true,true);
            RuntimeManager.write(new File(run,"request.json"),request.toString());
            RuntimeManager.write(new File(root,"etc/hosts"),"127.0.0.1 localhost\n::1 localhost\n");
            File natives=new File(context.getApplicationInfo().nativeLibraryDir),logs=new File(server.work,"logs");
            List<String> args=new ArrayList<>(Arrays.asList(new File(natives,"libproot.so").getPath(),"--kill-on-exit","--sysvipc","-0","-r",root.getPath(),
                "-b","/dev","-b","/proc","-b","/sys","-b",client+":/client","-b",dotnet+":/dotnet","-b",prefix+":/prefix","-b",run+":/session","-b",logs+":/logs","-b",backend+":/opt/uo-client","-b",tmp+":/tmp","-w","/client",
                "/usr/bin/env","-i","HOME=/root","USER=root","PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin","LANG=C.UTF-8","TMPDIR=/tmp","PYTHONUNBUFFERED=1","/usr/bin/python3","/opt/uo-client/uo_client_runner.py"));
            ProcessBuilder builder=new ProcessBuilder(args);RuntimeManager.prootEnvironment(builder,natives,tmp);
            // The pinned PRoot checks kernel support and falls back when its
            // seccomp acceleration is unavailable. Keep the server's policy
            // separate; this option applies only to the client process tree.
            if(request.getBoolean("proot_acceleration"))builder.environment().remove("PROOT_NO_SECCOMP");
            builder.environment().put("TRASC_PROOT_REPORT","1");
            if(renderer.equals("virgl"))graphics=GraphicsBridge.start(new File(natives,"libvirgl-server.so"),new File(tmp,".virgl_test"),new File(logs,"client-gpu.log"));
            if(request.getBoolean("audio"))audio=AudioBridge.start(context,new File(run,"audio.sock"),new File(logs,"client-audio.log"));
            LogRetention.rotate(new File(logs,"client-proot.log"));builder.redirectErrorStream(true);builder.redirectOutput(new File(logs,"client-proot.log"));process=builder.start();status="Starting TazUO with FEX / ARM64EC…";
            RuntimeManager.write(new File(server.work,"client/launch-options.json"),request.toString());
            final Process owned=process;final GraphicsBridge gpu=graphics;final AudioBridge sound=audio;
            new Thread(()->{
                try{
                    int code=owned.waitFor();
                    synchronized(ClientRuntime.this){
                        if(process==owned){
                            File report=new File(run,"status.json");JSONObject launch=new JSONObject();
                            if(report.isFile())try{launch=json(report);}catch(Exception ignored){}
                            launch.put("supervisor_exit_code",code).put("display_ready",false);
                            if(code!=0&&!launch.has("error"))launch.put("phase","error").put("error","Client runtime exited with code "+code+". Export support logs from the Journal.");
                            if(!launch.has("error"))launch.put("phase","stopped");
                            status=launch.optString("error","Client stopped");
                            RuntimeManager.write(report,launch.toString());
                            RuntimeManager.write(new File(logs,"client-state.json"),launch.toString());
                        }
                    }
                }catch(InterruptedException e){Thread.currentThread().interrupt();}
                catch(Exception e){server.recordFailure("client_process_exit",e);}
                finally{if(gpu!=null)try{gpu.stop();}catch(Exception ignored){}if(sound!=null)sound.close();}
            },"memento-client-monitor").start();
            return state();
        }catch(Exception e){if(graphics!=null)graphics.stop();if(audio!=null)audio.close();status=e.getMessage();throw e;}finally{busy=false;}
    }
    synchronized void stop()throws Exception{
        if(alive()){RuntimeManager.write(new File(run,"stop"),"stop");if(!process.waitFor(30,TimeUnit.SECONDS)){process.destroy();if(!process.waitFor(5,TimeUnit.SECONDS))process.destroyForcibly();}}
        if(graphics!=null){graphics.stop();graphics=null;}if(audio!=null){audio.close();audio=null;}process=null;status="Client stopped";
    }
}
