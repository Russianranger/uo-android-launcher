package io.github.russianranger.trasc;

import android.system.Os;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.zip.GZIPInputStream;

/** Extracts our GNU/USTAR runtime; all links are deferred until regular files finish. */
final class TarExtractor {
    interface Progress {void update(int count);}
    static File path(File root,String name) throws IOException {
        if(name.startsWith("/")||name.contains("\\")||name.indexOf('\0')>=0) throw new IOException("Unsafe archive path");
        for(String component:name.split("/"))if(component.equals(".."))throw new IOException("Unsafe archive path");
        File file=new File(root,name).getCanonicalFile();
        if(!file.toPath().startsWith(root.getCanonicalFile().toPath()))throw new IOException("Archive path escapes runtime");
        return file;
    }
    static void extract(File archive,File root,Progress progress) throws Exception {
        List<String[]> links=new ArrayList<>(); long total=0; int count=0; String longName=null,longLink=null;
        try(InputStream in=new BufferedInputStream(new GZIPInputStream(new FileInputStream(archive)),1024*1024)) {
            byte[] header=new byte[512];
            while(true) {
                full(in,header,512);
                boolean zero=true; for(byte b:header)if(b!=0){zero=false;break;} if(zero)break;
                long checksum=octal(header,148,8), actual=0;
                for(int i=0;i<512;i++)actual+=(i>=148&&i<156)?32:header[i]&255;
                if(checksum!=actual)throw new IOException("Corrupt tar header");
                long size=octal(header,124,12); int mode=(int)octal(header,100,8); char type=(char)header[156];
                if(size<0||size>8L*1024*1024*1024 || (total+=size)>10L*1024*1024*1024 || ++count>400000)throw new IOException("Runtime archive exceeds limits");
                String name=text(header,0,100), prefix=text(header,345,155), link=text(header,157,100);
                if(!prefix.isEmpty())name=prefix+"/"+name;
                if(type=='L'||type=='K') {
                    if(size>16384)throw new IOException("Archive path is too long");
                    byte[] data=new byte[(int)size]; full(in,data,data.length);
                    String extended=new String(data,StandardCharsets.UTF_8).replace("\0","");
                    if(type=='L')longName=extended;else longLink=extended;
                } else {
                    if(longName!=null){name=longName;longName=null;} if(longLink!=null){link=longLink;longLink=null;}
                    File dest=path(root,name);
                    if(type=='0'||type=='\0') {
                        if(size>root.getUsableSpace()-128L*1024*1024)throw new IOException("Not enough storage to unpack runtime");
                        dest.getParentFile().mkdirs();
                        try(OutputStream out=new FileOutputStream(dest)){transfer(in,out,size);}
                        Os.chmod(dest.getPath(),(mode&0111)!=0?0755:0644);
                    } else if(type=='5') {dest.mkdirs(); if(size!=0)throw new IOException("Malformed directory entry");}
                    else if(type=='1'||type=='2') {if(size!=0)throw new IOException("Malformed link");links.add(new String[]{name,link,String.valueOf(type)});}
                    else throw new IOException("Unsupported runtime tar member; use the release runtime archive (type "+type+")");
                }
                skip(in,(512-size%512)%512); if(count%500==0)progress.update(count);
            }
        }
        // Hardlinks point only to already extracted regular files, before symlinks exist.
        for(String[] link:links)if(link[2].equals("1")) {
            File dest=path(root,link[0]),source=path(root,link[1]); dest.getParentFile().mkdirs();
            if(!source.isFile()||dest.exists())throw new IOException("Invalid hardlink");
            Os.link(source.getPath(),dest.getPath());
        }
        for(String[] link:links)if(link[2].equals("2")) {
            File dest=path(root,link[0]); dest.getParentFile().mkdirs();
            // A guest absolute link must remain absolute for PRoot's path translation.
            if(link[1].isEmpty()||link[1].indexOf('\0')>=0||Files.exists(dest.toPath(),LinkOption.NOFOLLOW_LINKS))throw new IOException("Invalid symlink");
            Os.symlink(link[1],dest.getPath());
        }
        progress.update(count);
    }
    static void transfer(InputStream in,OutputStream out,long size)throws IOException {byte[] b=new byte[1024*1024];while(size>0){int n=in.read(b,0,(int)Math.min(size,b.length));if(n<0)throw new EOFException("Truncated runtime archive");out.write(b,0,n);size-=n;}}
    static void full(InputStream in,byte[] b,int length)throws IOException {int offset=0;while(offset<length){int n=in.read(b,offset,length-offset);if(n<0)throw new EOFException("Truncated runtime archive");offset+=n;}}
    static void skip(InputStream in,long n)throws IOException {while(n-->0)if(in.read()<0)throw new EOFException();}
    static String text(byte[] b,int at,int length){int end=at;while(end<at+length&&b[end]!=0)end++;return new String(b,at,end-at,StandardCharsets.UTF_8);}
    static long octal(byte[] b,int at,int length)throws IOException {String s=text(b,at,length).trim();try{return s.isEmpty()?0:Long.parseLong(s,8);}catch(NumberFormatException e){throw new IOException("Invalid tar size");}}
    static void remove(File file)throws IOException {
        if(!Files.exists(file.toPath(),LinkOption.NOFOLLOW_LINKS))return;
        if(!Files.isSymbolicLink(file.toPath())&&file.isDirectory()){File[] children=file.listFiles();if(children==null)throw new IOException("Cannot read "+file);for(File child:children)remove(child);}
        if(!file.delete())throw new IOException("Cannot remove "+file);
    }
}
