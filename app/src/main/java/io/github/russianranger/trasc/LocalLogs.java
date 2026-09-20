package io.github.russianranger.trasc;

import java.io.*;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;
import java.util.zip.*;

/** Diagnostics must remain available even when PRoot/Python cannot start. */
final class LocalLogs {
    static final int TAIL_BYTES=64000, MAX_FILES=10000;
    static final long RESERVE=64L*1024*1024;

    // Only startup diagnostics from the imported client, never its INI files,
    // binaries, saved credentials or potentially very large character chat logs.
    static boolean clientDiagnostic(String name) {
        String lower=name.toLowerCase(Locale.ROOT);
        if(lower.equals("dinput8.log")||lower.equals("dbg.txt"))return true;
        // TazUO can be nested inside the import and timestamps its crash reports.
        int logs=lower.lastIndexOf("/logs/");
        String leaf=lower.startsWith("logs/")?lower.substring(5):logs>=0?lower.substring(logs+6):"";
        return Arrays.asList("dbg.txt","dbg.log","uierrors.txt","crash.log","crash.txt").contains(leaf)
                ||leaf.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}-[0-9]{2}-[0-9]{2}_crash\\.txt");
    }

    static void addClientLog(Map<String,Path> files,Path root,Path path)throws IOException {
        String name=root.relativize(path).toString();
        if(clientDiagnostic(name)&&Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS)) {
            files.put("client/"+name,path);
            if(files.size()>MAX_FILES)throw new IOException("More than 10,000 log files; archive older logs before exporting");
        }
    }

    // Check every parent as well as the leaf. Never follow server/ or logs/ links.
    static Path checked(Path work,String relative)throws IOException {
        // Keep Context's lexical path throughout. Canonicalizing just the child
        // mixes /data/user/0 and /data/data and makes relativize() invent "..".
        work=work.toAbsolutePath().normalize();
        if(relative.startsWith("/")||relative.contains("\\")||relative.indexOf('\0')>=0)
            throw new IOException("Unsafe log path");
        for(String part:relative.split("/"))if(part.equals(".."))throw new IOException("Unsafe log path");
        Path path=work.resolve(relative).normalize(),current=work;
        if(!path.startsWith(work))throw new IOException("Log path escapes workspace");
        if(Files.isSymbolicLink(work))throw new IOException("Log workspace cannot be a symlink");
        for(Path part:work.relativize(path)) {
            current=current.resolve(part);
            if(Files.isSymbolicLink(current))throw new IOException("Log path cannot contain a symlink: "+relative);
        }
        return path;
    }

    static Map<String,Path> inventory(File work)throws IOException {
        Map<String,Path> files=new TreeMap<>();
        for(String directory:new String[]{"logs","server/logs"}) {
            Path root;
            try{root=checked(work.toPath(),directory);}catch(IOException unsafe){continue;}
            if(!Files.isDirectory(root,LinkOption.NOFOLLOW_LINKS))continue;
            Files.walkFileTree(root,new SimpleFileVisitor<Path>() {
                @Override public FileVisitResult visitFile(Path p,BasicFileAttributes attrs)throws IOException {
                    if(attrs.isRegularFile()) {
                        String name=(directory.equals("logs")?"":"server/")+root.relativize(p);
                        files.put(name,p);
                        if(files.size()>MAX_FILES)throw new IOException("More than 10,000 log files; archive older logs before exporting");
                    }
                    return FileVisitResult.CONTINUE;
                }
                @Override public FileVisitResult visitFileFailed(Path p,IOException error)throws IOException {
                    if(error instanceof NoSuchFileException)return FileVisitResult.CONTINUE; // Log rotation.
                    throw error;
                }
            });
        }
        Path client;
        try{client=checked(work.toPath(),"client/current");}catch(IOException unsafe){return files;}
        if(Files.isDirectory(client,LinkOption.NOFOLLOW_LINKS)) {
            Files.walkFileTree(client,EnumSet.noneOf(FileVisitOption.class),16,new SimpleFileVisitor<Path>() {
                int visited;
                @Override public FileVisitResult visitFile(Path path,BasicFileAttributes attrs)throws IOException {
                    if(++visited>250000)return FileVisitResult.TERMINATE;
                    if(attrs.isRegularFile())addClientLog(files,client,path);
                    return FileVisitResult.CONTINUE;
                }
                @Override public FileVisitResult visitFileFailed(Path path,IOException error) {
                    return FileVisitResult.CONTINUE; // Optional imported-client diagnostics.
                }
            });
        }
        return files;
    }

    static String tail(File work,String name)throws IOException {
        String relative=name.startsWith("server/")?"server/logs/"+name.substring(7):"logs/"+name;
        if(name.startsWith("client/")) {
            if(!clientDiagnostic(name.substring(7)))throw new IOException("Choose a client diagnostic log");
            relative="client/current/"+name.substring(7);
        }
        Path path=checked(work.toPath(),relative);
        if(!Files.exists(path,LinkOption.NOFOLLOW_LINKS))return "No log output yet.";
        if(!Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS))throw new IOException("Choose a regular log file");
        try(SeekableByteChannel channel=Files.newByteChannel(path,StandardOpenOption.READ,LinkOption.NOFOLLOW_LINKS)) {
            long size=channel.size();channel.position(Math.max(0,size-TAIL_BYTES));
            ByteBuffer bytes=ByteBuffer.allocate((int)Math.min(size,TAIL_BYTES));
            while(bytes.hasRemaining()&&channel.read(bytes)!=-1){}
            return new String(bytes.array(),0,bytes.position(),StandardCharsets.UTF_8);
        } catch(NoSuchFileException rotated){return "Log rotated; refresh to read the new file.";}
    }

    static File export(File work,String statusJson)throws IOException {
        Path exports=checked(work.toPath(),"exports");Files.createDirectories(exports);
        File partial=File.createTempFile("logs-",".partial",exports.toFile());
        File archive=new File(exports.toFile(),partial.getName().replace(".partial",".zip"));
        List<String> notes=new ArrayList<>();
        try {
            try(ZipOutputStream zip=new ZipOutputStream(new BufferedOutputStream(new FileOutputStream(partial)))) {
                zip.setLevel(1);
                for(Path file:inventory(work).values()) {
                    String name=work.toPath().toAbsolutePath().normalize().relativize(file).toString();
                    checked(work.toPath(),name);
                    SeekableByteChannel opened;
                    try{opened=Files.newByteChannel(file,StandardOpenOption.READ,LinkOption.NOFOLLOW_LINKS);}
                    catch(NoSuchFileException rotated){notes.add("Rotated before export: "+name);continue;}
                    try(SeekableByteChannel channel=opened) {
                        // Snapshot length: a running logger must not keep the export open forever.
                        long remaining=channel.size();
                        zip.putNextEntry(new ZipEntry(name));ByteBuffer buffer=ByteBuffer.allocate(65536);
                        while(remaining>0) {
                            buffer.clear();buffer.limit((int)Math.min(buffer.capacity(),remaining));
                            int n=channel.read(buffer);
                            if(n<0){notes.add("Truncated during export: "+name);break;}
                            if(exports.toFile().getUsableSpace()<RESERVE+n)throw new IOException("Not enough storage to export logs; free space and retry");
                            zip.write(buffer.array(),0,n);remaining-=n;
                        }
                        zip.closeEntry();
                    }
                }
                zip.putNextEntry(new ZipEntry("status.json"));zip.write(statusJson.getBytes(StandardCharsets.UTF_8));zip.closeEntry();
                zip.putNextEntry(new ZipEntry("export-notes.txt"));
                zip.write(("Native Android log export; no running Linux runtime required.\nSymlinks and non-regular files are excluded.\n"+String.join("\n",notes)+"\n").getBytes(StandardCharsets.UTF_8));zip.closeEntry();
            }
            try(FileOutputStream out=new FileOutputStream(partial,true)){out.getFD().sync();}
            Files.move(partial.toPath(),archive.toPath());
            return archive;
        } finally {Files.deleteIfExists(partial.toPath());}
    }

    static synchronized void failure(File work,String operation,Exception error)throws IOException {
        Path path=checked(work.toPath(),"logs/app.log");Files.createDirectories(path.getParent());
        if(Files.exists(path)&&Files.size(path)>LogRetention.LIMIT)LogRetention.rotate(path.toFile());
        try(PrintWriter out=new PrintWriter(new OutputStreamWriter(Files.newOutputStream(path,
                StandardOpenOption.CREATE,StandardOpenOption.APPEND,LinkOption.NOFOLLOW_LINKS),StandardCharsets.UTF_8))) {
            out.println(java.time.Instant.now()+" "+operation+" failed");error.printStackTrace(out);
            if(out.checkError())throw new IOException("Could not write app log");
        }
    }
}
