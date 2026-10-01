package io.github.russianranger.trasc;

import org.json.*;
import java.io.*;
import java.util.*;

/** App-private save archives remain discoverable while the realm runtime is off. */
final class LocalBackups {
    static boolean saveArchive(File file){return file.getName().matches("memento-world-[0-9]+\\.zip")&&file.isFile();}
    static File safe(File work,String name)throws IOException {
        if(!name.matches("memento-world-[0-9]+\\.zip"))throw new IOException("Select a save-data backup");
        File exports=new File(work,"exports").getCanonicalFile(),file=new File(exports,name);
        if(!file.getCanonicalFile().equals(file.getAbsoluteFile())||!file.isFile())throw new IOException("This backup is no longer available");
        return file;
    }
    static JSONObject inventory(File work)throws Exception {
        File[] files=new File(work,"exports").listFiles();List<File> backups=new ArrayList<>();
        if(files!=null)for(File file:files)if(saveArchive(file)){
            try{safe(work,file.getName());backups.add(file);}catch(IOException ignored){}
        }
        backups.sort(Comparator.comparingLong(File::lastModified).reversed().thenComparing(File::getName,Comparator.reverseOrder()));
        JSONArray entries=new JSONArray();long total=0;
        for(File file:backups){
            String name=file.getName();total+=file.length();
            JSONObject entry=new JSONObject().put("name",name).put("file","exports/"+name).put("bytes",file.length()).put("created_at",file.lastModified()/1000.0);
            File metadata=new File(work,"backups/metadata-"+name+".json"),exported=new File(work,"backups/exported-"+name+".json");
            try{JSONObject info=ClientRuntime.json(metadata);entry.put("reason",info.optString("reason","Save-data backup"));}catch(Exception ignored){entry.put("reason","Save-data backup");}
            try{entry.put("exported_at",ClientRuntime.json(exported).getDouble("exported_at"));}catch(Exception ignored){}
            entries.put(entry);
        }
        return new JSONObject().put("entries",entries).put("total_bytes",total);
    }
    static void markExported(File work,String path)throws Exception {
        if(!path.startsWith("exports/"))return;
        String name=path.substring("exports/".length());
        if(!name.matches("memento-world-[0-9]+\\.zip"))return;
        safe(work,name);
        RuntimeManager.write(new File(work,"backups/exported-"+name+".json"),new JSONObject().put("exported_at",System.currentTimeMillis()/1000.0).toString());
    }
}
