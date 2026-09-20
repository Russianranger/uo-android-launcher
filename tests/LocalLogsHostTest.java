package io.github.russianranger.trasc;

import java.io.*;
import java.nio.file.*;
import java.util.zip.*;

public final class LocalLogsHostTest {
    static void check(boolean condition,String message) {
        if(!condition)throw new AssertionError(message);
    }
    static void rejected(File work,String relative)throws Exception {
        try{LocalLogs.checked(work.toPath(),relative);throw new AssertionError("Accepted unsafe path: "+relative);}
        catch(IOException expected){}
    }
    public static void main(String[] args)throws Exception {
        Path base=Files.createTempDirectory("memento-logs-test");
        // Android Context paths may use /data/user/0 while canonical files use /data/data.
        Path actual=base.resolve("user/0");Files.createDirectories(actual);
        Path alias=base.resolve("data");Files.createSymbolicLink(alias,actual);
        File work=alias.resolve("package/files/work").toFile();
        Files.createDirectories(work.toPath().resolve("logs"));
        Files.writeString(work.toPath().resolve("logs/client-wine.log"),"startup failure evidence");
        File archive=LocalLogs.export(work,"{\"version\":\"test\"}");
        try(ZipFile zip=new ZipFile(archive)) {
            check(zip.getEntry("logs/client-wine.log")!=null,"Alias path lost the Wine log");
            check(zip.getEntry("status.json")!=null,"Missing status");
            for(var entries=zip.entries();entries.hasMoreElements();) {
                String name=entries.nextElement().getName();
                check(!name.startsWith("/")&&!name.contains(".."),"Unsafe ZIP member: "+name);
            }
        }
        check(LocalLogs.tail(work,"client-wine.log").contains("startup failure"),"Alias tail failed");
        Path client=work.toPath().resolve("client/current/Client");
        Files.createDirectories(client.resolve("Logs/Network"));
        Files.writeString(client.resolve("Logs/2026-09-20_06-20-00_crash.txt"),"TazUO crash evidence");
        Files.writeString(client.resolve("settings.json"),"private credentials");
        Files.writeString(client.resolve("Logs/Network/packets.log"),"private network data");
        Files.writeString(client.resolve("Logs/chat.txt"),"private chat data");
        Path secret=base.resolve("secret.txt");Files.writeString(secret,"outside workspace");
        Files.createSymbolicLink(work.toPath().resolve("logs/secret.log"),secret);
        Files.createSymbolicLink(work.toPath().resolve("logs/redirect"),client);
        // Even a link to a regular in-work log must be rejected before resolution.
        Files.createSymbolicLink(work.toPath().resolve("logs/alias.log"),Path.of("client-wine.log"));
        rejected(work,"logs/alias.log");rejected(work,"logs/redirect/Logs/chat.txt");
        rejected(work,"../secret.txt");rejected(work,"/etc/passwd");rejected(work,"logs/../run/api-token");
        rejected(work,"logs\\secret.txt");
        String crash="client/Client/Logs/2026-09-20_06-20-00_crash.txt";
        check(LocalLogs.inventory(work).containsKey(crash),"Nested crash log missing from Journal");
        check(LocalLogs.tail(work,crash).contains("TazUO crash evidence"),"Nested crash log cannot be read");
        archive=LocalLogs.export(work,"{}");
        try(ZipFile zip=new ZipFile(archive)) {
            check(zip.getEntry("client/current/Client/Logs/2026-09-20_06-20-00_crash.txt")!=null,"Crash report not exported");
            check(zip.getEntry("logs/secret.log")==null&&zip.getEntry("logs/alias.log")==null,"Followed a log symlink");
            for(var entries=zip.entries();entries.hasMoreElements();) {
                String name=entries.nextElement().getName();
                check(!name.contains("settings")&&!name.contains("packets")&&!name.contains("chat"),"Exported unrelated client data");
            }
        }
        try(var paths=Files.walk(base)) {
            for(Path path:paths.sorted(java.util.Comparator.reverseOrder()).toList())Files.delete(path);
        }
        System.out.println("Log export: Android aliases, nested TazUO crashes, and path/symlink exclusions passed");
    }
}
