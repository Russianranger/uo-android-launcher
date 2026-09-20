package io.github.russianranger.trasc;

import android.app.*;
import android.content.*;
import android.os.*;
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
            try{client.stop();}catch(Exception e){runtime.recordFailure("notification_client_stop",e);}
            try{runtime.stop();}catch(Exception e){runtime.status=e.getMessage();runtime.recordFailure("notification_runtime_stop",e);}
            new Handler(Looper.getMainLooper()).post(()->{
                stopping.set(false);
                if(!client.alive()&&!runtime.alive())stopSelf();
            });
        });
        return START_NOT_STICKY;
    }
    @Override public void onDestroy(){shutdown.shutdown();if(lock!=null&&lock.isHeld())lock.release();super.onDestroy();}
    @Override public IBinder onBind(Intent intent){return null;}
}
