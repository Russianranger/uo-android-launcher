package io.github.russianranger.trasc;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;

/** Fixed test phases share the game's UTC clock and remain in support exports. */
final class DiagnosticMarks {
    static final String[] LABELS={"Outdoor first pass","Interior first entry","Interior exit","Interior re-entry","Outdoor retrace","Test finished"};
    static final String[] IDS={"outdoor_cold","interior_cold","interior_exit","interior_warm","outdoor_warm","finished"};
    static synchronized void write(File work,int phase,String attempt,String utc,long elapsedNs)throws IOException {
        if(phase<0||phase>=IDS.length)throw new IllegalArgumentException("Unknown test phase");
        // Attempt IDs and UTC are parsed as timestamps before writing JSON.
        Instant.parse(attempt);Instant.parse(utc);
        Path log=LocalLogs.checked(work.toPath(),"logs/client-test-markers.log");Files.createDirectories(log.getParent());
        if(Files.exists(log,LinkOption.NOFOLLOW_LINKS)&&Files.size(log)>1024*1024)LogRetention.rotate(log.toFile());
        String line="{\"utc\":\""+utc+"\",\"attempt_started_utc\":\""+attempt+"\",\"elapsed_realtime_ns\":"+elapsedNs+",\"phase\":\""+IDS[phase]+"\"}\n";
        Files.write(log,line.getBytes(StandardCharsets.UTF_8),StandardOpenOption.CREATE,StandardOpenOption.APPEND,LinkOption.NOFOLLOW_LINKS);
    }
    static synchronized void surface(File work,String line)throws IOException {
        Path log=LocalLogs.checked(work.toPath(),"logs/client-surface-trace.log");Files.createDirectories(log.getParent());
        if(Files.exists(log,LinkOption.NOFOLLOW_LINKS)&&Files.size(log)>1024*1024)LogRetention.rotate(log.toFile());
        Files.write(log,(line+"\n").getBytes(StandardCharsets.UTF_8),StandardOpenOption.CREATE,StandardOpenOption.APPEND,LinkOption.NOFOLLOW_LINKS);
    }
}
