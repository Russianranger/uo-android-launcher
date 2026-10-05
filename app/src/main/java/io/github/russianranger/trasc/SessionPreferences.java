package io.github.russianranger.trasc;

import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.UUID;

/** UI choices are portable JSON, separate from the device's WebView database. */
final class SessionPreferences implements SessionArchive.Preferences {
    private final File file;
    SessionPreferences(File home){file=new File(home,".session-preferences.json");}
    JSONObject state()throws IOException {
        if(!Files.exists(file.toPath(),LinkOption.NOFOLLOW_LINKS))return new JSONObject();
        if(!Files.isRegularFile(file.toPath(),LinkOption.NOFOLLOW_LINKS)||file.length()>262144)throw new IOException("Invalid session preferences");
        try{return new JSONObject(new String(Files.readAllBytes(file.toPath()),StandardCharsets.UTF_8));}
        catch(Exception error){throw new IOException("Cannot read session preferences",error);}
    }
    public String read()throws IOException {JSONObject value=state();JSONObject ui=value.optJSONObject("ui");return ui==null?"{}":ui.toString();}
    public void write(String value)throws IOException {
        Path temporary=file.toPath().resolveSibling(file.getName()+".pending");
        try{
            if(value.length()>131072)throw new IOException("Session preferences exceed limits");
            JSONObject ui=new JSONObject(value);
            JSONObject state=new JSONObject().put("ui",ui).put("revision",UUID.randomUUID().toString());
            byte[] bytes=state.toString().getBytes(StandardCharsets.UTF_8);
            Files.deleteIfExists(temporary);
            try(OutputStream output=Files.newOutputStream(temporary,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)){
                output.write(bytes);output.flush();
            }
            try(RandomAccessFile synced=new RandomAccessFile(temporary.toFile(),"rw")){synced.getFD().sync();}
            try{Files.move(temporary,file.toPath(),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}
            catch(AtomicMoveNotSupportedException unsupported){Files.move(temporary,file.toPath(),StandardCopyOption.REPLACE_EXISTING);}
            SessionArchive.syncDirectory(file.toPath().getParent());
        }catch(IOException error){throw error;}
        catch(Exception error){throw new IOException("Cannot restore session preferences",error);}
        finally{Files.deleteIfExists(temporary);}
    }
}
