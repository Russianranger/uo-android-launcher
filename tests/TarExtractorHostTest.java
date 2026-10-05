package io.github.russianranger.trasc;

import android.system.Os;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermission;
import java.util.*;
import java.util.zip.GZIPOutputStream;

/** Regress the Android link(2) denial with real extraction, modes and budgets. */
public final class TarExtractorHostTest {
    record Entry(String name,char type,String target,int mode,byte[] data) {}
    static Entry file(String name,int mode,String data){return new Entry(name,'0',"",mode,data.getBytes(StandardCharsets.UTF_8));}
    static Entry link(String name,String target){return new Entry(name,'1',target,0,new byte[0]);}
    static Entry sym(String name,String target){return new Entry(name,'2',target,0777,new byte[0]);}
    static void field(byte[] h,int at,String value){byte[] b=value.getBytes(StandardCharsets.UTF_8);System.arraycopy(b,0,h,at,b.length);}
    static Path archive(Path dir,Entry... entries)throws IOException {
        Path archive=Files.createTempFile(dir,"fixture-",".tar.gz");
        try(OutputStream out=new GZIPOutputStream(Files.newOutputStream(archive))) {
            for(Entry e:entries) {
                byte[] h=new byte[512];field(h,0,e.name);field(h,100,String.format("%07o",e.mode));
                field(h,124,String.format("%011o",e.data.length));Arrays.fill(h,148,156,(byte)' ');
                h[156]=(byte)e.type;field(h,157,e.target);field(h,257,"ustar");
                int checksum=0;for(byte b:h)checksum+=b&255;field(h,148,String.format("%06o\0 ",checksum));
                out.write(h);out.write(e.data);out.write(new byte[(512-e.data.length%512)%512]);
            }
            out.write(new byte[1024]);
        }
        return archive;
    }
    static int mode(Path p)throws IOException {
        int mode=0;Set<PosixFilePermission> permissions=Files.getPosixFilePermissions(p,LinkOption.NOFOLLOW_LINKS);
        PosixFilePermission[] flags=PosixFilePermission.values();
        for(int i=0;i<9;i++)if(permissions.contains(flags[i]))mode|=1<<(8-i);
        return mode;
    }
    static void check(boolean ok,String message){if(!ok)throw new AssertionError(message);}
    static void rejected(Path tmp,String reason,long limit,Entry... entries)throws Exception {
        rejectsRoot(tmp,Files.createTempDirectory(tmp,"reject-").toFile(),reason,limit,entries);
    }
    static void rejectsRoot(Path tmp,File root,String reason,long limit,Entry... entries)throws Exception {
        try {
            TarExtractor.extract(archive(tmp,entries).toFile(),root,n->{},limit);
            throw new AssertionError("Accepted "+reason);
        } catch(IOException expected) {
            check(expected.getMessage().contains(reason),"Unexpected failure for "+reason+": "+expected);
        }
    }
    public static void main(String[] args)throws Exception {
        // Optional full-archive extraction is verified independently by Python.
        if(args.length==2) {
            Path root=Path.of(args[1]);Files.createDirectories(root);
            TarExtractor.extract(new File(args[0]),root.toFile(),n->{});
            check(Os.hardlinkCalls==0,"Runtime extraction called link(2)");
            return;
        }
        Path tmp=Files.createTempDirectory("memento-hardlink-test-");
        try {
            Path probe=tmp.resolve("probe");Files.writeString(probe,"test");
            try{Os.link(probe.toString(),tmp.resolve("denied").toString());throw new AssertionError("Host adapter permits hardlinks");}
            catch(IOException expected){check(expected.getMessage().contains("EACCES"),"Wrong simulated denial");}
            Os.hardlinkCalls=0;
            Path root=Files.createDirectory(tmp.resolve("root"));
            // Forward references and reverse-ordered chains exercise deferral.
            TarExtractor.extract(archive(tmp,
                link("usr/bin/alias2","usr/bin/alias"),link("usr/bin/alias","usr/bin/tool"),
                file("usr/bin/tool",0701,"executable bytes"),file("usr/share/data",0600,"data bytes"),
                link("usr/share/copy","usr/share/data"),file("usr/share/empty",0644,""),link("usr/share/empty-copy","usr/share/empty"),
                sym("bin","usr/bin"),sym("guest-absolute","/usr/bin/tool")
            ).toFile(),root.toFile(),n->{});
            for(String name:new String[]{"usr/bin/alias","usr/bin/alias2"}) {
                Path p=root.resolve(name);
                check(Files.readString(p).equals("executable bytes"),"Executable contents lost");
                check(mode(p)==0755,"Executable permission bits lost");
                check(!Files.isSymbolicLink(p)&&!Files.isSameFile(root.resolve("usr/bin/tool"),p),"Hardlink was not expanded to an independent regular file");
            }
            check(Files.readString(root.resolve("usr/share/copy")).equals("data bytes"),"Data copy corrupted");
            check(mode(root.resolve("usr/share/copy"))==0644,"Data copy became executable");
            check(Files.size(root.resolve("usr/share/empty-copy"))==0,"Empty hardlink failed");
            check(Files.readSymbolicLink(root.resolve("bin")).toString().equals("usr/bin"),"Relative guest symlink changed");
            check(Files.readSymbolicLink(root.resolve("guest-absolute")).toString().equals("/usr/bin/tool"),"Absolute guest symlink changed");
            Files.writeString(root.resolve("usr/bin/alias"),"changed");
            check(Files.readString(root.resolve("usr/bin/tool")).equals("executable bytes"),"Copy writes changed the target");
            rejected(tmp,"Unsafe archive path",100,file("file",0644,"x"),link("../escaped","file"));
            rejected(tmp,"Unsafe archive path",100,link("copy","../probe"));
            rejected(tmp,"Unsafe archive path",100,link("copy","/etc/passwd"));
            rejected(tmp,"Unsafe archive path",100,link("copy","dir\\file"));
            rejected(tmp,"Invalid hardlink",100,link("copy","missing"));
            rejected(tmp,"Invalid hardlink",100,link("copy","other"),link("other","copy"));
            rejected(tmp,"Invalid hardlink",100,new Entry("directory",'5',"",0755,new byte[0]),link("copy","directory"));
            rejected(tmp,"Invalid hardlink",100,file("file",0644,"x"),link("file","file"));
            rejected(tmp,"Invalid hardlink",100,file("file",0644,"x"),file("copy",0644,"original"),link("copy","file"));
            rejected(tmp,"Invalid hardlink",100,file("file",0644,"x"),link("copy","file"),link("copy","file"));
            rejected(tmp,"Invalid hardlink",100,file("file",0644,"x"),sym("symlink","file"),link("copy","symlink"));
            rejected(tmp,"exceeds limits after expanding hardlinks",2,file("file",0644,"x"),link("copy","file"),link("copy2","copy"));
            rejected(tmp,"Runtime archive exceeds limits",0,file("file",0644,"x"));
            rejected(tmp,"Invalid runtime extraction limit",-1);
            rejected(tmp,"Invalid runtime extraction limit",10L*1024*1024*1024+1);
            Path symbolic=Files.createDirectory(tmp.resolve("existing-symlinks"));
            Files.writeString(symbolic.resolve("target"),"unchanged");
            Files.createSymbolicLink(symbolic.resolve("source"),Path.of("target"));
            rejectsRoot(tmp,symbolic.toFile(),"Invalid hardlink",100,link("copy","source"));
            Files.createSymbolicLink(symbolic.resolve("copy"),Path.of("absent"));
            rejectsRoot(tmp,symbolic.toFile(),"Invalid hardlink",100,link("copy","target"));
            Path escaped=Files.createDirectory(tmp.resolve("confined"));
            Files.createSymbolicLink(escaped.resolve("outside"),tmp);
            rejectsRoot(tmp,escaped.toFile(),"Archive path escapes runtime",100,link("copy","outside/probe"));
            // A controlled usable-space value exercises both reserve checks.
            File noSpace=new File(Files.createTempDirectory(tmp,"storage-").toString()) {
                @Override public long getUsableSpace(){return 128L*1024*1024;}
            };
            rejectsRoot(tmp,noSpace,"Not enough storage to unpack runtime",100,file("file",0644,"x"));
            File copyNoSpace=new File(Files.createTempDirectory(tmp,"storage-copy-").toString()) {
                int checks;
                @Override public long getUsableSpace(){return 128L*1024*1024+(checks++==0?1:0);}
            };
            rejectsRoot(tmp,copyNoSpace,"Not enough storage to expand runtime hardlinks",100,file("file",0644,"x"),link("copy","file"));
            check(!Files.exists(tmp.resolve("escaped")),"Traversal escaped the extraction root");
            check(Os.hardlinkCalls==0,"Extraction attempted Android-denied link(2)");
            System.out.println("PASS: hardlink denial, independent copies, modes, empty files, forward references/chains, guest symlinks, target/path rejection, byte limits and storage reserve");
        } finally {TarExtractor.remove(tmp.toFile());}
    }
}
