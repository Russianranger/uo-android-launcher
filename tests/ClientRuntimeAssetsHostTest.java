package io.github.russianranger.trasc;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.zip.*;

/** Test deployed APK contents, never the repository's Python import path. */
public final class ClientRuntimeAssetsHostTest {
    static final String IMPORT_PROBE="import pathlib,sys,json,hashlib,base64; "
        +"root=pathlib.Path(sys.argv[1]).resolve(); sys.path.insert(0,str(root)); "
        +"import uo_client_runner,client_prefix,client_health,client_render_trace,client_music_cache,client_frame_budget,client_atlas_uploads,client_cold_trace,client_cold_resources,client_map_metadata,client_map_metadata_variants,client_graphics,client_audio,client_presentation,uo_content,log_retention; "
        +"assert pathlib.Path(uo_client_runner.__file__).parent.resolve()==root; "
        +"assert client_graphics.digest(root/client_graphics.ASSET)==client_graphics.FIXED_SDL; "
        +"assert len(client_cold_resources.VARIANTS)==7; "
        +"assert all(base64.b64decode((root/row[3]).read_bytes().strip(),validate=True) for row in client_cold_resources.VARIANTS); "
        +"assert len(client_map_metadata_variants.VARIANTS)==8; "
        +"assert all(base64.b64decode((root/row[3]).read_bytes().strip(),validate=True) for row in client_map_metadata_variants.VARIANTS); "
        +"audio=json.loads((root/'audio-bundle.json').read_text()); "
        +"assert audio['buffer_policy']==3 and audio['minimum_period_frames']==32 and audio['minimum_buffer_frames']==64; "
        +"assert hashlib.sha256((root/'libasound_module_pcm_trasc.so').read_bytes()).hexdigest()==audio['sha256']; "
        +"presentation=json.loads((root/'presentation-bundle.json').read_text()); "
        +"assert presentation['metadata_cache']==1; "
        +"assert hashlib.sha256((root/'x11-frame-bridge').read_bytes()).hexdigest()==presentation['sha256']; "
        +"trace=json.loads((root/'vulkan-trace-bundle.json').read_text()); "
        +"layer=(root/'libmemento-vulkan-trace.so').read_bytes(); "
        +"assert trace['format']==1 and trace['revision']==2 and hashlib.sha256(layer).hexdigest()==trace['sha256']; "
        +"assert layer[:5]==b'\\x7fELF\\x02' and int.from_bytes(layer[18:20],'little')==183; "
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

    static void mapMetadataProbe(Path deployed,Path fixture,Path verifier,Path helper)throws Exception {
        // Only original assemblies are supplied externally. The tested module,
        // generated variant manifest, deltas and managed helper come from APK.
        ProcessBuilder builder=new ProcessBuilder("python3","-I","-B",verifier.toAbsolutePath().toString(),
            deployed.toString(),fixture.toAbsolutePath().toString(),helper.toAbsolutePath().toString());
        builder.directory(deployed.toFile()).redirectErrorStream(true);
        Path output=deployed.resolve("map-metadata-check.txt");builder.redirectOutput(output.toFile());
        Process process=builder.start();
        if(!process.waitFor(120,TimeUnit.SECONDS)){
            process.destroyForcibly();process.waitFor();throw new AssertionError("Packaged map metadata test timed out");
        }
        String text=Files.readString(output,StandardCharsets.UTF_8);
        if(process.exitValue()!=0||!text.contains("DEPLOYED_MAP_METADATA_OK variants=8 pairs=16"))
            throw new AssertionError("Packaged map metadata payload failed:\n"+text);
        System.out.print(text);
    }

    public static void main(String[] args)throws Exception {
        if(args.length!=4)throw new IllegalArgumentException("Pass APK, exact original client fixture, map metadata verifier and built helper paths");
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
            mapMetadataProbe(temporary,Path.of(args[1]),Path.of(args[2]),Path.of(args[3]));
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
