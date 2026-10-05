package io.github.russianranger.trasc;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;

public final class SessionArchiveHostTest {
    interface Checked {void run()throws Exception;}
    static final SessionArchive.Progress QUIET=text->{};
    static void check(boolean condition,String message){if(!condition)throw new AssertionError(message);}
    static void rejected(Checked work,String message)throws Exception {
        try{work.run();throw new AssertionError("Accepted "+message);}catch(IOException expected){}
    }
    static void write(Path root,String path,String text)throws Exception {
        Path file=root.resolve(path);Files.createDirectories(file.getParent());Files.writeString(file,text);SessionArchive.chmod(file,0640);
    }
    static void runtime(Path home,String path,boolean client)throws Exception {
        write(home,path+"/etc/"+(client?"memento-client-runtime.json":"trasc-runtime.json"),client?"{\"format\":2,\"architecture\":\"arm64\",\"runtime\":\"fex-arm64ec-1\"}":"{\"format\":1,\"architecture\":\"arm64\"}");
        String[] binaries=client?new String[]{"usr/bin/python3.11","usr/bin/Xtigervnc","opt/wine/bin/wine","opt/wine/bin/wineserver","opt/wine/lib/wine/aarch64-windows/libarm64ecfex.dll","opt/wine/lib/wine/aarch64-windows/libwow64fex.dll"}:new String[]{"usr/bin/python3.11","usr/bin/git","usr/bin/apt-get"};
        for(String name:binaries){write(home,path+"/"+name,"test executable: "+name);SessionArchive.chmod(home.resolve(path+"/"+name),0755);}
    }
    static void fixture(Path home)throws Exception {
        runtime(home,"rootfs",false);runtime(home,"work/client/runtime-fex-v1",true);
        write(home,"rootfs/var/lib/dpkg/info/test:arm64.list","installed Mono package state");
        write(home,"rootfs/var/cache/apt/download.deb","cache excluded");write(home,"rootfs/var/log/apt/history.log","log excluded");
        write(home,"rootfs/run/guest.pid","PID excluded");write(home,"work/client/runtime-fex-v1/tmp/guest.tmp","tmp excluded");
        Files.createSymbolicLink(home.resolve("rootfs/bin"),Path.of("usr/bin"));
        Files.createSymbolicLink(home.resolve("rootfs/usr/bin/python3"),Path.of("python3.11"));
        Files.createLink(home.resolve("rootfs/usr/bin/git-copy"),home.resolve("rootfs/usr/bin/git"));
        for(String path:new String[]{"work/server/Saves/world.bin","work/server/Info/settings.cfg","work/server/Backups/first/world.bin","work/server/WorldLinux.exe","work/server-source/World/Source/source.cs","work/server-source/realm-source.json","work/source/.git/config","work/client/current/Client/settings.json","work/client/current/Client/Profiles/player.json","work/client/current/Client/assets/tiledata.mul","work/client/dotnet/dotnet.exe","work/client/prefix-fex-v1/system.reg","work/client/prefix-fex-v1/.memento-registry-last-good/system.reg","work/client/launch-options.json","work/client/controller.json","work/backups/settings-last-change.json"})write(home,path,"persistent bytes: "+path);
        Files.createDirectories(home.resolve("work/server/Saves/empty"));
        Files.createDirectories(home.resolve("work/client/prefix-fex-v1/dosdevices"));Files.createDirectories(home.resolve("work/client/prefix-fex-v1/drive_c"));
        Files.createSymbolicLink(home.resolve("work/client/prefix-fex-v1/dosdevices/c:"),Path.of("../drive_c"));
        Files.createSymbolicLink(home.resolve("work/client/prefix-fex-v1/dosdevices/z:"),Path.of("/"));
        Files.createDirectories(home.resolve("work/server/Data/Files"));
        Files.createSymbolicLink(home.resolve("work/server/Data/Files/tiledata.mul"),Path.of("/work/client/current/Client/assets/tiledata.mul"));
        Files.createSymbolicLink(home.resolve("work/source/local-client"),home.resolve("work/client/current"));
        write(home,"work/server/Info/readonly.cfg","read-only bytes");SessionArchive.chmod(home.resolve("work/server/Info/readonly.cfg"),0444);
        for(String path:new String[]{"work/exports/older.zip","work/incoming/import.zip","work/run/api-token","work/logs/runtime.log","work/server-staging/stale.cs","work/source-staging/stale.cs","work/source-export/stale.cs","work/sources/git-cache/object","work/client/current.previous/stale.txt","work/client/runtime-fex-v1.previous/stale.txt","work/backups/metadata-memento-world-123.zip.json","work/backups/exported-memento-world-123.zip.json"})write(home,path,"transient bytes: "+path);
    }
    static final class MemoryPreferences implements SessionArchive.Preferences {
        String value;boolean failOnce;MemoryPreferences(String value){this.value=value;}
        public String read(){return value;}
        public void write(String next)throws IOException {if(failOnce){failOnce=false;throw new IOException("injected preference failure");}value=next;}
    }
    static LinkedHashMap<String,byte[]> members(File archive)throws Exception {
        LinkedHashMap<String,byte[]> result=new LinkedHashMap<>();try(ZipFile zip=new ZipFile(archive)) {
            for(var entries=zip.entries();entries.hasMoreElements();) {ZipEntry entry=entries.nextElement();try(InputStream in=zip.getInputStream(entry)){result.put(entry.getName(),in.readAllBytes());}}
        }return result;
    }
    static File zip(Path path,Map<String,byte[]> members)throws Exception {
        try(ZipOutputStream zip=new ZipOutputStream(Files.newOutputStream(path))) {for(var entry:members.entrySet()){zip.putNextEntry(new ZipEntry(entry.getKey()));zip.write(entry.getValue());zip.closeEntry();}}return path.toFile();
    }
    static String encoded(String text){return Base64.getEncoder().encodeToString(text.getBytes(StandardCharsets.UTF_8));}
    static void appendIndex(Map<String,byte[]> members,String line)throws Exception {
        String index=new String(members.get(SessionArchive.INDEX),StandardCharsets.UTF_8);members.put(SessionArchive.INDEX,(index+line+"\n").getBytes(StandardCharsets.UTF_8));
        Properties manifest=new Properties();manifest.load(new ByteArrayInputStream(members.get(SessionArchive.MANIFEST)));manifest.setProperty("entries",String.valueOf(Integer.parseInt(manifest.getProperty("entries"))+1));
        ByteArrayOutputStream out=new ByteArrayOutputStream();manifest.store(out,"");members.put(SessionArchive.MANIFEST,out.toByteArray());
    }
    static void invalidZip(Path directory,File archive,String label,java.util.function.Consumer<Map<String,byte[]>> mutate)throws Exception {
        Map<String,byte[]> entries=members(archive);mutate.accept(entries);File bad=zip(directory.resolve(label+".zip"),entries);
        rejected(()->SessionArchive.preview(bad),label);
        Path stage=directory.resolve(label+"-stage");rejected(()->SessionArchive.restore(bad,stage.toFile(),QUIET),label+" staged restore");check(!Files.exists(stage),"Invalid archive left staging: "+label);
    }
    static void unsafeEntry(Path directory,File archive,String label,String name,String link)throws Exception {
        Map<String,byte[]> entries=members(archive);appendIndex(entries,"L\t0\t0\t-\t"+encoded(name)+"\t"+encoded(link));
        File bad=zip(directory.resolve(label+".zip"),entries);rejected(()->SessionArchive.preview(bad),label);
    }
    static void roundtrip(Path base,Path home,File archive,String prefs)throws Exception {
        Properties preview=SessionArchive.preview(archive);check(preview.getProperty("format").equals(SessionArchive.FORMAT),"Wrong archive identity");
        check(Long.parseLong(preview.getProperty("bytes"))==archive.length(),"Wrong archive bytes");check(SessionArchive.archivedPreferences(archive).equals(prefs),"UI snapshot lost");
        Path restored=base.resolve("fresh");Files.createDirectory(restored);Path stage=restored.resolve("session-stage");SessionArchive.restore(archive,stage.toFile(),QUIET);
        for(String path:new String[]{"rootfs/etc/trasc-runtime.json","work/server/Saves/world.bin","work/server/Backups/first/world.bin","work/server-source/realm-source.json","work/source/.git/config","work/client/current/Client/Profiles/player.json","work/client/controller.json","work/client/dotnet/dotnet.exe","work/client/prefix-fex-v1/system.reg","work/client/runtime-fex-v1/opt/wine/bin/wine","work/backups/settings-last-change.json"})check(Arrays.equals(Files.readAllBytes(home.resolve(path)),Files.readAllBytes(stage.resolve(path))),"Roundtrip lost "+path);
        check(Files.isDirectory(stage.resolve("work/server/Saves/empty")),"Empty save directory lost");
        check(Files.readSymbolicLink(stage.resolve("rootfs/bin")).equals(Path.of("usr/bin")),"Linux symlink lost");
        check(Files.readSymbolicLink(stage.resolve("work/client/prefix-fex-v1/dosdevices/c:")).equals(Path.of("../drive_c")),"Colon/prefix link lost");
        check(Files.readSymbolicLink(stage.resolve("work/client/prefix-fex-v1/dosdevices/z:")).equals(Path.of("/")),"Wine guest-root link lost");
        check(Files.readSymbolicLink(stage.resolve("work/server/Data/Files/tiledata.mul")).toString().startsWith("/work/"),"Guest assets link lost");
        check(!Files.readSymbolicLink(stage.resolve("work/source/local-client")).isAbsolute(),"Android home symlink was not made portable");
        check(SessionArchive.mode(stage.resolve("rootfs/usr/bin/git"))==0755,"Executable mode lost");check(SessionArchive.mode(stage.resolve("work/server/Info/readonly.cfg"))==0444,"Read-only mode lost");
        check(!Files.isSameFile(stage.resolve("rootfs/usr/bin/git"),stage.resolve("rootfs/usr/bin/git-copy")),"Hard links were recreated");
        for(String path:new String[]{"work/exports","work/incoming","work/run","work/logs","work/server-staging","work/sources","work/client/current.previous","rootfs/var/cache/apt/download.deb","rootfs/var/log/apt/history.log","rootfs/run/guest.pid","work/client/runtime-fex-v1/tmp/guest.tmp","work/backups/metadata-memento-world-123.zip.json"})check(!Files.exists(stage.resolve(path),LinkOption.NOFOLLOW_LINKS),"Archived excluded content: "+path);
        MemoryPreferences preferences=new MemoryPreferences("{}");SessionArchive.activate(restored.toFile(),stage.toFile(),preferences,QUIET);
        check(preferences.value.equals(prefs),"Fresh install preferences missing");check(Files.isRegularFile(restored.resolve("rootfs/etc/trasc-runtime.json")),"Fresh install needs an existing runtime");
        check(!Files.exists(restored.resolve(SessionArchive.TRANSACTION)),"Committed transaction not cleaned");
    }
    static void rollback(Path base,File archive)throws Exception {
        Path home=base.resolve("rollback");Files.createDirectory(home);fixture(home);write(home,"work/server/Saves/world.bin","original world");
        String before="{\"launch\":{\"renderer\":\"original\"}}";MemoryPreferences preferences=new MemoryPreferences(before);Path stage=home.resolve("stage");
        SessionArchive.restore(archive,stage.toFile(),QUIET);preferences.failOnce=true;
        rejected(()->SessionArchive.activate(home.toFile(),stage.toFile(),preferences,QUIET),"failing preference activation");
        check(Files.readString(home.resolve("work/server/Saves/world.bin")).equals("original world"),"Failure replaced the original world");check(preferences.value.equals(before),"Failure replaced preferences");
        check(Files.exists(home.resolve("work/exports/older.zip")),"Failure lost an app backup");check(Files.exists(home.resolve("work/incoming/import.zip")),"Failure lost a pending import");
        check(!Files.exists(home.resolve(SessionArchive.TRANSACTION)),"Rollback did not finish");
        // Simulate process death at each filesystem/preferences boundary. Errors
        // deliberately bypass ordinary exception rollback, like a killed process.
        for(String point:new String[]{"Preserving","Restoring rootfs","Restoring work","Restoring launcher"}) {
            SessionArchive.restore(archive,stage.toFile(),QUIET);
            try {SessionArchive.activate(home.toFile(),stage.toFile(),preferences,text->{if(text.startsWith(point))throw new AssertionError("simulated process death");});throw new AssertionError("Crash hook did not fire");}
            catch(AssertionError expected){check(expected.getMessage().equals("simulated process death"),expected.getMessage());}
            check(Files.exists(home.resolve(SessionArchive.TRANSACTION)),"Interrupted restore lost journal");
            SessionArchive.recover(home.toFile(),preferences);SessionArchive.recover(home.toFile(),preferences);
            check(Files.readString(home.resolve("work/server/Saves/world.bin")).equals("original world"),"Interrupted restore lost original world at "+point);
            check(preferences.value.equals(before),"Interrupted restore lost original prefs at "+point);
            check(Files.exists(home.resolve("work/exports/older.zip")),"Interrupted restore lost exports at "+point);
            check(Files.exists(home.resolve("work/incoming/import.zip")),"Interrupted restore lost incoming at "+point);
        }
        SessionArchive.restore(archive,stage.toFile(),QUIET);SessionArchive.activate(home.toFile(),stage.toFile(),preferences,QUIET);
        check(!Files.readString(home.resolve("work/server/Saves/world.bin")).equals("original world"),"Valid restore was not activated");
        for(String path:new String[]{"work/exports/older.zip","work/incoming/import.zip","work/logs/runtime.log","work/backups/metadata-memento-world-123.zip.json"})check(Files.exists(home.resolve(path)),"Activation lost retained "+path);
    }
    static void durableDecisionRecovery(Path base,File archive)throws Exception {
        Path home=base.resolve("commit-recovery");Files.createDirectory(home);fixture(home);Path stage=home.resolve("stage");SessionArchive.restore(archive,stage.toFile(),QUIET);
        Path transaction=home.resolve(SessionArchive.TRANSACTION);Files.createDirectory(transaction);
        for(String component:new String[]{"rootfs","work"}) {
            Files.move(home.resolve(component),transaction.resolve("old-"+component));Files.move(stage.resolve(component),home.resolve(component));
        }
        for(String retained:new String[]{"exports","incoming","logs"})Files.move(transaction.resolve("old-work/"+retained),home.resolve("work/"+retained));
        Properties journal=new Properties();journal.setProperty("format",SessionArchive.FORMAT);journal.setProperty("phase","committed");journal.setProperty("stage","stage");journal.setProperty("had_rootfs","true");journal.setProperty("had_work","true");
        try(OutputStream out=Files.newOutputStream(transaction.resolve("journal.properties"))){journal.store(out,"");}
        // Cleanup may have deleted the old preferences or one of the old trees
        // before power/process loss. The committed decision remains authoritative.
        SessionArchive.remove(transaction.resolve("old-rootfs"));
        MemoryPreferences preferences=new MemoryPreferences("{\"restored\":true}");SessionArchive.recover(home.toFile(),preferences);
        check(preferences.value.equals("{\"restored\":true}"),"Committed recovery rewrote preferences");check(Files.exists(home.resolve("work/server/Saves/world.bin")),"Committed cleanup lost restored world");
        check(Files.exists(home.resolve("work/exports/older.zip")),"Committed cleanup lost retained archive");check(!Files.exists(transaction),"Committed cleanup did not resume");
        // The same rule applies when rollback finished but its cleanup was killed.
        Files.createDirectory(transaction);journal.setProperty("phase","rolled_back");try(OutputStream out=Files.newOutputStream(transaction.resolve("journal.properties"))){journal.store(out,"");}
        SessionArchive.recover(home.toFile(),preferences);check(preferences.value.equals("{\"restored\":true}"),"Completed rollback cleanup required deleted preferences");
        check(!Files.exists(transaction),"Rolled-back cleanup did not finish");
        Files.createDirectory(transaction);Files.createDirectory(transaction.resolve("old-work"));
        rejected(()->SessionArchive.recover(home.toFile(),preferences),"missing recovery journal with previous data");check(Files.exists(transaction.resolve("old-work")),"Corrupt journal discarded previous data");
    }
    static void malicious(Path base,Path original,File archive)throws Exception {
        Path bad=base.resolve("bad");Files.createDirectory(bad);
        unsafeEntry(bad,archive,"traversal","work/../outside","../outside");unsafeEntry(bad,archive,"absolute-path","/etc/passwd","../outside");
        unsafeEntry(bad,archive,"windows-path","C:/outside","../outside");unsafeEntry(bad,archive,"backslash","work/unsafe\\outside","../outside");
        unsafeEntry(bad,archive,"absolute-link","work/source/unsafe","/etc/passwd");unsafeEntry(bad,archive,"relative-escape","work/source/unsafe","../../../outside");
        unsafeEntry(bad,archive,"host-link","rootfs/root/unsafe","/data/user/0/other/files/secret");unsafeEntry(bad,archive,"unknown-component","other/file","../outside");
        unsafeEntry(bad,archive,"transient-component","work/run/api-token","../outside");
        invalidZip(bad,archive,"corrupt-bytes",map->map.put("work/server/Saves/world.bin","changed file bytes".getBytes(StandardCharsets.UTF_8)));
        invalidZip(bad,archive,"unexpected-member",map->map.put("unindexed-member.txt",new byte[]{1}));
        invalidZip(bad,archive,"index-line-limit",map->map.put(SessionArchive.INDEX,("A".repeat(40000)+"\n").getBytes(StandardCharsets.UTF_8)));
        invalidZip(bad,archive,"duplicate-index",map->{try {String line=new String(map.get(SessionArchive.INDEX),StandardCharsets.UTF_8).split("\n")[0];appendIndex(map,line);}catch(Exception error){throw new RuntimeException(error);}});
        invalidZip(bad,archive,"missing-runtime",map->map.remove("rootfs/etc/trasc-runtime.json"));
        invalidZip(bad,archive,"unsupported-runtime",map->map.put("rootfs/etc/trasc-runtime.json","{\"format\":99,\"architecture\":\"arm64\"}".getBytes(StandardCharsets.UTF_8)));
        // A link with descendants is forbidden even when it points within work.
        Map<String,byte[]> parents=members(archive);String parentIndex=new String(parents.get(SessionArchive.INDEX),StandardCharsets.UTF_8);
        String[] rows=parentIndex.split("\n");for(int i=0;i<rows.length;i++)if(rows[i].split("\t",-1)[4].equals(encoded("work/server/Saves")))rows[i]="L\t0\t0\t-\t"+encoded("work/server/Saves")+"\t"+encoded("../Info");
        parents.put(SessionArchive.INDEX,(String.join("\n",rows)+"\n").getBytes(StandardCharsets.UTF_8));
        File parent=zip(bad.resolve("link-parent.zip"),parents);rejected(()->SessionArchive.preview(parent),"link as indexed parent");
        // Java's writer prevents duplicate members, so edit equal-length names
        // in the finished local/central headers to exercise the reader's check.
        Map<String,byte[]> duplicates=members(archive);String originalName="work/server/Saves/world.bin",duplicateName="work/server/Saves/w0rld.bin";
        duplicates.put(duplicateName,duplicates.get(originalName));Path duplicatePath=bad.resolve("duplicate-member.zip");zip(duplicatePath,duplicates);
        byte[] duplicateBytes=Files.readAllBytes(duplicatePath),oldName=duplicateName.getBytes(StandardCharsets.UTF_8),newName=originalName.getBytes(StandardCharsets.UTF_8);
        for(int i=0;i<=duplicateBytes.length-oldName.length;i++) {boolean match=true;for(int j=0;j<oldName.length;j++)if(duplicateBytes[i+j]!=oldName[j]){match=false;break;}if(match)System.arraycopy(newName,0,duplicateBytes,i,newName.length);}
        Files.write(duplicatePath,duplicateBytes);rejected(()->SessionArchive.preview(duplicatePath.toFile()),"duplicate ZIP member");
        byte[] zipBytes=Files.readAllBytes(archive.toPath());Path truncated=bad.resolve("truncated.zip");Files.write(truncated,Arrays.copyOf(zipBytes,zipBytes.length-100));rejected(()->SessionArchive.preview(truncated.toFile()),"truncated archive");
        File refused=original.resolve("work/source/recursive.zip").toFile();rejected(()->SessionArchive.create(original.toFile(),refused,"test","{}",QUIET),"archive self-inclusion");check(!refused.exists(),"Self-inclusion left an archive");
        // A native symlink outside the captured session cannot be silently copied.
        Files.createSymbolicLink(original.resolve("work/source/host-secret"),Path.of("/etc/passwd"));
        File unsafe=original.resolve("work/exports/unsafe.zip").toFile();rejected(()->SessionArchive.create(original.toFile(),unsafe,"test","{}",QUIET),"outside backup symlink");check(!unsafe.exists(),"Unsafe backup left partial archive");Files.delete(original.resolve("work/source/host-secret"));
        File unfinished=original.resolve("work/exports/interrupted.zip").toFile();rejected(()->SessionArchive.create(original.toFile(),unfinished,"test","{}",text->{throw new IOException("cancelled");}),"interrupted backup");check(!unfinished.exists(),"Interrupted backup left partial archive");
    }
    public static void main(String[] args)throws Exception {
        Path base=Files.createTempDirectory("memento-session-test");
        try {
            Path home=base.resolve("original");Files.createDirectory(home);fixture(home);
            String prefs="{\"launch\":{\"renderer\":\"turnip\"},\"source\":{\"source\":\"custom\",\"repository\":\"https://github.com/example/server.git\",\"ref\":\"main\"}}";
            File archive=home.resolve("work/exports/memento-session-test.zip").toFile();SessionArchive.create(home.toFile(),archive,"test",prefs,QUIET);
            roundtrip(base,home,archive,prefs);rollback(base,archive);durableDecisionRecovery(base,archive);malicious(base,home,archive);
            // Android files paths can contain /data/data aliases. Resolve the home
            // once, then preserve its contents without following guest symlinks.
            Path alias=base.resolve("home-alias");Files.createSymbolicLink(alias,home);
            File aliased=alias.resolve("work/exports/aliased.zip").toFile();SessionArchive.create(alias.toFile(),aliased,"test",prefs,QUIET);SessionArchive.preview(aliased);
            System.out.println("Complete sessions: all persistent components, bytes/modes/links, fresh install, retained backups, invalid archives, interruption rollback and preferences passed");
        }finally{SessionArchive.remove(base);}
    }
}
