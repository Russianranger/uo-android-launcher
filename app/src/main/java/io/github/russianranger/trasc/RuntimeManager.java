package io.github.russianranger.trasc;

import android.content.Context;
import org.json.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** Independent app-private Memento installation. */
final class RuntimeManager {
    interface Progress {void update(String text);}
    static final String RELEASE="https://github.com/Russianranger/trasc-server-android/releases/download/runtime-v1/";
    private static RuntimeManager instance;
    static synchronized RuntimeManager get(Context c){if(instance==null)instance=new RuntimeManager(c.getApplicationContext());return instance;}
    final Context context;
    final File home,work,rootfs;
    volatile boolean installing,sessionBusy;
    volatile String status="Prepare your realm to begin.";
    private volatile Process process;
    private String token;
    private RuntimeManager(Context c){context=c;home=c.getFilesDir();work=new File(home,"work");rootfs=new File(home,"rootfs");for(String n:new String[]{"incoming","logs","run","exports"})new File(work,n).mkdirs();}
    boolean installed(){return new File(rootfs,"etc/trasc-runtime.json").isFile();}
    boolean alive(){return process!=null&&process.isAlive();}
    synchronized void start()throws Exception {
        if(alive())return;
        if(installing)throw new IOException("Finish runtime installation first");
        if(!installed())throw new IOException("Install the realm runtime first");
        File backend=new File(home,"backend");backend.mkdirs();
        for(String n:new String[]{"engine.py","uo_content.py","MementoAndroidControl.cs","log_retention.py"})try(InputStream in=context.getAssets().open(n)){copy(in,new File(backend,n));}
        byte[] random=new byte[32];new SecureRandom().nextBytes(random);token=hex(random);
        write(new File(work,"run/api-token"),token);
        File tmp=new File(home,"tmp/server");tmp.mkdirs();
        write(new File(rootfs,"etc/hosts"),"127.0.0.1 localhost\n::1 localhost\n");
        write(new File(rootfs,"etc/resolv.conf"),"nameserver 1.1.1.1\nnameserver 8.8.8.8\n");
        File natives=new File(context.getApplicationInfo().nativeLibraryDir);
        List<String> args=new ArrayList<>(Arrays.asList(new File(natives,"libproot.so").getPath(),"--kill-on-exit","-0","-r",rootfs.getPath(),
            "-b","/dev","-b","/proc","-b",work+":/work","-b",backend+":/opt/uo","-b",tmp+":/tmp","-w","/work",
            "/usr/bin/env","-i","HOME=/root","USER=root","PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin","LANG=C.UTF-8","TMPDIR=/tmp","PYTHONUNBUFFERED=1",
            "/usr/bin/python3","/opt/uo/engine.py","--token-file","/work/run/api-token"));
        ProcessBuilder builder=new ProcessBuilder(args);prootEnvironment(builder,natives,tmp);
        LogRetention.rotate(new File(work,"logs/runtime.log"));builder.redirectErrorStream(true);builder.redirectOutput(ProcessBuilder.Redirect.appendTo(new File(work,"logs/runtime.log")));
        process=builder.start();status="Opening realm runtime…";
        for(int i=0;i<60;i++){if(!alive())throw new IOException("Runtime exited. Open runtime.log.");try{request("state",new JSONObject());status="Realm runtime ready";return;}catch(IOException e){Thread.sleep(500);}}
        throw new IOException("Runtime has not responded. Open runtime.log.");
    }
    static void prootEnvironment(ProcessBuilder builder,File natives,File tmp){builder.environment().put("PROOT_LOADER",new File(natives,"libproot-loader.so").getPath());builder.environment().put("PROOT_TMP_DIR",tmp.getPath());builder.environment().put("PROOT_NO_SECCOMP","1");}
    JSONObject request(String op,JSONObject args)throws Exception {
        if(!alive()||token==null)throw new IOException("Open the realm runtime first");
        HttpURLConnection c=(HttpURLConnection)new URL("http://127.0.0.1:18785/").openConnection();
        c.setConnectTimeout(2500);c.setReadTimeout(200000);c.setRequestMethod("POST");c.setDoOutput(true);
        c.setRequestProperty("Authorization","Bearer "+token);c.setRequestProperty("Content-Type","application/json");
        byte[] data=new JSONObject().put("operation",op).put("args",args).toString().getBytes(StandardCharsets.UTF_8);c.setFixedLengthStreamingMode(data.length);
        try{try(OutputStream out=c.getOutputStream()){out.write(data);}if(c.getResponseCode()!=200)throw new IOException("Local runtime returned HTTP "+c.getResponseCode());try(InputStream in=c.getInputStream()){return new JSONObject(readText(in,4*1024*1024));}}finally{c.disconnect();}
    }
    synchronized void stop()throws Exception {
        if(!alive())return;
        JSONObject response=request("exit",new JSONObject());
        if(!response.getBoolean("ok"))throw new IOException(response.optString("error"));
        if(!process.waitFor(30,TimeUnit.SECONDS))throw new IOException("Runtime is still stopping. It has not been force-killed.");
        process=null;status="Realm saved and closed";
    }
    JSONObject nativeState()throws Exception{return new JSONObject().put("installed",installed()).put("alive",alive()).put("installing",installing).put("status",status).put("free_bytes",home.getUsableSpace()).put("version",BuildConfig.VERSION_NAME);}
    JSONObject logs(String name)throws Exception{return new JSONObject().put("text",LocalLogs.tail(work,name)).put("names",new JSONArray(LocalLogs.inventory(work).keySet()));}
    JSONObject exportLogs()throws Exception {
        try{AndroidExitDiagnostics.collect(context,work);}
        catch(Exception unavailable){recordFailure("android_exit_diagnostics",unavailable);}
        File file=LocalLogs.export(work,new JSONObject().put("version",BuildConfig.VERSION_NAME).put("device",android.os.Build.MODEL).put("runtime",nativeState()).put("client",ClientRuntime.get(context).state()).toString(2));
        return new JSONObject().put("file","exports/"+file.getName());
    }
    void recordFailure(String op,Exception e){try{LocalLogs.failure(work,op,e);}catch(IOException ignored){android.util.Log.e("Memento",op,e);}}
    synchronized void beginInstall()throws IOException{if(alive()||installing)throw new IOException("Close the realm runtime first");if(!Arrays.asList(android.os.Build.SUPPORTED_ABIS).contains("arm64-v8a"))throw new IOException("ARM64 Android is required");installing=true;}
    void installOnline()throws Exception {
        beginInstall();File archive=new File(context.getCacheDir(),"runtime.tar.gz"),manifest=new File(context.getCacheDir(),"runtime-manifest.json");
        try{download(RELEASE+manifest.getName(),manifest);JSONObject info=ClientRuntime.json(manifest);
            if(info.getInt("format")!=1||!info.getString("architecture").equals("arm64")||!info.getString("file").equals("runtime-arm64.tar.gz"))throw new IOException("Unsupported runtime manifest");
            download(RELEASE+info.getString("file"),archive);if(!sha256(archive).equalsIgnoreCase(info.getString("sha256")))throw new IOException("Runtime checksum failed");installArchive(archive);
        }finally{installing=false;archive.delete();manifest.delete();}
    }
    void installArchive(File archive)throws Exception {
        File staging=new File(home,"runtime-install"),previous=new File(home,"rootfs.previous");
        if(!rootfs.exists()&&previous.exists()&&!previous.renameTo(rootfs))throw new IOException("Cannot recover previous runtime");
        TarExtractor.remove(staging);staging.mkdirs();
        try{TarExtractor.extract(archive,staging,n->status="Unpacking runtime · "+n+" files");
            JSONObject marker=ClientRuntime.json(new File(staging,"etc/trasc-runtime.json"));
            if(marker.getInt("format")!=1||!marker.getString("architecture").equals("arm64"))throw new IOException("Unsupported ARM64 runtime");
            for(String name:new String[]{"usr/bin/python3.11","usr/bin/git","usr/bin/apt-get"})if(!new File(staging,name).isFile())throw new IOException("Incomplete runtime: "+name);
            TarExtractor.remove(previous);if(rootfs.exists()&&!rootfs.renameTo(previous))throw new IOException("Cannot preserve previous runtime");
            if(!staging.renameTo(rootfs)){previous.renameTo(rootfs);throw new IOException("Cannot activate runtime");}status="Runtime installed. Open it and prepare the Mono compiler.";
        }finally{TarExtractor.remove(staging);}
    }
    void download(String url,File target)throws Exception{download(url,target,t->status=t);}
    void download(String url,File target,Progress progress)throws Exception {
        URL current=new URL(url);
        for(int redirect=0;redirect<8;redirect++){
            if(!current.getProtocol().equals("https"))throw new IOException("HTTPS is required");
            HttpURLConnection c=(HttpURLConnection)current.openConnection();c.setConnectTimeout(30000);c.setReadTimeout(60000);c.setInstanceFollowRedirects(false);c.setRequestProperty("User-Agent","UO-Memento/0.1");
            try{int code=c.getResponseCode();if(code>=300&&code<400){current=new URL(current,c.getHeaderField("Location"));continue;}
                if(code!=200)throw new IOException("Download returned HTTP "+code+". Use the matching offline runtime archive.");
                long size=c.getContentLengthLong(),done=0;if(size>home.getUsableSpace()-128L*1024*1024)throw new IOException("Not enough storage");
                try(InputStream in=c.getInputStream();OutputStream out=new FileOutputStream(target)){byte[] b=new byte[1024*1024];int n;while((n=in.read(b))!=-1){done+=n;if(done>4L*1024*1024*1024||home.getUsableSpace()<128L*1024*1024)throw new IOException("Download exceeds available storage");out.write(b,0,n);progress.update("Downloading · "+done/1048576+" MB");}}return;
            }finally{c.disconnect();}
        }throw new IOException("Too many redirects");
    }
    static String sha256(File file)throws Exception{MessageDigest d=MessageDigest.getInstance("SHA-256");try(InputStream in=new FileInputStream(file)){byte[] b=new byte[1024*1024];int n;while((n=in.read(b))!=-1)d.update(b,0,n);}return hex(d.digest());}
    static String hex(byte[] data){StringBuilder s=new StringBuilder();for(byte b:data)s.append(String.format(Locale.ROOT,"%02x",b&255));return s.toString();}
    static void write(File file,String text)throws IOException{file.getParentFile().mkdirs();try(OutputStream out=new FileOutputStream(file)){out.write(text.getBytes(StandardCharsets.UTF_8));}}
    static void copy(InputStream in,File file)throws IOException{file.getParentFile().mkdirs();try(OutputStream out=new FileOutputStream(file)){byte[] b=new byte[1024*1024];int n;while((n=in.read(b))!=-1){if(file.getParentFile().getUsableSpace()<n+67108864L)throw new IOException("Storage is full");out.write(b,0,n);}}}
    static String readText(InputStream in,int limit)throws IOException{ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1){if(out.size()+n>limit)throw new IOException("Response is too large");out.write(b,0,n);}return out.toString("UTF-8");}
}
