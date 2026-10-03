using System.Diagnostics;
using System.Globalization;
using System.Reflection;
using Memento;

bool enabled = args.Single() == "enabled";
Environment.SetEnvironmentVariable("MEMENTO_COLD_TRACE",enabled ? "1" : "0");
const BindingFlags PrivateStatic = BindingFlags.Static | BindingFlags.NonPublic;
const BindingFlags Fields = BindingFlags.Instance | BindingFlags.NonPublic;
var field = typeof(ColdTrace).GetField("state",PrivateStatic)!;
var output = new StringWriter(CultureInfo.InvariantCulture);var saved = Console.Error;Console.SetError(output);
void Check(bool ok,string why) { if(!ok)throw new Exception(why); }
void Set(string name,object value) { var state=field.GetValue(null)!;state.GetType().GetField(name,Fields)!.SetValue(state,value); }
object Get(string name) { var state=field.GetValue(null)!;return state.GetType().GetField(name,Fields)!.GetValue(state)!; }
void Stage(int stage) { long began=FrameBudget.Begin(stage);FrameBudget.End(stage,began); }
Dictionary<string,string> Parse(string prefix) => output.ToString().Split('\n').Last(s=>s.StartsWith(prefix+" ",StringComparison.Ordinal)).Split(' ',StringSplitOptions.RemoveEmptyEntries).Skip(1).Select(s=>s.TrimEnd('\r').Split('=',2)).ToDictionary(p=>p[0],p=>p[1]);
try
{
    FrameBudget.Announce();Stage(FrameBudget.Update);Stage(FrameBudget.Draw);Stage(FrameBudget.EndDraw);
    ColdTrace.EndNative(0,ColdTrace.BeginNative(0));
    if(!enabled) { Check(!output.ToString().Contains("COLD_")&&field.GetValue(null)==null,"Disabled diagnostics created state or logged"); }
    else
    {
        long update=FrameBudget.Begin(FrameBudget.Update);
        var allocation=new byte[4096];GC.KeepAlive(allocation);
        FrameBudget.EndPacket(FrameBudget.BeginPacket(new byte[]{0x20},true));
        ColdTrace.Atlas(5,2,3,8192,Stopwatch.Frequency/100,Stopwatch.Frequency/50,1);
        for(int i=0;i<12;i++)ColdTrace.EndNative(13,Stopwatch.GetTimestamp()-Stopwatch.Frequency*60/1000);
        FrameBudget.End(FrameBudget.Update,update);Stage(FrameBudget.Draw);Stage(FrameBudget.EndDraw);
        Set("began",Stopwatch.GetTimestamp()-Stopwatch.Frequency*150/1000);Stage(FrameBudget.Update);
        var row=Parse("COLD_FRAME");
        Check(row["packet_id"]=="20"&&row["packet_network"]=="true"&&row["packet_calls"]=="1","Packet/frame association lost");
        Check(row["atlas_sprites"]=="5"&&row["atlas_uploads"]=="2"&&row["atlas_merged"]=="3"&&row["atlas_upload_bytes"]=="8192","Atlas frame counters lost");
        Check(long.Parse(row["allocated_bytes"])>=4096&&row["thread_cpu_ms"]!="unavailable"&&row["enddraw_cpu_ms"]!="unavailable","Allocation/CPU measurement unavailable");
        Check(row["native_calls"]=="12"&&row["native_op"]=="FNA3D_SwapBuffers","Native call attribution lost");
        Check(output.ToString().Split('\n').Count(s=>s.StartsWith("FNA_CALL "))==8&&(long)Get("nativeSuppressed")==4,"Native logs are not bounded");
        for(int i=0;i<12;i++){Set("began",Stopwatch.GetTimestamp()-Stopwatch.Frequency*1100/1000);Stage(FrameBudget.Update);}
        Set("nextReport",1L);Stage(FrameBudget.Update);var summary=Parse("COLD_WINDOW");
        Check(summary["gap_ge_1000ms"]=="12"&&long.Parse(summary["long_records_suppressed"])>0,"Suppression lost histogram counts");
        Check(output.ToString().Split('\n').Count(s=>s.StartsWith("COLD_FRAME "))==8,"Long-frame logs are not bounded");
        Check((long)Get("packetCalls")==0&&(long)Get("atlasSprites")==0&&(int)Get("nativeWritten")==0,"Per-frame/window state leaked");
        // Hot observations allocate no strings, delegates, arrays or objects.
        for(int i=0;i<100;i++){long began=ColdTrace.BeginNative(0);ColdTrace.EndNative(0,began);}
        long before=GC.GetAllocatedBytesForCurrentThread();
        for(int i=0;i<10000;i++){long began=ColdTrace.BeginNative(0);ColdTrace.EndNative(0,began);ColdTrace.Atlas(1,1,0,256,0,0,0);}
        Check(GC.GetAllocatedBytesForCurrentThread()==before,"Warm native/atlas observations allocate");
        Task.Run(()=>{Stage(FrameBudget.Update);ColdTrace.EndNative(1,ColdTrace.BeginNative(1));Check((long)Get("nativeCalls")==1,"Thread state was shared");}).GetAwaiter().GetResult();
        Check((long)Get("nativeCalls")>10000,"Worker replaced the render-thread counters");
        Console.SetError(new FailedWriter());ColdTrace.EndNative(13,Stopwatch.GetTimestamp()-Stopwatch.Frequency);Set("nextReport",1L);Stage(FrameBudget.Update);
    }
}
finally{Console.SetError(saved);}
Console.WriteLine("COLD_TRACE_OK mode="+args[0]+" bounded=true histograms=true attribution=true allocation_free=true");
sealed class FailedWriter : TextWriter { public override System.Text.Encoding Encoding=>System.Text.Encoding.UTF8;public override void WriteLine(string value)=>throw new IOException("fixture full log"); }
