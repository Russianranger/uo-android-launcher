package io.github.russianranger.trasc;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.zip.*;

/** Test deployed APK contents, never the repository's Python import path. */
public final class ClientRuntimeAssetsHostTest {
    static final String IMPORT_PROBE="import pathlib,sys,json,hashlib; "
        +"root=pathlib.Path(sys.argv[1]).resolve(); sys.path.insert(0,str(root)); "
        +"import uo_client_runner,client_prefix,client_health,client_render_trace,client_graphics,client_audio,client_presentation,uo_content,log_retention; "
        +"assert pathlib.Path(uo_client_runner.__file__).parent.resolve()==root; "
        +"assert client_graphics.digest(root/client_graphics.ASSET)==client_graphics.FIXED_SDL; "
        +"audio=json.loads((root/'audio-bundle.json').read_text()); "
        +"assert audio['buffer_policy']==3 and audio['minimum_period_frames']==32 and audio['minimum_buffer_frames']==64; "
        +"assert hashlib.sha256((root/'libasound_module_pcm_trasc.so').read_bytes()).hexdigest()==audio['sha256']; "
        +"presentation=json.loads((root/'presentation-bundle.json').read_text()); "
        +"assert presentation['metadata_cache']==1; "
        +"assert hashlib.sha256((root/'x11-frame-bridge').read_bytes()).hexdigest()==presentation['sha256']; "
        +"print('DEPLOYED_CLIENT_IMPORT_OK',flush=True)";

    static String probe(Path deployed,boolean expectSuccess)throws Exception {
        ProcessBuilder builder=new ProcessBuilder("python3","-I","-B","-c",IMPORT_PROBE,deployed.toString());
        builder.directory(deployed.toFile()).redirectErrorStream(true);
        Path output=deployed.resolve("import-check.txt");builder.redirectOutput(output.toFile());
        Process process=builder.start();
        if(!process.waitFor(15,TimeUnit.SECONDS)){
            process.destroyForcibly();process.waitFor();throw new AssertionError("Deployed import timed out");
        }
        String text=Files.readString(output,StandardCharsets.UTF_8);
        if(expectSuccess&&(process.exitValue()!=0||!text.contains("DEPLOYED_CLIENT_IMPORT_OK")))
            throw new AssertionError("Packaged client cannot import:\n"+text);
        if(!expectSuccess&&(process.exitValue()==0||!text.contains("No module named 'client_health'")))
            throw new AssertionError("Missing-module negative control was not detected:\n"+text);
        return text;
    }

    public static void main(String[] args)throws Exception {
        if(args.length!=1)throw new IllegalArgumentException("Pass the built APK path");
        Path temporary=Files.createTempDirectory("memento-apk-client-");
        try(ZipFile apk=new ZipFile(args[0])){
            Set<String> names=new HashSet<>();
            for(String name:ClientRuntimeAssets.FILES){
                if(!names.add(name))throw new AssertionError("Duplicate asset "+name);
                ZipEntry entry=apk.getEntry("assets/"+name);
                if(entry==null||entry.isDirectory())throw new AssertionError("Missing APK asset "+name);
                try(InputStream in=apk.getInputStream(entry)){Files.copy(in,temporary.resolve(name));}
            }
            probe(temporary,true);
            // The module was present in 0.1.8's APK but omitted at deployment.
            // Remove only the deployed copy and require the exact failure.
            Path health=temporary.resolve("client_health.py");
            byte[] module=Files.readAllBytes(health);Files.delete(health);
            probe(temporary,false);
            Files.write(health,module);probe(temporary,true);
            System.out.println("APK client deployment: "+names.size()+" assets present; isolated imports pass; missing client_health is detected and recovery passes");
        }finally{
            try(var entries=Files.walk(temporary)){
                for(Path path:entries.sorted(Comparator.reverseOrder()).toList())Files.deleteIfExists(path);
            }
        }
    }
}
