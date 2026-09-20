package io.github.russianranger.trasc;

import android.app.*;
import android.content.Context;
import android.os.Build;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

/** Own-package exit history, capped at five records and 256 KiB per trace. */
final class AndroidExitDiagnostics {
    static void collect(Context context,File work)throws Exception {
        if(Build.VERSION.SDK_INT<30)return;
        JSONArray records=new JSONArray();
        ActivityManager manager=context.getSystemService(ActivityManager.class);
        for(ApplicationExitInfo exit:manager.getHistoricalProcessExitReasons(context.getPackageName(),0,5)){
            JSONObject record=new JSONObject().put("timestamp",exit.getTimestamp()).put("process",exit.getProcessName())
                .put("reason",exit.getReason()).put("status",exit.getStatus()).put("description",exit.getDescription())
                .put("pid",exit.getPid()).put("pss_kib",exit.getPss()).put("rss_kib",exit.getRss());
            try(InputStream stream=exit.getTraceInputStream()){
                if(stream!=null){
                    ByteArrayOutputStream trace=new ByteArrayOutputStream();byte[] buffer=new byte[8192];int remaining=256*1024;
                    while(remaining>0){int n=stream.read(buffer,0,Math.min(buffer.length,remaining));if(n<0)break;trace.write(buffer,0,n);remaining-=n;}
                    record.put("trace_truncated",remaining==0);
                    if(exit.getReason()==ApplicationExitInfo.REASON_CRASH_NATIVE)
                        record.put("tombstone_protobuf_base64",android.util.Base64.encodeToString(trace.toByteArray(),android.util.Base64.NO_WRAP));
                    else record.put("trace",new String(trace.toByteArray(),StandardCharsets.UTF_8));
                }
            }catch(IOException e){record.put("trace_error",e.toString());}
            records.put(record);
        }
        Path target=LocalLogs.checked(work.toPath(),"logs/android-exit.log");Files.createDirectories(target.getParent());
        Path temp=Files.createTempFile(target.getParent(),"android-exit-",".tmp");
        try{Files.write(temp,new JSONObject().put("collected_utc",java.time.Instant.now()).put("exits",records).toString(2).getBytes(StandardCharsets.UTF_8));
            Files.move(temp,target,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
        }finally{Files.deleteIfExists(temp);}
    }
}
