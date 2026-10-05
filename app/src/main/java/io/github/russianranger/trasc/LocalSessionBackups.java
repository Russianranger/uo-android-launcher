package io.github.russianranger.trasc;

import org.json.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Complete session archives stay exportable with both runtimes closed. */
final class LocalSessionBackups {
    private static final String NAME="memento-session-(before-restore-)?[0-9]+-[a-f0-9]{8}\\.zip";
    static File createPath(File work,boolean beforeRestore)throws IOException {
        File exports=new File(work,"exports");
        if(!exports.isDirectory()&&!exports.mkdirs())throw new IOException("Cannot create session backup folder");
        return new File(exports,"memento-session-"+(beforeRestore?"before-restore-":"")+System.currentTimeMillis()+"-"+UUID.randomUUID().toString().substring(0,8)+".zip");
    }
    static File archive(File work,String relative)throws IOException {
        boolean exported=relative.startsWith("exports/")&&relative.substring(8).matches(NAME);
        boolean imported=relative.matches("[0-9a-f-]{36}\\.zip");
        if(!exported&&!imported)throw new IOException("Select a complete session backup");
        File selected=TarExtractor.path(work,exported?relative:"incoming/"+relative);
        if(!Files.isRegularFile(selected.toPath(),LinkOption.NOFOLLOW_LINKS))throw new IOException("This session backup is no longer available");
        return selected;
    }
    static JSONObject inventory(File work)throws Exception {
        File[] files=new File(work,"exports").listFiles();List<File> backups=new ArrayList<>();
        if(files!=null)for(File file:files)if(file.getName().matches(NAME)){
            try{backups.add(archive(work,"exports/"+file.getName()));}catch(IOException ignored){}
        }
        backups.sort(Comparator.comparingLong(File::lastModified).reversed().thenComparing(File::getName));
        JSONArray entries=new JSONArray();long total=0;
        for(File file:backups){
            total+=file.length();
            JSONObject entry=new JSONObject().put("file","exports/"+file.getName()).put("name",file.getName())
                .put("bytes",file.length()).put("created_at",file.lastModified()/1000.0)
                .put("reason",file.getName().contains("before-restore")?"Before session restore":"Complete session backup");
            try{entry.put("exported_at",ClientRuntime.json(new File(work,"backups/exported-"+file.getName()+".json")).getDouble("exported_at"));}catch(Exception ignored){}
            entries.put(entry);
        }
        return new JSONObject().put("entries",entries).put("total_bytes",total);
    }
    static void markExported(File work,String relative)throws Exception {
        if(!relative.startsWith("exports/")||!relative.substring(8).matches(NAME))return;
        File selected=archive(work,relative);
        RuntimeManager.write(new File(work,"backups/exported-"+selected.getName()+".json"),new JSONObject().put("exported_at",System.currentTimeMillis()/1000.0).toString());
    }
}
