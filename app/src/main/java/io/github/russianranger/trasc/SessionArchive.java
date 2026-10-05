package io.github.russianranger.trasc;

import java.io.*;
import java.nio.charset.*;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.nio.file.attribute.*;
import java.security.*;
import java.util.*;
import java.util.regex.*;
import java.util.zip.*;

/** Offline, streamed ZIP64 snapshots. Call only after a confirmed clean shutdown.
 * The transport follows TRASC's indexed session format, with a separate UO format
 * identity. Hard links become independent files; Linux links are never followed.
 * The durable activation journal restores both trees and preferences after a crash.
 */
final class SessionArchive {
    interface Progress {void update(String text)throws IOException;}
    interface Preferences {
        String read()throws IOException;
        void write(String json)throws IOException;
    }
    static final long RESERVE=128L*1024*1024, MAX_BYTES=256L*1024*1024*1024;
    static final int MAX_FILES=250000, MAX_INDEX=64*1024*1024, MAX_PREFERENCES=131072;
    static final String MANIFEST="session.properties", INDEX="session-index.tsv";
    static final String FORMAT="uo-memento-session-1", TRANSACTION=".session-restore-transaction";
    static final String PREFERENCES="ui-preferences.json";
    private static final Progress SILENT=text->{};
    private static final String[] RETAINED={"exports","incoming","logs"};
    private static final Set<String> WORK_TRANSIENT=new HashSet<>(Arrays.asList(
        "exports","incoming","run","logs","sources","source-staging","source-export",
        "server-staging","server.previous","restore-staging","restore-deployment"));
    private static final Set<String> CLIENT_TRANSIENT=new HashSet<>(Arrays.asList(
        "current.previous","client-staging","dotnet.previous","dotnet-staging",
        "runtime-fex-v1.previous","runtime-fex-install","prefix-fex-v1.previous"));
    private static final PosixFilePermission[] MODE_BITS={
        PosixFilePermission.OTHERS_EXECUTE,PosixFilePermission.OTHERS_WRITE,PosixFilePermission.OTHERS_READ,
        PosixFilePermission.GROUP_EXECUTE,PosixFilePermission.GROUP_WRITE,PosixFilePermission.GROUP_READ,
        PosixFilePermission.OWNER_EXECUTE,PosixFilePermission.OWNER_WRITE,PosixFilePermission.OWNER_READ};
    private static final class Entry {
        String name,type,hash="-",link="";int mode;long size;
        String line(){return type+"\t"+mode+"\t"+size+"\t"+hash+"\t"+encode(name)+"\t"+encode(link)+"\n";}
    }
    private static final class Inventory {
        final Properties manifest;
        final LinkedHashMap<String,Entry> entries;
        final long bytes;
        Inventory(Properties manifest,LinkedHashMap<String,Entry> entries,long bytes){this.manifest=manifest;this.entries=entries;this.bytes=bytes;}
    }
    private SessionArchive(){}
    private static String encode(String text){return Base64.getEncoder().encodeToString(text.getBytes(StandardCharsets.UTF_8));}
    private static String decode(String text)throws IOException {
        try{return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .decode(java.nio.ByteBuffer.wrap(Base64.getDecoder().decode(text))).toString();}
        catch(IllegalArgumentException|CharacterCodingException error){throw new IOException("Invalid session index encoding",error);}
    }
    private static MessageDigest sha()throws IOException {
        try{return MessageDigest.getInstance("SHA-256");}catch(NoSuchAlgorithmException error){throw new IOException(error);}
    }
    private static String hex(byte[] bytes){StringBuilder out=new StringBuilder();for(byte b:bytes)out.append(String.format(Locale.ROOT,"%02x",b&255));return out.toString();}
    static Path confined(Path root,String name)throws IOException {
        if(name.isEmpty()||name.length()>8192||name.startsWith("/")||name.contains("\\")||name.indexOf('\0')>=0||name.matches("(?s)^[A-Za-z]:.*"))throw new IOException("Unsafe session path: "+name);
        for(String part:name.split("/",-1))if(part.isEmpty()||part.equals(".")||part.equals(".."))throw new IOException("Unsafe session path: "+name);
        Path path=root.resolve(name).normalize();if(!path.startsWith(root))throw new IOException("Session path escapes its destination");return path;
    }
    static int mode(Path path)throws IOException {
        int result=0;Set<PosixFilePermission> actual=Files.getPosixFilePermissions(path,LinkOption.NOFOLLOW_LINKS);
        for(int i=0;i<MODE_BITS.length;i++)if(actual.contains(MODE_BITS[i]))result|=1<<i;return result;
    }
    static void chmod(Path path,int value)throws IOException {
        Set<PosixFilePermission> permissions=EnumSet.noneOf(PosixFilePermission.class);
        for(int i=0;i<MODE_BITS.length;i++)if((value&(1<<i))!=0)permissions.add(MODE_BITS[i]);Files.setPosixFilePermissions(path,permissions);
    }
    private static boolean exists(Path path){return Files.exists(path,LinkOption.NOFOLLOW_LINKS);}
    private static void space(File directory,long needed)throws IOException {
        if(needed<0||needed>directory.getUsableSpace()-RESERVE)throw new IOException("Not enough storage for the complete session. Free space and retry.");
    }
    private static boolean excludedWork(Path relative) {
        if(relative.toString().isEmpty())return false;
        String first=relative.getName(0).toString();if(WORK_TRANSIENT.contains(first))return true;
        if(first.equals("client")&&relative.getNameCount()>1) {
            if(CLIENT_TRANSIENT.contains(relative.getName(1).toString()))return true;
            if(relative.getName(1).toString().equals("runtime-fex-v1")&&relative.getNameCount()>2&&excludedRuntime(relative.subpath(2,relative.getNameCount())))return true;
        }
        // App exports are retained on this device, rather than nested in each new
        // complete snapshot. World/server/Backups is part of the snapshot.
        if(first.equals("backups")&&relative.getNameCount()>1) {
            String name=relative.getName(1).toString();return name.endsWith(".zip")||name.startsWith("metadata-")||name.startsWith("exported-");
        }
        return false;
    }
    private static boolean excludedRuntime(Path relative) {
        if(relative.toString().isEmpty())return false;
        String path=relative.toString();String first=relative.getName(0).toString();
        if(Arrays.asList("tmp","run","proc","sys","dev").contains(first))return relative.getNameCount()>1;
        return path.startsWith("var/cache/")||path.startsWith("var/log/")||path.startsWith("var/tmp/");
    }
    private static boolean excluded(String name)throws IOException {
        if(name.equals("work"))return false;
        if(name.startsWith("work/"))return excludedWork(Paths.get(name.substring(5)));
        if(name.equals("rootfs"))return false;
        if(name.startsWith("rootfs/"))return excludedRuntime(Paths.get(name.substring(7)));
        return !name.equals("configuration/ui.json");
    }
    private static Path destination(Path stage,String name)throws IOException {
        confined(stage,name);
        if(name.equals("configuration/ui.json"))return stage.resolve(PREFERENCES);
        if(!(name.equals("rootfs")||name.startsWith("rootfs/")||name.equals("work")||name.startsWith("work/"))||excluded(name))throw new IOException("Unknown or transient session component: "+name);
        return confined(stage,name);
    }
    /** Validate link targets lexically, without traversing the filesystem. Absolute
     * guest paths are retained for PRoot; links to the original Android home are
     * made relative so moving a snapshot to a fresh installation remains usable.
     */
    private static String backupLink(Path home,Path path,String name)throws IOException {
        Path target=Files.readSymbolicLink(path);
        if(target.isAbsolute()&&target.normalize().startsWith(home))target=path.getParent().relativize(target.normalize());
        String text=target.toString();validateLink(name,text);return text;
    }
    static void validateLink(String name,String link)throws IOException {
        if(link.isEmpty()||link.length()>8192||link.indexOf('\0')>=0||link.contains("\\"))throw new IOException("Invalid session symbolic link: "+name);
        Path target=Paths.get(link),absolute;
        if(target.isAbsolute()) {
            // Absolute paths inside a runtime/prefix have guest-root semantics.
            // A server's asset links refer to the /work PRoot bind mount.
            if(name.startsWith("rootfs/")||name.startsWith("work/client/runtime-fex-v1/")||name.startsWith("work/client/prefix-fex-v1/")) {
                absolute=target.normalize();
                int depth=0;for(Path part:target){if(part.toString().equals("..")){if(--depth<0)throw new IOException("Session link escapes its guest root");}else if(!part.toString().equals("."))depth++;}
                // Android/private host paths are never guest content.
                if(absolute.startsWith("/data")||absolute.startsWith("/sdcard")||absolute.startsWith("/storage")||absolute.startsWith("/workspace"))throw new IOException("Session link targets Android host storage");
                return;
            }
            if(!target.normalize().startsWith("/work")||!target.startsWith("/work"))throw new IOException("Session link targets outside the realm: "+name);
            absolute=Paths.get("work").resolve(Paths.get("/work").relativize(target)).normalize();
        } else absolute=Paths.get(name).getParent().resolve(target).normalize();
        String root=name.startsWith("rootfs/")?"rootfs":"work";
        if(!absolute.startsWith(root))throw new IOException("Session link escapes its component: "+name);
    }
    static Properties create(File home,File archive,String version,String uiPreferencesJson,Progress progress)throws IOException {
        if(progress==null)progress=SILENT;
        Path base=home.getCanonicalFile().toPath();Files.createDirectories(archive.getAbsoluteFile().getParentFile().toPath());
        Path output=archive.getCanonicalFile().toPath();
        if(output.startsWith(base.resolve("rootfs"))||(output.startsWith(base.resolve("work"))&&!output.startsWith(base.resolve("work/exports"))))throw new IOException("Store session archives in exports, outside their contents");
        if(exists(output))throw new IOException("Session archive already exists");
        if(!Files.isRegularFile(base.resolve("rootfs/etc/trasc-runtime.json"),LinkOption.NOFOLLOW_LINKS))throw new IOException("Install the realm runtime before creating a complete session backup");
        byte[] prefs=preferenceBytes(uiPreferencesJson);
        Path index=Files.createTempFile(output.getParent(),"session-index-",".tsv"),preferences=Files.createTempFile(output.getParent(),"session-ui-",".json");
        Files.write(preferences,prefs);chmod(preferences,0600);
        long[] total={0};int[] count={0};Progress report=progress;
        Properties manifest=new Properties();
        try(ZipOutputStream zip=new ZipOutputStream(new BufferedOutputStream(Files.newOutputStream(output,StandardOpenOption.CREATE_NEW),1024*1024));
            BufferedWriter writer=Files.newBufferedWriter(index,StandardCharsets.UTF_8)) {
            zip.setLevel(1);
            for(String component:new String[]{"rootfs","work","configuration/ui.json"}) {
                Path source=component.equals("configuration/ui.json")?preferences:base.resolve(component);
                if(!exists(source))continue;
                if(!component.equals("configuration/ui.json")&&!Files.isDirectory(source,LinkOption.NOFOLLOW_LINKS))throw new IOException("Session component must be a real directory: "+component);
                report.update("Backing up "+component+"…");
                Files.walkFileTree(source,new SimpleFileVisitor<Path>() {
                    boolean skipped(Path path)throws IOException {
                        String name=component+(source.equals(path)?"":"/"+source.relativize(path));return excluded(name);
                    }
                    void add(Path path,BasicFileAttributes attributes)throws IOException {
                        if(++count[0]>MAX_FILES)throw new IOException("Session contains too many files");
                        Entry entry=new Entry();entry.name=component+(source.equals(path)?"":"/"+source.relativize(path));confined(base,entry.name);
                        if(attributes.isSymbolicLink()){entry.type="L";entry.link=backupLink(base,path,entry.name);}
                        else if(attributes.isDirectory()){entry.type="D";entry.mode=mode(path);}
                        else if(attributes.isRegularFile()) {
                            entry.type="F";entry.mode=mode(path);entry.size=attributes.size();
                            if(entry.size>MAX_BYTES-total[0])throw new IOException("Session exceeds 256 GB");total[0]+=entry.size;
                            MessageDigest digest=sha();long copied=0;zip.putNextEntry(new ZipEntry(entry.name));
                            try(InputStream in=Files.newInputStream(path,LinkOption.NOFOLLOW_LINKS)) {
                                byte[] buffer=new byte[1024*1024];int n;
                                while((n=in.read(buffer))!=-1){space(output.getParent().toFile(),n);zip.write(buffer,0,n);digest.update(buffer,0,n);copied+=n;if(copied>entry.size)throw new IOException("Session file changed during backup: "+entry.name);}
                            }
                            zip.closeEntry();BasicFileAttributes after=Files.readAttributes(path,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);
                            if(copied!=entry.size||!after.isRegularFile()||!attributes.lastModifiedTime().equals(after.lastModifiedTime())||!Objects.equals(attributes.fileKey(),after.fileKey()))throw new IOException("Session file changed during backup: "+entry.name);
                            entry.hash=hex(digest.digest());
                        }else throw new IOException("Stop all processes before backing up: "+entry.name);
                        writer.write(entry.line());if(count[0]%250==0)report.update("Backing up · "+count[0]+" files");
                    }
                    @Override public FileVisitResult preVisitDirectory(Path path,BasicFileAttributes attributes)throws IOException {if(skipped(path))return FileVisitResult.SKIP_SUBTREE;add(path,attributes);return FileVisitResult.CONTINUE;}
                    @Override public FileVisitResult visitFile(Path path,BasicFileAttributes attributes)throws IOException {if(!skipped(path))add(path,attributes);return FileVisitResult.CONTINUE;}
                });
            }
            writer.flush();if(Files.size(index)>MAX_INDEX)throw new IOException("Session index exceeds limits");
            zip.putNextEntry(new ZipEntry(INDEX));Files.copy(index,zip);zip.closeEntry();
            manifest.setProperty("format",FORMAT);manifest.setProperty("architecture","arm64");manifest.setProperty("runtime_backend","fex-arm64ec-1");
            manifest.setProperty("app_version",version);manifest.setProperty("created_utc",java.time.Instant.now().toString());manifest.setProperty("created_at",String.valueOf(System.currentTimeMillis()/1000.0));
            manifest.setProperty("entries",String.valueOf(count[0]));manifest.setProperty("uncompressed_bytes",String.valueOf(total[0]));manifest.setProperty("world_state","clean_shutdown");
            manifest.setProperty("components",components(base));
            manifest.setProperty("excluded","app exports and their catalog records,incoming archives,logs,process IDs and API tokens,temporary and staging trees,package caches,network source caches");
            zip.putNextEntry(new ZipEntry(MANIFEST));manifest.store(zip,"UO Memento complete session; includes accounts and credentials");zip.closeEntry();
        }catch(IOException|RuntimeException error){Files.deleteIfExists(output);throw error;}
        finally{Files.deleteIfExists(index);Files.deleteIfExists(preferences);}
        try(ZipFile check=new ZipFile(archive)){inventory(check);sync(output);}
        catch(IOException|RuntimeException error){Files.deleteIfExists(output);throw error;}
        report.update("Complete session ZIP ready");return report(manifest,archive);
    }
    private static String components(Path home) {
        List<String> included=new ArrayList<>();included.add("Realm runtime");
        if(exists(home.resolve("work/server")))included.add("World saves and configuration");
        if(exists(home.resolve("work/server/WorldLinux.exe")))included.add("Compiled server");
        if(exists(home.resolve("work/server-source"))||exists(home.resolve("work/source")))included.add("Server source");
        for(String[] component:new String[][]{{"client/current","Client content and settings"},{"client/prefix-fex-v1","Wine prefix"},{"client/runtime-fex-v1","FEX runtime"},{"client/dotnet",".NET"},{"client/controller.json","Controller preferences"}})
            if(exists(home.resolve("work/"+component[0])))included.add(component[1]);
        included.add("Launcher preferences");return String.join(",",included);
    }
    private static byte[] preferenceBytes(String text)throws IOException {
        if(text==null)text="{}";byte[] bytes=text.getBytes(StandardCharsets.UTF_8);
        if(bytes.length>MAX_PREFERENCES||!text.trim().startsWith("{")||!text.trim().endsWith("}"))throw new IOException("Invalid launcher preferences snapshot");return bytes;
    }
    private static Properties report(Properties properties,File archive) {
        properties.setProperty("files",properties.getProperty("entries"));properties.setProperty("unpacked_bytes",properties.getProperty("uncompressed_bytes"));
        properties.setProperty("bytes",String.valueOf(archive.length()));properties.setProperty("archive_bytes",String.valueOf(archive.length()));return properties;
    }
    private static InputStream bounded(InputStream input,long limit) {
        return new FilterInputStream(input) {
            long done;
            private void count(int amount)throws IOException {if(amount>0&&(done+=amount)>limit)throw new IOException("Session metadata exceeds limits");}
            @Override public int read()throws IOException {int value=in.read();count(value<0?0:1);return value;}
            @Override public int read(byte[] bytes,int offset,int length)throws IOException {int amount=in.read(bytes,offset,length);count(amount);return amount;}
        };
    }
    private static String readText(Path path,int limit)throws IOException {
        if(Files.size(path)>limit)throw new IOException("Session metadata exceeds limits");
        try(InputStream in=bounded(Files.newInputStream(path,LinkOption.NOFOLLOW_LINKS),limit);ByteArrayOutputStream out=new ByteArrayOutputStream()) {
            byte[] bytes=new byte[8192];int count;while((count=in.read(bytes))!=-1)out.write(bytes,0,count);
            try{return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).decode(java.nio.ByteBuffer.wrap(out.toByteArray())).toString();}
            catch(CharacterCodingException error){throw new IOException("Invalid session metadata encoding",error);}
        }
    }
    private static byte[] small(ZipFile zip,ZipEntry member,int limit)throws IOException {
        if(member==null||member.getSize()<0||member.getSize()>limit)throw new IOException("Session metadata exceeds limits or is missing");
        try(InputStream in=zip.getInputStream(member);ByteArrayOutputStream out=new ByteArrayOutputStream()) {
            byte[] bytes=new byte[8192];int n;while((n=in.read(bytes))!=-1){if(out.size()>limit-n)throw new IOException("Session metadata exceeds limits");out.write(bytes,0,n);}return out.toByteArray();
        }
    }
    private static long number(Properties properties,String name,long max)throws IOException {
        try{long value=Long.parseLong(properties.getProperty(name));if(value<0||value>max)throw new NumberFormatException();return value;}
        catch(NumberFormatException error){throw new IOException("Invalid session totals",error);}
    }
    private static String indexLine(BufferedReader reader)throws IOException {
        StringBuilder line=new StringBuilder();int value;
        while((value=reader.read())!=-1&&value!='\n') {
            if(line.length()>=32768)throw new IOException("Session index line exceeds limits");line.append((char)value);
        }
        if(value==-1&&line.length()==0)return null;return line.toString();
    }
    private static Inventory inventory(ZipFile zip)throws IOException {
        Properties manifest=new Properties();manifest.load(new ByteArrayInputStream(small(zip,zip.getEntry(MANIFEST),16384)));
        if(!FORMAT.equals(manifest.getProperty("format"))||!"arm64".equals(manifest.getProperty("architecture"))||!"fex-arm64ec-1".equals(manifest.getProperty("runtime_backend"))||!"clean_shutdown".equals(manifest.getProperty("world_state")))throw new IOException("This ZIP is not a supported UO Memento complete session");
        LinkedHashMap<String,Entry> entries=new LinkedHashMap<>();Map<Path,Entry> targets=new HashMap<>();long total=0;Path virtual=Paths.get("/session");
        ZipEntry index=zip.getEntry(INDEX);if(index==null||index.getSize()<0||index.getSize()>MAX_INDEX)throw new IOException("Session index exceeds limits or is missing");
        try(BufferedReader reader=new BufferedReader(new InputStreamReader(bounded(zip.getInputStream(index),MAX_INDEX),StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)))) {
            String line;while((line=indexLine(reader))!=null) {
                if(line.length()>32768||entries.size()>=MAX_FILES)throw new IOException("Session index exceeds limits");
                String[] cols=line.split("\t",-1);if(cols.length!=6)throw new IOException("Invalid session file record");
                Entry entry=new Entry();entry.type=cols[0];entry.hash=cols[3];entry.name=decode(cols[4]);entry.link=decode(cols[5]);
                try{entry.mode=Integer.parseInt(cols[1]);entry.size=Long.parseLong(cols[2]);}catch(NumberFormatException error){throw new IOException("Invalid session file metadata",error);}
                if(!Arrays.asList("F","D","L").contains(entry.type)||entry.mode<0||entry.mode>0777||entry.size<0||entry.size>MAX_BYTES)throw new IOException("Invalid session file type, mode or size");
                Path target=destination(virtual,entry.name);
                if(entries.put(entry.name,entry)!=null||targets.put(target,entry)!=null)throw new IOException("Duplicate session path: "+entry.name);
                if(entry.type.equals("F")) {
                    ZipEntry member=zip.getEntry(entry.name);if(member==null||member.getSize()!=entry.size||!entry.hash.matches("[0-9a-f]{64}")||!entry.link.isEmpty())throw new IOException("Missing or damaged session file: "+entry.name);
                    if(entry.size>MAX_BYTES-total)throw new IOException("Session exceeds supported size");total+=entry.size;
                }else {
                    if(entry.size!=0||!entry.hash.equals("-")||(entry.type.equals("D")&&!entry.link.isEmpty()))throw new IOException("Invalid session directory/link metadata");
                    if(entry.type.equals("L"))validateLink(entry.name,entry.link);
                }
            }
        }
        if(total!=number(manifest,"uncompressed_bytes",MAX_BYTES)||entries.size()!=number(manifest,"entries",MAX_FILES))throw new IOException("Session inventory does not match its manifest");
        Set<String> names=new HashSet<>();Enumeration<? extends ZipEntry> members=zip.entries();
        while(members.hasMoreElements()) {
            ZipEntry member=members.nextElement();String name=member.getName();
            if(!names.add(name)||(!name.equals(INDEX)&&!name.equals(MANIFEST)&&(!entries.containsKey(name)||!entries.get(name).type.equals("F")))||member.isDirectory())throw new IOException("Unexpected or duplicate ZIP member: "+name);
        }
        for(Map.Entry<Path,Entry> pair:targets.entrySet())for(Path parent=pair.getKey().getParent();parent!=null&&parent.startsWith(virtual);parent=parent.getParent()) {
            Entry ancestor=targets.get(parent);if(ancestor!=null&&!ancestor.type.equals("D"))throw new IOException("A session file/link cannot contain other files: "+ancestor.name);
        }
        for(String required:new String[]{"rootfs","work"})if(!entries.containsKey(required)||!entries.get(required).type.equals("D"))throw new IOException("Incomplete session: "+required);
        if(entries.containsKey("work/backups")&&!entries.get("work/backups").type.equals("D"))throw new IOException("The restored backup catalog must be a real directory");
        requireFile(entries,"rootfs/etc/trasc-runtime.json");requireFile(entries,"configuration/ui.json");
        if(entries.get("configuration/ui.json").size>MAX_PREFERENCES)throw new IOException("Launcher preferences exceed limits");
        marker(zip,"rootfs/etc/trasc-runtime.json",1,null);
        for(String name:new String[]{"usr/bin/python3.11","usr/bin/git","usr/bin/apt-get"})requireRuntimeFile(entries,"rootfs",name);
        if(entries.containsKey("work/client/runtime-fex-v1")) {
            requireFile(entries,"work/client/runtime-fex-v1/etc/memento-client-runtime.json");marker(zip,"work/client/runtime-fex-v1/etc/memento-client-runtime.json",2,"fex-arm64ec-1");
            for(String name:new String[]{"usr/bin/python3.11","usr/bin/Xtigervnc","opt/wine/bin/wine","opt/wine/bin/wineserver","opt/wine/lib/wine/aarch64-windows/libarm64ecfex.dll","opt/wine/lib/wine/aarch64-windows/libwow64fex.dll"})requireRuntimeFile(entries,"work/client/runtime-fex-v1",name);
        }
        return new Inventory(manifest,entries,total);
    }
    private static void requireFile(Map<String,Entry> entries,String name)throws IOException {
        if(!entries.containsKey(name)||!entries.get(name).type.equals("F"))throw new IOException("Incomplete session: "+name);
    }
    private static void requireRuntimeFile(Map<String,Entry> entries,String component,String relative)throws IOException {
        String name=component+"/"+relative;Set<String> seen=new HashSet<>();
        while(seen.add(name)) {
            Entry entry=entries.get(name);if(entry==null)break;
            if(entry.type.equals("F")&&entry.size>0)return;
            if(!entry.type.equals("L"))break;
            Path target=Paths.get(entry.link);
            Path resolved=target.isAbsolute()?Paths.get(component).resolve(Paths.get("/").relativize(target)).normalize():Paths.get(name).getParent().resolve(target).normalize();
            if(!resolved.startsWith(component))break;name=resolved.toString();
        }
        throw new IOException("Incomplete runtime: "+component+"/"+relative);
    }
    private static void marker(ZipFile zip,String path,int format,String runtime)throws IOException {
        String text=new String(small(zip,zip.getEntry(path),131072),StandardCharsets.UTF_8);
        if(!jsonField(text,"format").equals(String.valueOf(format))||!jsonField(text,"architecture").equals("arm64")||(runtime!=null&&!runtime.equals(jsonField(text,"runtime"))))throw new IOException("Unsupported session runtime: "+path);
    }
    // Marker fields are a small, fixed contract; the Android bridge separately
    // validates the full preferences JSON with JSONObject before applying it.
    private static String jsonField(String json,String field)throws IOException {
        Matcher match=Pattern.compile("\""+field+"\"\\s*:\\s*(?:\"([^\"\\\\]*)\"|([0-9]+))").matcher(json);
        if(!match.find())throw new IOException("Missing session runtime metadata");String value=match.group(1)==null?match.group(2):match.group(1);if(match.find())throw new IOException("Duplicate runtime metadata");return value;
    }
    static Properties preview(File archive)throws IOException{return preview(archive,SILENT);}
    static String archivedPreferences(File archive)throws IOException {
        try(ZipFile zip=new ZipFile(archive)) {
            byte[] bytes=small(zip,zip.getEntry("configuration/ui.json"),MAX_PREFERENCES);
            try {
                String text=StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).decode(java.nio.ByteBuffer.wrap(bytes)).toString();
                preferenceBytes(text);return text;
            }catch(CharacterCodingException error){throw new IOException("Invalid launcher preferences encoding",error);}
        }
    }
    static Properties preview(File archive,Progress progress)throws IOException {
        try(ZipFile zip=new ZipFile(archive)) {
            Inventory inventory=inventory(zip);verify(zip,inventory,null,progress==null?SILENT:progress);
            archivedPreferences(archive);return report(inventory.manifest,archive);
        }
    }
    private static void verify(ZipFile zip,Inventory inventory,Path stage,Progress progress)throws IOException {
        int count=0;byte[] buffer=new byte[1024*1024];
        for(Entry entry:inventory.entries.values()) {
            Path target=stage==null?null:destination(stage,entry.name);
            if(entry.type.equals("D")){if(stage!=null)Files.createDirectories(target);continue;}
            if(!entry.type.equals("F"))continue;
            if(stage!=null)Files.createDirectories(target.getParent());MessageDigest digest=sha();long done=0;
            try(InputStream in=zip.getInputStream(zip.getEntry(entry.name));OutputStream out=stage==null?new OutputStream(){public void write(int value){}public void write(byte[] bytes,int offset,int length){}}:Files.newOutputStream(target,StandardOpenOption.CREATE_NEW,LinkOption.NOFOLLOW_LINKS)) {
                int n;while((n=in.read(buffer))!=-1){done+=n;if(done>entry.size)throw new IOException("Session file is larger than recorded");if(stage!=null)space(stage.toFile(),n);out.write(buffer,0,n);digest.update(buffer,0,n);}
            }
            if(done!=entry.size||!hex(digest.digest()).equals(entry.hash))throw new IOException("Session checksum failed: "+entry.name);
            if(stage!=null){chmod(target,entry.mode);sync(target);}if(++count%250==0)progress.update((stage==null?"Checking session":"Verifying and restoring")+" · "+count+" files");
        }
    }
    static Properties restore(File archive,File staging,Progress progress)throws IOException {
        if(progress==null)progress=SILENT;Path stage=staging.getCanonicalFile().toPath();
        if(exists(stage))throw new IOException("Session staging already exists; finish recovery before restoring");
        Files.createDirectories(stage);
        try(ZipFile zip=new ZipFile(archive)) {
            Inventory inventory=inventory(zip);space(staging,inventory.bytes);verify(zip,inventory,stage,progress);
            for(Entry entry:inventory.entries.values())if(entry.type.equals("L")) {
                Path target=destination(stage,entry.name);Files.createDirectories(target.getParent());Files.createSymbolicLink(target,Paths.get(entry.link));
            }
            List<Entry> dirs=new ArrayList<>();for(Entry entry:inventory.entries.values())if(entry.type.equals("D"))dirs.add(entry);
            // Sync child entries before restricting parent permissions. The
            // entire staged filesystem must be durable before its verified mark.
            Files.walkFileTree(stage,new SimpleFileVisitor<Path>() {
                @Override public FileVisitResult postVisitDirectory(Path path,IOException error)throws IOException {if(error!=null)throw error;syncDirectory(path);return FileVisitResult.CONTINUE;}
            });
            dirs.sort((a,b)->Integer.compare(b.name.length(),a.name.length()));for(Entry entry:dirs){Path path=destination(stage,entry.name);chmod(path,entry.mode);syncDirectory(path);}
            preferenceBytes(readText(stage.resolve(PREFERENCES),MAX_PREFERENCES));
            durableWrite(stage.resolve("verified.properties"),propertiesBytes(inventory.manifest));
            progress.update("Complete session verified; ready to restore");return report(inventory.manifest,archive);
        }catch(IOException|RuntimeException error){try{remove(stage);}catch(IOException cleanup){error.addSuppressed(cleanup);}throw error;}
    }
    static String restoredPreferences(File staging)throws IOException {
        Path path=staging.toPath().resolve(PREFERENCES);if(Files.size(path)>MAX_PREFERENCES)throw new IOException("Launcher preferences exceed limits");
        String text=readText(path,MAX_PREFERENCES);preferenceBytes(text);return text;
    }
    private static byte[] propertiesBytes(Properties properties)throws IOException {
        ByteArrayOutputStream out=new ByteArrayOutputStream();properties.store(out,"UO session restore transaction");return out.toByteArray();
    }
    private static Properties properties(Path file)throws IOException {
        Properties result=new Properties();try(InputStream in=Files.newInputStream(file,LinkOption.NOFOLLOW_LINKS)){result.load(in);}return result;
    }
    private static void sync(Path path)throws IOException {try(FileChannel file=FileChannel.open(path,StandardOpenOption.READ)){file.force(true);}}
    static void durableWrite(Path file,byte[] bytes)throws IOException {
        Files.createDirectories(file.getParent());Path pending=file.resolveSibling(file.getFileName()+".new");
        try(FileOutputStream out=new FileOutputStream(pending.toFile())){out.write(bytes);out.getFD().sync();}
        Files.move(pending,file,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
        syncDirectory(file.getParent());
    }
    static void syncDirectory(Path path)throws IOException {try(FileChannel directory=FileChannel.open(path,StandardOpenOption.READ)){directory.force(true);}}
    private static void move(Path from,Path to)throws IOException {
        Files.move(from,to,StandardCopyOption.ATOMIC_MOVE);syncDirectory(from.getParent());if(!from.getParent().equals(to.getParent()))syncDirectory(to.getParent());
    }
    /** Swap two independently bound guest trees and launcher preferences as a
     * single recoverable transaction. The original trees remain until commit.
     * Runtime/client references continue to use the same home/work pathnames.
     */
    static synchronized void activate(File home,File staging,Preferences preferences,Progress progress)throws IOException {
        if(progress==null)progress=SILENT;recover(home,preferences);
        Path base=home.getCanonicalFile().toPath(),stage=staging.getCanonicalFile().toPath(),transaction=base.resolve(TRANSACTION);
        if(!stage.getParent().equals(base)||stage.equals(base.resolve("rootfs"))||stage.equals(base.resolve("work"))||stage.equals(transaction))throw new IOException("Session staging must be a separate directory beside the runtime");
        Properties verified=properties(stage.resolve("verified.properties"));if(!FORMAT.equals(verified.getProperty("format")))throw new IOException("Verify the complete session before restoring it");
        for(String component:new String[]{"rootfs","work"})if(!Files.isDirectory(stage.resolve(component),LinkOption.NOFOLLOW_LINKS))throw new IOException("Incomplete staged session");
        String next=restoredPreferences(staging),before=preferences.read();byte[] original=preferenceBytes(before);
        Files.createDirectory(transaction);Properties journal=new Properties();journal.setProperty("format",FORMAT);journal.setProperty("phase","prepared");journal.setProperty("stage",stage.getFileName().toString());
        for(String component:new String[]{"rootfs","work"})journal.setProperty("had_"+component,String.valueOf(exists(base.resolve(component))));
        durableWrite(transaction.resolve("before-preferences.json"),original);durableWrite(transaction.resolve("journal.properties"),propertiesBytes(journal));
        try {
            progress.update("Preserving the current complete session…");
            for(String component:new String[]{"rootfs","work"}) {
                Path live=base.resolve(component);if(exists(live))move(live,transaction.resolve("old-"+component));move(stage.resolve(component),live);
                progress.update("Restoring "+component+"…");
            }
            for(String retained:RETAINED) {
                Path old=transaction.resolve("old-work/"+retained),live=base.resolve("work/"+retained);
                if(exists(old)){if(exists(live))throw new IOException("A complete snapshot unexpectedly includes "+retained);move(old,live);}
                else Files.createDirectories(live);
            }
            preserveCatalog(transaction.resolve("old-work/backups"),base.resolve("work/backups"));
            progress.update("Restoring launcher preferences…");preferences.write(next);
            journal.setProperty("phase","committed");durableWrite(transaction.resolve("journal.properties"),propertiesBytes(journal));
        }catch(IOException|RuntimeException error){try{recover(home,preferences);}catch(IOException recovery){error.addSuppressed(recovery);}throw error;}
        // A cleanup error after commit is recoverable on the next opening. It
        // must never be reported as a failed restore of the active new session.
        try{remove(stage);cleanTransaction(transaction);}catch(IOException cleanup){progress.update("Session restored; previous-session cleanup will resume next time");return;}
        progress.update("Complete session restored");
    }
    private static void preserveCatalog(Path old,Path destination)throws IOException {
        if(!Files.isDirectory(old,LinkOption.NOFOLLOW_LINKS))return;
        if(exists(destination)&&!Files.isDirectory(destination,LinkOption.NOFOLLOW_LINKS))throw new IOException("The restored backup catalog must be a real directory");
        Files.createDirectories(destination);
        try(DirectoryStream<Path> files=Files.newDirectoryStream(old)) {
            for(Path path:files) {
                String name=path.getFileName().toString();
                if((name.startsWith("metadata-")||name.startsWith("exported-"))&&Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS)&&Files.size(path)<=131072) {
                    Path copied=destination.resolve(name);Files.copy(path,copied,StandardCopyOption.REPLACE_EXISTING,LinkOption.NOFOLLOW_LINKS);sync(copied);
                }
            }
        }
        syncDirectory(destination);
    }
    /** Must run before opening any guest or loading the controller profile. */
    static synchronized void recover(File home,Preferences preferences)throws IOException {
        Path base=home.getCanonicalFile().toPath(),transaction=base.resolve(TRANSACTION);if(!exists(transaction))return;
        if(!Files.isDirectory(transaction,LinkOption.NOFOLLOW_LINKS))throw new IOException("Unsafe session restore recovery directory");
        Path journalFile=transaction.resolve("journal.properties");
        if(!exists(journalFile)) {
            // A crash while preparing the journal cannot have moved live trees.
            if(exists(transaction.resolve("old-work"))||exists(transaction.resolve("old-rootfs")))throw new IOException("Session recovery journal is missing; preserve the previous session and retry");
            remove(transaction);syncDirectory(base);return;
        }
        Properties journal=properties(journalFile);
        if(!FORMAT.equals(journal.getProperty("format"))||!Arrays.asList("prepared","committed","rolled_back").contains(journal.getProperty("phase")))throw new IOException("Invalid session recovery journal");
        String name=journal.getProperty("stage","");Path stage=confined(base,name);if(!stage.getParent().equals(base)||stage.equals(base.resolve("rootfs"))||stage.equals(base.resolve("work"))||stage.equals(transaction))throw new IOException("Unsafe session recovery staging path");
        if("prepared".equals(journal.getProperty("phase"))) {
            Path oldWork=transaction.resolve("old-work");
            if(exists(oldWork))for(String retained:RETAINED) {
                Path old=oldWork.resolve(retained),live=base.resolve("work/"+retained);if(!exists(old)&&exists(live))move(live,old);
            }
            Path prefs=transaction.resolve("before-preferences.json");if(Files.size(prefs)>MAX_PREFERENCES)throw new IOException("Previous launcher preferences exceed limits");
            String before=readText(prefs,MAX_PREFERENCES);preferenceBytes(before);preferences.write(before);
            for(String component:new String[]{"rootfs","work"}) {
                Path old=transaction.resolve("old-"+component),live=base.resolve(component);
                if(exists(old)){remove(live);move(old,live);}
                else if("false".equals(journal.getProperty("had_"+component)))remove(live);
                else if(!"true".equals(journal.getProperty("had_"+component)))throw new IOException("Invalid session recovery state");
            }
            journal.setProperty("phase","rolled_back");durableWrite(journalFile,propertiesBytes(journal));
        }
        remove(stage);cleanTransaction(transaction);
    }
    private static void cleanTransaction(Path transaction)throws IOException {
        // Keep the durable decision until the old trees and preference snapshot
        // have been removed. Killing the process during cleanup can then resume
        // cleanup without mistaking a committed restore for an incomplete one.
        try(DirectoryStream<Path> children=Files.newDirectoryStream(transaction)) {
            for(Path path:children)if(!path.getFileName().toString().equals("journal.properties"))remove(path);
        }
        syncDirectory(transaction);Files.deleteIfExists(transaction.resolve("journal.properties"));syncDirectory(transaction);
        Files.delete(transaction);syncDirectory(transaction.getParent());
    }
    static void remove(Path root)throws IOException {
        if(!exists(root))return;
        if(Files.isDirectory(root,LinkOption.NOFOLLOW_LINKS))chmod(root,mode(root)|0700);
        Files.walkFileTree(root,new SimpleFileVisitor<Path>() {
            @Override public FileVisitResult preVisitDirectory(Path path,BasicFileAttributes attrs)throws IOException {
                // walkFileTree opens directories before preVisitDirectory, so
                // grant owner traversal on children before it tries to open them.
                try(DirectoryStream<Path> children=Files.newDirectoryStream(path)) {
                    for(Path child:children)if(Files.isDirectory(child,LinkOption.NOFOLLOW_LINKS))chmod(child,mode(child)|0700);
                }
                return FileVisitResult.CONTINUE;
            }
            @Override public FileVisitResult visitFile(Path path,BasicFileAttributes attrs)throws IOException {Files.delete(path);return FileVisitResult.CONTINUE;}
            @Override public FileVisitResult postVisitDirectory(Path path,IOException error)throws IOException {if(error!=null)throw error;Files.delete(path);return FileVisitResult.CONTINUE;}
        });
    }
}
