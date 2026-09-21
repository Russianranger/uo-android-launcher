using System.Collections.Concurrent;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using Memento;

if(args.Length != 2) throw new ArgumentException("client-folder original|budget");
bool budgeted = args[1] == "budget";
var folder = Path.GetFullPath(args[0]);
AssemblyLoadContext.Default.Resolving += (_, name) => {
    var path = Path.Combine(folder, name.Name + ".dll");
    return File.Exists(path) ? AssemblyLoadContext.Default.LoadFromAssemblyPath(path) : null;
};
void Check(bool ok,string why) { if(!ok) throw new Exception(why); }
const BindingFlags Fields = BindingFlags.Instance|BindingFlags.NonPublic;
var assembly = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(folder,"TazUO.dll"));
var parserType = assembly.GetType("ClassicUO.Network.PacketHandlers.PacketParser",true)!;
var parser = parserType.GetField("Instance")!.GetValue(null)!;
// Retain the production singleton, queue and methods. Replace only handlers and
// world setup so this real-assembly probe does not initialize a game display.
foreach(var field in parserType.GetFields(Fields)) {
    object value = field.Name == "_readingBuffer" ? new byte[65536] : field.FieldType.IsArray ? Array.CreateInstance(field.FieldType.GetElementType()!,256) :
        Activator.CreateInstance(field.FieldType,field.FieldType.GetConstructors()[0].GetParameters().Select(p=>p.DefaultValue).ToArray())!;
    field.SetValue(parser,value);
}
var network = assembly.GetType("ClassicUO.Network.AsyncNetClient",true)!;
var table = assembly.GetType("ClassicUO.Network.PacketsTable",true)!;
var constructor = table.GetConstructors().Single();
var tableValue = constructor.Invoke(new[]{Enum.ToObject(constructor.GetParameters()[0].ParameterType,0x07000F01u)});
network.GetProperty("PacketsTable")!.SetValue(null,tableValue);
((short[])table.GetField("_packetsTable",Fields)!.GetValue(tableValue)!)[0xFE] = -1;
var stream = parserType.GetField("_buffer",Fields)!.GetValue(parser)!;
var pluginStream = parserType.GetField("_pluginsBuffer",Fields)!.GetValue(parser)!;
var enqueue = new DynamicMethod("Enqueue",null,new[]{typeof(object),typeof(byte[])},typeof(Observed).Module,true);
var il = enqueue.GetILGenerator(); il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Castclass,stream.GetType()); il.Emit(OpCodes.Ldarg_1);
il.Emit(OpCodes.Call,typeof(Span<byte>).GetMethod("op_Implicit",new[]{typeof(byte[])})!);
il.Emit(OpCodes.Callvirt,stream.GetType().GetMethod("Enqueue",new[]{typeof(Span<byte>)})!); il.Emit(OpCodes.Ret);
var append = (Action<object,byte[]>)enqueue.CreateDelegate(typeof(Action<object,byte[]>));
var handlerField = parserType.GetField("_handlers",Fields)!;
var handlerType = handlerField.FieldType.GetElementType()!;
var parameters = handlerType.GetMethod("Invoke")!.GetParameters().Select(p=>p.ParameterType).ToArray();
var handler = new DynamicMethod("Handle",null,parameters,typeof(Observed).Module,true);
il = handler.GetILGenerator();il.Emit(OpCodes.Ldarg_1);il.Emit(OpCodes.Call,parameters[1].GetElementType()!.GetMethod("ReadUInt16BE")!);
il.Emit(OpCodes.Call,typeof(Observed).GetMethod("Record")!);il.Emit(OpCodes.Ret);
((Array)handlerField.GetValue(parser)!).SetValue(handler.CreateDelegate(handlerType),0xFE);
var parse = parserType.GetMethods(Fields).Single(m=>m.Name=="ParsePackets");
var gameType = assembly.GetType("ClassicUO.GameController",true)!;
var clientType = assembly.GetType("ClassicUO.Client",true)!;
var game = RuntimeHelpers.GetUninitializedObject(gameType);
clientType.GetField("<Game>k__BackingField",BindingFlags.Static|BindingFlags.NonPublic)!.SetValue(null,game);
var uo = gameType.GetField("<UO>k__BackingField",Fields)!;
uo.SetValue(game,RuntimeHelpers.GetUninitializedObject(uo.FieldType));
var socket = network.GetProperty("Socket")!.GetValue(null)!;
var queue = (ConcurrentQueue<byte[]>)network.GetField("_incomingMessages",Fields)!.GetValue(socket)!;
var process = gameType.GetMethod("ProcessNetworkPackets",Fields)!;
int Length(object buffer) => (int)buffer.GetType().GetProperty("Length")!.GetValue(buffer)!;
void Frame() => process.Invoke(game,null);
byte[] Packet(int n) => new byte[]{0xFE,0,5,(byte)(n>>8),(byte)n};
Frame(); Frame();
queue.Enqueue(Enumerable.Range(0,14000).SelectMany(Packet).ToArray());
int frames = 0, maxPerFrame = 0;
while(Observed.Values.Count < 14000 && frames++ < 200) {
    int before = Observed.Values.Count; Frame(); maxPerFrame = Math.Max(maxPerFrame,Observed.Values.Count-before);
}
Check(Observed.Values.SequenceEqual(Enumerable.Range(0,14000)),"Dropped/reordered/repeated burst packets");
Check(Length(stream)==0 && queue.IsEmpty,"Retained bytes were not drained without new socket messages");
Check(budgeted ? frames>=14 && maxPerFrame<=1000 : frames==1 && maxPerFrame==14000,"Per-packet budget was not applied");
if(budgeted) {
    // An indivisible handler can overrun 5ms; the following packet must yield.
    Observed.Values.Clear(); Observed.Delay=true;
    queue.Enqueue(Packet(15000).Concat(Packet(15001)).ToArray());Frame();
    Check(Observed.Values.SequenceEqual(new[]{15000}) && Length(stream)==5,"Time budget failed to yield after expensive handler");
    Observed.Delay=false;Frame();Check(Observed.Values.SequenceEqual(new[]{15000,15001}),"Time-budget continuation failed");
}
Observed.Values.Clear();
var split=Packet(16000);queue.Enqueue(split[..2]);Frame();Check(Observed.Values.Count==0,"Partial header dispatched");
queue.Enqueue(split[2..4]);Frame();Check(Observed.Values.Count==0,"Partial body dispatched");
queue.Enqueue(split[4..].Concat(Packet(16001)).ToArray());Frame();
Check(Observed.Values.SequenceEqual(new[]{16000,16001}),"Split packet reassembly changed");
if(budgeted) {
    Observed.Values.Clear();append(pluginStream,Packet(17000));Frame();
    Check(Observed.Values.SequenceEqual(new[]{17000}),"Plugin packets stranded without socket data");
    Observed.Values.Clear();Observed.ThrowAt=18000;
    queue.Enqueue(Packet(18000).Concat(Packet(18001)).ToArray());
    try{Frame();throw new Exception("Handler failure was swallowed");}
    catch(TargetInvocationException e) when(e.InnerException is InvalidOperationException){}
    Observed.ThrowAt=-1;Thread.Sleep(8);Check(FrameBudget.More(),"Budget remained active after handler exception");
    bool released=Task.Run(()=>{if(!Monitor.TryEnter(stream,1000))return false;Monitor.Exit(stream);return true;}).Result;
    Check(released,"Original parser lock leaked");Frame();
    Check(Observed.Values.SequenceEqual(new[]{18000,18001}),"Exception continuation changed packet order");
    Observed.Values.Clear();append(pluginStream,Packet(19000));long began=FrameBudget.BeginNetwork();
    try{Thread.Sleep(8);parse.Invoke(parser,new[]{null,pluginStream,(object)false});}
    finally{FrameBudget.EndNetwork(began);}
    Check(Observed.Values.SequenceEqual(new[]{19000}),"Plugin traffic incorrectly budgeted");
    Observed.Values.Clear();append(stream,Packet(20000));append(pluginStream,Packet(20001));
    parserType.GetMethod("MementoClearBuffers",Fields)!.Invoke(parser,null);
    Check(Length(stream)==0&&Length(pluginStream)==0,"Old-connection buffers survived reset");
    queue.Enqueue(Packet(20002));Frame();Check(Observed.Values.SequenceEqual(new[]{20002}),"Connection reset replayed stale data");
    var state=typeof(FrameBudget).GetField("state",BindingFlags.Static|BindingFlags.NonPublic)!.GetValue(null)!;
    state.GetType().GetField("nextReport",Fields|BindingFlags.Public)!.SetValue(state,1L);
    long timing=FrameBudget.Begin(FrameBudget.Update);FrameBudget.End(FrameBudget.Update,timing);
}
Console.WriteLine($"FRAME_BUDGET_OK actual_assembly=true mode={args[1]} frames={frames} max_packets_per_frame={maxPerFrame} ordered=true split_packets=true retained_bytes=true exception_cleanup={budgeted} plugins={budgeted}");

public static class Observed {
    public static readonly List<int> Values = new();
    public static bool Delay; public static int ThrowAt=-1;
    public static void Record(int value) { Values.Add(value);if(Delay)Thread.Sleep(8);if(value==ThrowAt)throw new InvalidOperationException("fixture handler"); }
}
