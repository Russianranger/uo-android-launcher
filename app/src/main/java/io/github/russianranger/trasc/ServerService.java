package io.github.russianranger.trasc;

import android.app.*;
import android.content.*;
import android.os.*;
import org.json.*;
import java.io.IOException;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ServerService extends Service {
    static final String STOP="io.github.russianranger.trasc.STOP";
    private PowerManager.WakeLock lock;
    private final ExecutorService shutdown=Executors.newSingleThreadExecutor();
    private final AtomicBoolean stopping=new AtomicBoolean();
    @Override public void onCreate(){
        super.onCreate();
        NotificationManager nm=getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel("server","Local server",NotificationManager.IMPORTANCE_LOW));
        PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop=PendingIntent.getService(this,1,new Intent(this,ServerService.class).setAction(STOP),PendingIntent.FLAG_IMMUTABLE);
        Notification n=new Notification.Builder(this,"server").setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("UO Memento").setContentText("Local runtime active · tap to manage")
            .setContentIntent(open).addAction(new Notification.Action.Builder(null,"Shut down",stop).build()).setOngoing(true).build();
        startForeground(1,n);
        lock=((PowerManager)getSystemService(POWER_SERVICE)).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"Memento:runtime");lock.acquire();
    }
    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(intent!=null&&STOP.equals(intent.getAction())&&stopping.compareAndSet(false,true))shutdown.execute(()->{
            RuntimeManager runtime=RuntimeManager.get(this);ClientRuntime client=ClientRuntime.get(this);
            boolean guarded=false;
            try{
                runtime.session.beginShutdown();guarded=true;
                closeSession(runtime,client);
            }catch(InterruptedException e){Thread.currentThread().interrupt();}
            catch(Exception e){runtime.session.status=e.getMessage();runtime.status=e.getMessage();runtime.recordFailure("notification_session_close",e);}
            finally{if(guarded)runtime.session.finish();}
            new Handler(Looper.getMainLooper()).post(()->{
                stopping.set(false);
                if(!client.alive()&&!runtime.alive())stopSelf();
            });
        });
        return START_NOT_STICKY;
    }
    static JSONObject closeSession(RuntimeManager runtime,ClientRuntime client)throws Exception {
        SessionShutdown.run(new SessionShutdown.Host(){
            public void progress(String message)throws Exception {runtime.session.progress(message);}
            public void stopClient()throws Exception {client.stop();}
            public void awaitRealmTask()throws Exception {waitForRealmTask(runtime);}
            public void closeRuntime()throws Exception {runtime.stop();}
        });
        return new JSONObject().put("message",runtime.session.status);
    }
    private static void waitForRealmTask(RuntimeManager runtime)throws Exception {
        long deadline=SystemClock.elapsedRealtime()+660000;
        while(runtime.alive()){
            JSONObject response=runtime.request("state",new JSONObject());
            if(!response.getBoolean("ok"))throw new IOException(response.optString("error"));
            JSONArray jobs=response.getJSONObject("result").getJSONArray("jobs");boolean pending=false;
            for(int i=0;i<jobs.length();i++){
                String status=jobs.getJSONObject(i).optString("status");
                if("queued".equals(status)||"running".equals(status)){pending=true;break;}
            }
            if(!pending)return;
            runtime.session.status="Waiting for the current server task, then saving and closing…";
            if(SystemClock.elapsedRealtime()>=deadline)throw new IOException("The server task is still busy. It has been left running; retry Shut down when the task finishes.");
            Thread.sleep(500);
        }
    }
    @Override public void onDestroy(){shutdown.shutdown();if(lock!=null&&lock.isHeld())lock.release();super.onDestroy();}
    @Override public IBinder onBind(Intent intent){return null;}
}
