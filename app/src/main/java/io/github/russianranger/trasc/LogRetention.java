package io.github.russianranger.trasc;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;
import java.util.regex.*;

/** Retain closed diagnostic logs only. Live process logs and user data are excluded. */
final class LogRetention {
    static final long LIMIT=8L*1024*1024;
    private static final Pattern ARCHIVE=Pattern.compile("(.+)\\.previous(?:\\.([2-5]))?\\.log");
    private static final Pattern SERVER=Pattern.compile("(login|world|ucs|query_server|zone)_(\\d+)\\.log");
    private static final Pattern ZONE=Pattern.compile(".+_version_\\d+_inst_id_\\d+_port_\\d+_(\\d+)\\.log");

    static int count(File work) {
        try {
            Path p=LocalLogs.checked(work.toPath(),"logs/retention-count.txt");
            if(Files.size(p)>16)return 5;
            int n=Integer.parseInt(new String(Files.readAllBytes(p),StandardCharsets.UTF_8).trim());
            return n>=2&&n<=5?n:5;
        }catch(IOException|NumberFormatException e){return 5;}
    }

    static synchronized void save(File work,int count)throws IOException {
        if(count<2||count>5)throw new IOException("Choose 2, 3, 4 or 5 older logs");
        Path target=LocalLogs.checked(work.toPath(),"logs/retention-count.txt");
        Files.createDirectories(target.getParent());
        Path tmp=Files.createTempFile(target.getParent(),"retention-",".tmp");
        try {
            Files.write(tmp,(count+"\n").getBytes(StandardCharsets.UTF_8));
            Files.move(tmp,target,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
        }finally{Files.deleteIfExists(tmp);}
    }

    static Path history(Path log,int index) {
        String name=log.getFileName().toString();
        return log.resolveSibling(name.substring(0,name.length()-4)+".previous"+(index==1?"":"."+index)+".log");
    }

    static synchronized void rotate(File file)throws IOException {
        Path log=file.toPath();
        File work=file.getParentFile().getParentFile();
        LocalLogs.checked(work.toPath(),"logs/"+file.getName());
        if(!Files.isRegularFile(log,LinkOption.NOFOLLOW_LINKS)||Files.size(log)==0)return;
        int keep=count(work);
        for(int i=5;i>=1;i--) {
            Path old=history(log,i);
            if(Files.isSymbolicLink(old))throw new IOException("Log history cannot contain a symlink");
            if(!Files.isRegularFile(old,LinkOption.NOFOLLOW_LINKS))continue;
            if(i>=keep)Files.delete(old);
            else Files.move(old,history(log,i+1),StandardCopyOption.REPLACE_EXISTING);
        }
        Path target=history(log,1);
        if(Files.size(log)<=LIMIT)Files.move(log,target,StandardCopyOption.REPLACE_EXISTING);
        else {
            Path tmp=Files.createTempFile(log.getParent(),"log-history-",".tmp");
            byte[] marker="\n[TRASC: previous log shortened; startup and final output retained]\n".getBytes(StandardCharsets.UTF_8);
            try(RandomAccessFile in=new RandomAccessFile(file,"r");OutputStream out=Files.newOutputStream(tmp)) {
                copy(in,out,LIMIT/2);out.write(marker);
                long tail=LIMIT-LIMIT/2-marker.length;in.seek(in.length()-tail);copy(in,out,tail);
            }catch(IOException e){Files.deleteIfExists(tmp);throw e;}
            try{Files.move(tmp,target,StandardCopyOption.REPLACE_EXISTING);Files.delete(log);}
            finally{Files.deleteIfExists(tmp);}
        }
    }

    private static void copy(RandomAccessFile in,OutputStream out,long size)throws IOException {
        byte[] data=new byte[65536];
        while(size>0){int n=in.read(data,0,(int)Math.min(size,data.length));if(n<0)break;out.write(data,0,n);size-=n;}
    }

    static synchronized long[] prune(File work)throws IOException {
        return prune(work,Paths.get("/proc"));
    }

    static long[] prune(File work,Path proc)throws IOException {
        int keep=count(work);
        Map<String,List<Path>> groups=new TreeMap<>();
        long[] removed={0,0};
        for(String directory:new String[]{"logs","server/logs"}) {
            Path root=LocalLogs.checked(work.toPath(),directory);
            if(!Files.isDirectory(root,LinkOption.NOFOLLOW_LINKS))continue;
            Files.walkFileTree(root,new SimpleFileVisitor<Path>() {
                @Override public FileVisitResult visitFile(Path path,BasicFileAttributes attrs)throws IOException {
                    if(!attrs.isRegularFile())return FileVisitResult.CONTINUE;
                    String relative=root.relativize(path).toString(),name=path.getFileName().toString();
                    Matcher archive=ARCHIVE.matcher(name),server=SERVER.matcher(name),zone=ZONE.matcher(name);
                    if(!relative.contains("/")&&archive.matches()) {
                        int index=archive.group(2)==null?1:Integer.parseInt(archive.group(2));
                        if(index>keep)remove(path,removed);
                    }else if(directory.equals("server/logs")) {
                        String group=null,pid=null;
                        if(server.matches()&&(!relative.contains("/")||relative.equals("zone/"+name))) {
                            group=server.group(1);pid=server.group(2);
                        }else if(relative.equals("zone/"+name)&&zone.matches()) {group="zone";pid=zone.group(1);}
                        // PID reuse / inaccessible proc entries are conservatively retained.
                        if(group!=null&&Files.isDirectory(proc)&&Files.notExists(proc.resolve(pid)))
                            groups.computeIfAbsent(group,k->new ArrayList<>()).add(path);
                    }
                    return FileVisitResult.CONTINUE;
                }
                @Override public FileVisitResult visitFileFailed(Path p,IOException e)throws IOException {
                    if(e instanceof NoSuchFileException)return FileVisitResult.CONTINUE;
                    throw e;
                }
            });
        }
        for(List<Path> paths:groups.values()) {
            paths.sort(Comparator.comparingLong(LogRetention::modified).reversed().thenComparing(Path::toString));
            for(int i=keep;i<paths.size();i++) {
                Path path=paths.get(i);
                String name=path.getFileName().toString();
                String pid=name.substring(name.lastIndexOf('_')+1,name.length()-4);
                if(Files.notExists(proc.resolve(pid)))remove(path,removed);
            }
        }
        return removed;
    }

    private static long modified(Path path) {
        try{return Files.getLastModifiedTime(path,LinkOption.NOFOLLOW_LINKS).toMillis();}
        catch(IOException e){return Long.MAX_VALUE;}
    }
    private static void remove(Path path,long[] removed)throws IOException {
        try {
            if(!Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS))return;
            long size=Files.size(path);
            if(Files.deleteIfExists(path)){removed[0]++;removed[1]+=size;}
        }catch(NoSuchFileException ignored){}
    }
}
