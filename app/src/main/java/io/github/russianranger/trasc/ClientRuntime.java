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
    static final String RELEASE="https://github.com/Russianranger/trasc-server-android/releases/download/client-runtime-v1/";
    private static ClientRuntime instance;
    static synchronized ClientRuntime get(Context c){if(instance==null)instance=new ClientRuntime(c.getApplicationContext());return instance;}
    final Context context;
    final RuntimeManager server;
    final File root,client,prefix,run,tmp,dotnet;
    volatile boolean busy;
    volatile String status="Import Memento and prepare the client runtime.";
    private volatile Process process;
    private GraphicsBridge graphics;
    private AudioBridge audio;
    ClientRuntime(Context c){context=c;server=RuntimeManager.get(c);root=new File(server.work,"client/runtime");client=new File(server.work,"client/current");prefix=new File(server.work,"client/prefix");run=new File(server.home,"tmp/client/session");tmp=new File(server.home,"tmp/client/tmp");dotnet=new File(server.work,"client/dotnet");}
    boolean installed(){return new File(root,"etc/trasc-client-runtime.json").isFile();}
    boolean alive(){return process!=null&&process.isAlive();}
    File frameSocket(){return new File(run,"frames.sock");}
    File displaySocket(){return new File(run,"display.sock");}
    static JSONObject json(File f)throws Exception{if(f.length()>131072)throw new IOException("Metadata exceeds limits");return new JSONObject(new String(Files.readAllBytes(f.toPath()),StandardCharsets.UTF_8));}
    JSONObject state()throws Exception{
        boolean running=alive();
        JSONObject out=new JSONObject().put("installed",installed()).put("alive",running).put("busy",busy).put("status",status).put("display_ready",false);
        File f=new File(run,"status.json");
        if(f.isFile())try{
            JSONObject launch=json(f);out.put("launch",launch);
            out.put("display_ready",ClientReadiness.ready(running,launch.optBoolean("display_ready"),launch.has("error"),
                displaySocket().exists(),launch.optString("presentation_active"),frameSocket().exists(),
                launch.optString("pointer_transport"),new File(run,"input.sock").exists()));
        }catch(Exception ignored){}
        File options=new File(server.work,"client/launch-options.json");if(options.isFile())out.put("launch_options",json(options));return out;
    }
    synchronized JSONObject installOnline()throws Exception{
        if(alive()||busy)throw new IOException("Stop the client and finish its current task first");busy=true;
        File archive=new File(context.getCacheDir(),"client-runtime.tar.gz"),manifest=new File(context.getCacheDir(),"client-runtime-manifest.json");
        try{server.download(RELEASE+manifest.getName(),manifest,t->status=t);JSONObject info=json(manifest);
            if(info.getInt("format")!=1||!info.getString("architecture").equals("arm64")||!info.getString("file").equals("client-runtime-arm64.tar.gz"))throw new IOException("Unsupported client runtime manifest");
            server.download(RELEASE+info.getString("file"),archive,t->status=t);if(!RuntimeManager.sha256(archive).equalsIgnoreCase(info.getString("sha256")))throw new IOException("Client runtime checksum failed");activate(archive);return state();
        }finally{busy=false;archive.delete();manifest.delete();}
    }
    synchronized JSONObject installOffline(File archive)throws Exception{if(alive()||busy)throw new IOException("Stop the client first");busy=true;try{activate(archive);return state();}finally{busy=false;}}
    private void activate(File archive)throws Exception{
        File staging=new File(server.home,"client-runtime-install"),previous=new File(root.getParentFile(),"runtime.previous");
        if(!root.exists()&&previous.exists()&&!previous.renameTo(root))throw new IOException("Cannot recover previous runtime");
        TarExtractor.remove(staging);staging.mkdirs();
        try{TarExtractor.extract(archive,staging,n->status="Unpacking client runtime · "+n+" files");JSONObject marker=json(new File(staging,"etc/trasc-client-runtime.json"));
            if(marker.getInt("format")!=1||!marker.getString("architecture").equals("arm64")||!marker.getString("runtime").equals("client-1.0"))throw new IOException("Unsupported client runtime");
            for(String n:new String[]{"usr/bin/python3.11","usr/bin/Xtigervnc","usr/local/bin/box64","opt/wine/bin/wine"})if(!new File(staging,n).isFile())throw new IOException("Incomplete client runtime: "+n);
            root.getParentFile().mkdirs();TarExtractor.remove(previous);if(root.exists()&&!root.renameTo(previous))throw new IOException("Cannot preserve client runtime");if(!staging.renameTo(root)){previous.renameTo(root);throw new IOException("Cannot activate client runtime");}status="Client runtime installed";
        }finally{TarExtractor.remove(staging);}
    }
    synchronized JSONObject start(JSONObject options)throws Exception{
        if(alive()||busy)throw new IOException("Client is already open or busy");
        if(!installed())throw new IOException("Install the client runtime first");
        if(server.alive()){
            JSONArray jobs=server.request("state",new JSONObject()).getJSONObject("result").getJSONArray("jobs");
            for(int i=0;i<jobs.length();i++){JSONObject job=jobs.getJSONObject(i);if(Arrays.asList("queued","running").contains(job.optString("status")))throw new IOException("Wait for the current realm/import task to finish");}
        }
        busy=true;
        try{
            String mode=options.optString("mode","client"),renderer=options.optString("renderer","turnip"),resolution=options.optString("resolution","1280x720"),presentation=options.optString("presentation_mode","native_surface");
            int fps=options.optInt("display_fps",60);
            boolean gumpSpace=options.optBoolean("gump_space",resolution.equals("1280x720"));
            if(gumpSpace&&!resolution.equals("1280x720"))throw new IOException("The 1098x720 world viewport requires a 1280x720 display");
            if(!Arrays.asList("client","desktop").contains(mode)||!Arrays.asList("turnip","virgl","software").contains(renderer)||!Arrays.asList("800x600","1024x768","1280x720").contains(resolution)||!Arrays.asList("rfb","native_surface").contains(presentation)||(fps!=30&&fps!=60))throw new IOException("Unsupported client options");
            JSONObject request=new JSONObject().put("mode",mode).put("renderer",renderer).put("resolution",resolution).put("presentation_mode",presentation).put("display_fps",fps).put("audio",options.optBoolean("audio",true));
            request.put("gump_space",gumpSpace);
            request.put("memory_compatibility",options.optBoolean("memory_compatibility",true));
            if(mode.equals("client")){
                JSONObject info=json(new File(client,"memento-client.json"));
                if(!info.optBoolean("self_contained")&&!new File(dotnet,"dotnet.exe").isFile())throw new IOException("Prepare the required .NET runtime in the Client tab first");
                request.put("client",info);
            }
            TarExtractor.remove(run);TarExtractor.remove(tmp);run.mkdirs();tmp.mkdirs();prefix.mkdirs();client.mkdirs();dotnet.mkdirs();
            File backend=new File(server.home,"client-backend");backend.mkdirs();
            try(InputStream in=context.getAssets().open("Memento.Diagnostics.dll")){RuntimeManager.copy(in,new File(backend,"Memento.Diagnostics.dll"));}
            for(String name:new String[]{"uo_client_runner.py","uo_content.py","client_presentation.py","client_audio.py","log_retention.py","graphics_probe.py","runtime_probe.py","x11-frame-bridge","presentation-bundle.json","libasound_module_pcm_trasc.so","audio-bundle.json","turnip-26.0.0.so","libXcomposite.so.1","dxvk-d3d11-x64.dll","dxvk-dxgi-x64.dll","dxvk-d3d11-x86.dll","dxvk-dxgi-x86.dll"})try(InputStream in=context.getAssets().open(name)){RuntimeManager.copy(in,new File(backend,name));}
            new File(backend,"x11-frame-bridge").setExecutable(true,true);
            RuntimeManager.write(new File(run,"request.json"),request.toString());
            RuntimeManager.write(new File(root,"etc/hosts"),"127.0.0.1 localhost\n::1 localhost\n");
            File natives=new File(context.getApplicationInfo().nativeLibraryDir),logs=new File(server.work,"logs");
            List<String> args=new ArrayList<>(Arrays.asList(new File(natives,"libproot.so").getPath(),"--kill-on-exit","--sysvipc","-0","-r",root.getPath(),
                "-b","/dev","-b","/proc","-b","/sys","-b",client+":/client","-b",dotnet+":/dotnet","-b",prefix+":/prefix","-b",run+":/session","-b",logs+":/logs","-b",backend+":/opt/uo-client","-b",tmp+":/tmp","-w","/client",
                "/usr/bin/env","-i","HOME=/root","USER=root","PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin","LANG=C.UTF-8","TMPDIR=/tmp","PYTHONUNBUFFERED=1","/usr/bin/python3","/opt/uo-client/uo_client_runner.py"));
            ProcessBuilder builder=new ProcessBuilder(args);RuntimeManager.prootEnvironment(builder,natives,tmp);
            if(renderer.equals("virgl"))graphics=GraphicsBridge.start(new File(natives,"libvirgl-server.so"),new File(tmp,".virgl_test"),new File(logs,"client-gpu.log"));
            if(request.getBoolean("audio"))audio=AudioBridge.start(context,new File(run,"audio.sock"),new File(logs,"client-audio.log"));
            LogRetention.rotate(new File(logs,"client-proot.log"));builder.redirectErrorStream(true);builder.redirectOutput(new File(logs,"client-proot.log"));process=builder.start();status="Starting TazUO display and Wine…";
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
