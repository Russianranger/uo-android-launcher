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
                try{String mime=path.endsWith(".js")?"application/javascript":path.endsWith(".css")?"text/css":path.endsWith(".png")?"image/png":"text/html";
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
    final class Bridge {
        @JavascriptInterface public void call(String id,String operation,String input){submit(()->{
            try{JSONObject args=new JSONObject(input);Object result;
                switch(operation){
                    case "native_state":result=runtime.nativeState();break;
                    case "client_native_state":result=client.state();break;
                    case "runtime_install":service();runtime.installOnline();result=runtime.nativeState();break;
                    case "runtime_start":service();runtime.start();result=runtime.nativeState();break;
                    case "runtime_stop":runtime.stop();if(!client.alive()&&!client.busy)stopService(new Intent(MainActivity.this,ServerService.class));result=runtime.nativeState();break;
                    case "client_runtime_online":service();result=client.installOnline();break;
                    case "client_start":service();result=client.start(args);break;
                    case "client_stop":client.stop();result=client.state();break;
                    case "client_view":if(!client.state().optBoolean("display_ready"))throw new IOException("Wait for the client display and controls to finish preparing");runOnUiThread(()->startActivity(new Intent(MainActivity.this,ClientActivity.class)));result=new JSONObject();break;
                    case "controller_open":runOnUiThread(()->{controller.reload();new ControllerDialog(MainActivity.this,controller,()->{}).show();reply(id,new JSONObject(),null);});return;
                    case "logs":result=runtime.logs(args.optString("name","runtime.log"));break;
                    case "export_logs":result=runtime.exportLogs();break;
                    case "pick":runOnUiThread(()->pick(id,args.optString("kind","client")));return;
                    case "export":runOnUiThread(()->export(id,args.optString("path")));return;
                    default:
                        service();
                        synchronized(client){
                            if(java.util.Arrays.asList("import_client_zip","prepare_dotnet","pull_compile","restore_world").contains(operation)&&(client.alive()||client.busy))throw new IOException("Stop the client before changing its files or world");
                            JSONObject response=runtime.request(operation,args);if(!response.getBoolean("ok"))throw new IOException(response.optString("error"));result=response.get("result");
                        }
                }
                reply(id,result,null);
            }catch(Exception e){runtime.recordFailure(operation,e);reply(id,null,e);}
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
        Uri uri=data.getData();service();submit(()->{File temp=null;
            try{
                if(request==EXPORT){try(InputStream in=new FileInputStream(exportFile(path));OutputStream out=getContentResolver().openOutputStream(uri,"wt")){if(out==null)throw new IOException("Cannot write destination");byte[] b=new byte[1024*1024];int n;while((n=in.read(b))!=-1)out.write(b,0,n);}reply(id,new JSONObject().put("message","File exported"),null);return;}
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
                        JSONObject response=runtime.request(kind.equals("world")?"restore_world":"import_client_zip",new JSONObject().put("file",temp.getName()));
                        if(!response.getBoolean("ok"))throw new IOException(response.optString("error"));reply(id,response.get("result"),null);temp=null;
                    }
                }
            }catch(Exception e){runtime.recordFailure("import_export",e);reply(id,null,e);}finally{if(temp!=null)temp.delete();}
        });
    }
    @Override public void onBackPressed(){super.onBackPressed();}
    @Override protected void onDestroy(){if(controller!=null)controller.close();if(web!=null){web.removeJavascriptInterface("Memento");web.destroy();web=null;}tasks.shutdown();super.onDestroy();}
}
