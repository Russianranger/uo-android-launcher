package io.github.russianranger.trasc;

import android.Manifest;
import android.app.Activity;
import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.webkit.*;
import org.json.*;
import java.io.*;
import java.util.concurrent.*;
import java.util.zip.*;

/** Local asset UI; no remote page can access the native bridge. */
public final class MainActivity extends Activity {
    private WebView web;
    private RuntimeManager runtime;
    private ClientRuntime client;
    private ControllerManager controller;
    private final ExecutorService tasks=Executors.newFixedThreadPool(3);
    private String pickerId,pickerKind,exportPath;
    private static final int IMPORT=10,FOLDER=11,EXPORT=12;
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);runtime=RuntimeManager.get(this);client=ClientRuntime.get(this);
        getWindow().setStatusBarColor(0xff17131e);getWindow().setNavigationBarColor(0xff17131e);
        web=new WebView(this);setContentView(web);
        controller=new ControllerManager(this,runtime.work,event->{});
        WebSettings settings=web.getSettings();settings.setJavaScriptEnabled(true);settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);settings.setAllowContentAccess(false);settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.addJavascriptInterface(new Bridge(),"Memento");
        web.setWebViewClient(new WebViewClient(){
            @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest request){
                Uri uri=request.getUrl();String path=uri.getPath();
                if(!"https".equals(uri.getScheme())||!"app.memento.local".equals(uri.getHost())||path==null||!path.matches("/[A-Za-z0-9_.-]+"))return blocked();
                try{String mime=path.endsWith(".js")?"application/javascript":path.endsWith(".css")?"text/css":path.endsWith(".png")?"image/png":path.endsWith(".webp")?"image/webp":"text/html";
                    WebResourceResponse response=new WebResourceResponse(mime,"UTF-8",getAssets().open("ui"+path));
                    java.util.Map<String,String> headers=new java.util.HashMap<>();headers.put("Content-Security-Policy","default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'none'; base-uri 'none'; form-action 'none'");response.setResponseHeaders(headers);return response;
                }catch(IOException e){return blocked();}
            }
            private WebResourceResponse blocked(){return new WebResourceResponse("text/plain","UTF-8",new ByteArrayInputStream(new byte[0]));}
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){return true;}
            @Override public boolean onRenderProcessGone(WebView view,RenderProcessGoneDetail detail){runtime.recordFailure("ui",new IOException("WebView renderer exited"));web=null;view.destroy();recreate();return true;}
        });
        web.loadUrl("https://app.memento.local/index.html");
        if(android.os.Build.VERSION.SDK_INT>=33)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},20);
    }
    private void service(){startForegroundService(new Intent(this,ServerService.class));}
    private void submit(Runnable task){try{tasks.execute(task);}catch(RejectedExecutionException ignored){}}
    private void reply(String id,Object result,Exception error){
        try{JSONObject value=new JSONObject().put("ok",error==null);if(error==null)value.put("result",result);else value.put("error",String.valueOf(error.getMessage()));
            String script="window.nativeReply("+JSONObject.quote(id)+","+value+")";
            runOnUiThread(()->{if(web!=null&&!isDestroyed())web.evaluateJavascript(script,null);});
        }catch(Exception ignored){}
    }
    private JSONObject realm(String operation,JSONObject args)throws Exception {
        JSONObject response=runtime.request(operation,args);
        if(!response.getBoolean("ok"))throw new IOException(response.optString("error"));
        return response.getJSONObject("result");
    }
    private void requireIdle(JSONObject state)throws Exception {
        JSONArray jobs=state.getJSONArray("jobs");
        for(int i=0;i<jobs.length();i++){
            JSONObject job=jobs.getJSONObject(i);
            if(java.util.Arrays.asList("queued","running").contains(job.optString("status")))
                throw new IOException("Wait for the current realm task to finish: "+job.optString("message"));
        }
    }
    private void awaitServer()throws Exception {
        JSONObject state=realm("state",new JSONObject());requireIdle(state);
        if(!state.optBoolean("mono_ready"))throw new IOException("Open Realm setup and prepare the Mono compiler first");
        if(state.optBoolean("ready"))return;
        String jobId=state.optBoolean("running")?null:realm("server_start",new JSONObject()).getString("id");
        long deadline=android.os.SystemClock.elapsedRealtime()+660000;
        while(android.os.SystemClock.elapsedRealtime()<deadline){
            runtime.session.checkCancelled();state=realm("state",new JSONObject());
            boolean jobDone=jobId==null;
            if(jobId!=null){
                JSONArray jobs=state.getJSONArray("jobs");boolean found=false;
                for(int i=0;i<jobs.length();i++){
                    JSONObject job=jobs.getJSONObject(i);if(!jobId.equals(job.optString("id")))continue;
                    found=true;
                    if("error".equals(job.optString("status")))throw new IOException(job.optString("error","Server startup failed. Open server.log."));
                    jobDone="done".equals(job.optString("status"));break;
                }
                if(!found)throw new IOException("Server startup task disappeared. Open the Journal for logs.");
            }
            if(jobDone&&state.optBoolean("ready"))return;
            if(jobDone&&!state.optBoolean("running"))throw new IOException("Server stopped before it was ready. Open server.log.");
            Thread.sleep(500);
        }
        throw new IOException("Server is still starting. Check server.log; it has been left running.");
    }
    private void awaitClient(JSONObject options)throws Exception {
        runtime.session.checkCancelled();
        if(!client.alive())client.start(options);
        long deadline=android.os.SystemClock.elapsedRealtime()+180000;
        while(android.os.SystemClock.elapsedRealtime()<deadline){
            runtime.session.checkCancelled();JSONObject state=client.state(),launch=state.optJSONObject("launch");
            if(launch!=null&&launch.has("error"))throw new IOException(launch.optString("error"));
            if(state.optBoolean("display_ready"))return;
            if(!state.optBoolean("alive"))throw new IOException("Client stopped. Open the Journal for logs.");
            Thread.sleep(500);
        }
        throw new IOException("Client is still preparing its display. Check the Journal, then use Return to client when ready.");
    }
    private JSONObject launchSession(boolean withClient,JSONObject options)throws Exception {
        LaunchSequence.run(new LaunchSequence.Host(){
            public void checkSetup(boolean includeClient)throws Exception {
                if(!runtime.installed())throw new IOException("Open Realm setup and install the realm runtime first");
                if(!new File(runtime.work,"server/WorldLinux.exe").isFile())throw new IOException("Open Realm setup and pull & compile the server first");
                if(includeClient){
                    if(!client.installed())throw new IOException("Open Client setup and install the FEX client runtime first");
                    File metadata=new File(client.client,"memento-client.json");
                    if(!metadata.isFile())throw new IOException("Open Client setup and import the complete Memento client first");
                    if(!ClientRuntime.json(metadata).optBoolean("self_contained")&&!new File(client.dotnet,"dotnet.exe").isFile())throw new IOException("Open Client setup and prepare the required .NET runtime first");
                    if(client.busy)throw new IOException("Finish the current client setup task first");
                }
            }
            public void progress(String message)throws Exception {runtime.session.progress(message);}
            public void openRuntime()throws Exception {runtime.start();}
            public void awaitServer()throws Exception {MainActivity.this.awaitServer();}
            public void awaitClient()throws Exception {MainActivity.this.awaitClient(options);}
        },withClient);
        runtime.session.checkCancelled();
        if(withClient)runOnUiThread(()->{if(!isDestroyed()&&!runtime.session.closing())startActivity(new Intent(MainActivity.this,ClientActivity.class));});
        return new JSONObject().put("message",runtime.session.status);
    }
    final class Bridge {
        @JavascriptInterface public void call(String id,String operation,String input){submit(()->{
            boolean guarded=false;
            try{JSONObject args=new JSONObject(input);Object result;
                if(java.util.Arrays.asList("session_close","session_cancel").contains(operation)){
                    runtime.session.beginShutdown();guarded=true;
                }else if(!java.util.Arrays.asList("native_state","client_native_state","state","logs","export_logs","controller_open","client_view","pick","export","backups","backup_preview","settings_read").contains(operation)){
                    runtime.session.begin("Working · "+operation.replace('_',' '));guarded=true;
                    runtime.session.cancellable=java.util.Arrays.asList("session_play","server_start").contains(operation);
                }
                switch(operation){
                    case "native_state":result=runtime.nativeState();break;
                    case "client_native_state":result=client.state();break;
                    case "runtime_install":service();runtime.installOnline();result=runtime.nativeState();break;
                    case "runtime_start":service();runtime.start();result=runtime.nativeState();break;
                    case "runtime_stop":runtime.stop();if(!client.alive()&&!client.busy)stopService(new Intent(MainActivity.this,ServerService.class));result=runtime.nativeState();break;
                    case "client_runtime_online":service();result=client.installOnline();break;
                    case "session_play":service();result=launchSession(true,args);break;
                    case "server_start":service();result=launchSession(false,args);break;
                    case "session_close":case "session_cancel":service();result=ServerService.closeSession(runtime,client);if(!client.alive()&&!runtime.alive())stopService(new Intent(MainActivity.this,ServerService.class));break;
                    case "client_start":service();result=client.start(args);break;
                    case "save_backup":service();runtime.start();requireIdle(realm("state",new JSONObject()));client.stop();result=realm("save_backup",args);break;
                    case "client_stop":client.stop();result=client.state();break;
                    case "client_view":if(!client.state().optBoolean("display_ready"))throw new IOException("Wait for the client display and controls to finish preparing");runOnUiThread(()->startActivity(new Intent(MainActivity.this,ClientActivity.class)));result=new JSONObject();break;
                    case "controller_open":runOnUiThread(()->{controller.reload();new ControllerDialog(MainActivity.this,controller,()->{}).show();reply(id,new JSONObject(),null);});return;
                    case "logs":result=runtime.logs(args.optString("name","runtime.log"));break;
                    case "export_logs":result=runtime.exportLogs();break;
                    case "backups":result=LocalBackups.inventory(runtime.work);break;
                    case "discard_import":{
                        String name=args.getString("file");if(!name.matches("[0-9a-f-]{36}\\.zip"))throw new IOException("Invalid pending import");
                        File file=TarExtractor.path(runtime.work,"incoming/"+name);if(file.isFile()&&!file.delete())throw new IOException("Could not discard the pending import");
                        result=new JSONObject().put("message","Import cancelled");break;
                    }
                    case "pick":if(runtime.session.busy)throw new IOException("Finish the current launch or setup task first");runOnUiThread(()->pick(id,args.optString("kind","client")));return;
                    case "export":runOnUiThread(()->export(id,args.optString("path")));return;
                    default:
                        service();
                        synchronized(client){
                            if(java.util.Arrays.asList("import_client_zip","prepare_dotnet","pull_compile","restore_world").contains(operation)&&(client.alive()||client.busy))throw new IOException("Stop the client before changing its files or world");
                            if(!"state".equals(operation))runtime.start();
                            if(java.util.Arrays.asList("save_backup","backup_world","restore_world","settings_save","settings_undo").contains(operation))requireIdle(realm("state",new JSONObject()));
                            JSONObject response=runtime.request(operation,args);if(!response.getBoolean("ok"))throw new IOException(response.optString("error"));result=response.get("result");
                        }
                }
                reply(id,result,null);
            }catch(Exception e){if(guarded)runtime.session.status=e.getMessage();runtime.recordFailure(operation,e);reply(id,null,e);}
            finally{if(guarded)runtime.session.finish();}
        });}
    }
    private void pick(String id,String kind){
        if(pickerId!=null){reply(id,null,new IOException("Finish the current file picker first"));return;}
        pickerId=id;pickerKind=kind;
        Intent intent=kind.equals("client-folder")?new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE):new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");
        try{startActivityForResult(intent,kind.equals("client-folder")?FOLDER:IMPORT);}catch(Exception e){pickerId=null;reply(id,null,e);}
    }
    private File exportFile(String path)throws IOException{File file=TarExtractor.path(runtime.work,path);if(!path.startsWith("exports/")||!file.isFile())throw new IOException("Select an exported backup or log archive");return file;}
    private void export(String id,String path){
        if(pickerId!=null){reply(id,null,new IOException("Finish the current file picker first"));return;}
        try{File file=exportFile(path);pickerId=id;exportPath=path;startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/zip").putExtra(Intent.EXTRA_TITLE,file.getName()),EXPORT);}catch(Exception e){pickerId=null;reply(id,null,e);}
    }
    private void zipTree(Uri tree,String doc,String prefix,ZipOutputStream out,int[] count,long[] bytes)throws Exception{
        if(prefix.split("/").length>48)throw new IOException("Folder nesting is too deep");
        Uri children=DocumentsContract.buildChildDocumentsUriUsingTree(tree,doc);
        String[] columns={DocumentsContract.Document.COLUMN_DOCUMENT_ID,DocumentsContract.Document.COLUMN_DISPLAY_NAME,DocumentsContract.Document.COLUMN_MIME_TYPE};
        try(Cursor cursor=getContentResolver().query(children,columns,null,null,null)){
            if(cursor==null)throw new IOException("Cannot read selected folder");
            while(cursor.moveToNext()){
                if(++count[0]>250000)throw new IOException("Too many imported files");
                String child=cursor.getString(0),name=cursor.getString(1),mime=cursor.getString(2);
                if(name==null||name.equals(".")||name.equals("..")||name.contains("/")||name.contains("\\")||name.contains(":"))throw new IOException("Unsupported filename");
                String relative=prefix+name;
                if(DocumentsContract.Document.MIME_TYPE_DIR.equals(mime)){zipTree(tree,child,relative+"/",out,count,bytes);continue;}
                runtime.status="Importing · "+count[0]+" files · "+bytes[0]/1048576+" MB";
                out.putNextEntry(new ZipEntry(relative));
                try(InputStream in=getContentResolver().openInputStream(DocumentsContract.buildDocumentUriUsingTree(tree,child))){
                    if(in==null)throw new IOException("Cannot read "+name);byte[] buffer=new byte[1024*1024];int n;
                    while((n=in.read(buffer))!=-1){bytes[0]+=n;if(bytes[0]>32L*1024*1024*1024||runtime.home.getUsableSpace()<128L*1024*1024)throw new IOException("Import exceeds available storage");out.write(buffer,0,n);}
                }out.closeEntry();
            }
        }
    }
    @Override protected void onActivityResult(int request,int code,Intent data){
        super.onActivityResult(request,code,data);if(request!=IMPORT&&request!=FOLDER&&request!=EXPORT)return;
        String id=pickerId,kind=pickerKind,path=exportPath;pickerId=null;if(id==null)return;
        if(code!=RESULT_OK||data==null||data.getData()==null){reply(id,null,new IOException("File selection cancelled"));return;}
        Uri uri=data.getData();service();submit(()->{File temp=null;boolean guarded=false;
            try{
                if(request==EXPORT){try(InputStream in=new FileInputStream(exportFile(path));OutputStream out=getContentResolver().openOutputStream(uri,"wt")){if(out==null)throw new IOException("Cannot write destination");byte[] b=new byte[1024*1024];int n;while((n=in.read(b))!=-1)out.write(b,0,n);}LocalBackups.markExported(runtime.work,path);reply(id,new JSONObject().put("message","File exported"),null);return;}
                runtime.session.begin("Importing selected files…");guarded=true;
                synchronized(client){
                    if(client.alive()||client.busy)throw new IOException("Stop the client before importing");
                    client.busy=true;
                }
                try{
                    temp=new File(runtime.work,"incoming/"+java.util.UUID.randomUUID()+".zip");
                    if(request==FOLDER){try(ZipOutputStream zip=new ZipOutputStream(new FileOutputStream(temp))){zip.setLevel(0);zipTree(uri,DocumentsContract.getTreeDocumentId(uri),"",zip,new int[]{0},new long[]{0});}}
                    else try(InputStream in=getContentResolver().openInputStream(uri)){if(in==null)throw new IOException("Cannot read file");RuntimeManager.copy(in,temp);}
                }finally{client.busy=false;}
                if(kind.equals("runtime")){runtime.beginInstall();try{runtime.installArchive(temp);}finally{runtime.installing=false;}reply(id,runtime.nativeState(),null);}
                else if(kind.equals("client-runtime")){reply(id,client.installOffline(temp),null);}
                else{
                    synchronized(client){
                        if(client.alive()||client.busy)throw new IOException("Stop the client before importing");
                        runtime.start();
                        JSONObject response=runtime.request(kind.equals("world")?"preview_world":"import_client_zip",new JSONObject().put("file",temp.getName()));
                        if(!response.getBoolean("ok"))throw new IOException(response.optString("error"));reply(id,response.get("result"),null);temp=null;
                    }
                }
            }catch(Exception e){runtime.recordFailure("import_export",e);reply(id,null,e);}finally{if(temp!=null)temp.delete();if(guarded)runtime.session.finish();}
        });
    }
    @Override public void onBackPressed(){super.onBackPressed();}
    @Override protected void onDestroy(){if(controller!=null)controller.close();if(web!=null){web.removeJavascriptInterface("Memento");web.destroy();web=null;}tasks.shutdown();super.onDestroy();}
}
