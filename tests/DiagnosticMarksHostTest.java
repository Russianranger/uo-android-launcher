package io.github.russianranger.trasc;
import java.nio.file.*;

public final class DiagnosticMarksHostTest {
    public static void main(String[] args)throws Exception {
        Path root=Files.createTempDirectory("memento-markers-");
        String attempt="2026-10-03T12:00:00Z";
        for(int i=0;i<DiagnosticMarks.IDS.length;i++)DiagnosticMarks.write(root.toFile(),i,attempt,"2026-10-03T12:01:00Z",1234);
        String output=Files.readString(root.resolve("logs/client-test-markers.log"));
        if(output.lines().count()!=6||!output.contains("\"phase\":\"outdoor_cold\"")||!output.contains("\"attempt_started_utc\":\""+attempt+"\""))throw new AssertionError("Phase/session correlation lost");
        DiagnosticMarks.surface(root.toFile(),"SURFACE_FRAME utc=2026-10-03T12:01:00Z lock_ms=123");
        if(!Files.readString(root.resolve("logs/client-surface-trace.log")).contains("lock_ms=123"))throw new AssertionError("Surface trace missing");
        try{DiagnosticMarks.write(root.toFile(),0,"bad timestamp","2026-10-03T12:01:00Z",1234);throw new AssertionError("Invalid timestamp accepted");}catch(java.time.format.DateTimeParseException expected){}
        Path log=root.resolve("logs/client-test-markers.log");Files.delete(log);Files.createSymbolicLink(log,root.resolve("target"));
        try{DiagnosticMarks.write(root.toFile(),0,attempt,"2026-10-03T12:01:00Z",1234);throw new AssertionError("Symlink accepted");}catch(java.io.IOException expected){}
        System.out.println("DIAGNOSTIC_MARKERS_OK phases=6 session_id=true surface_export=true symlinks_rejected=true");
    }
}
