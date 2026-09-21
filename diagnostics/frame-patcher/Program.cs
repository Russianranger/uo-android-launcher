using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Security.Cryptography;

if (args.Length < 3) throw new ArgumentException("client.dll helper.dll output.dll [--inspect]");
string hash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[0]))).ToLowerInvariant();
if (hash != "b04066be1b1b475ca00e6982a980e2dd11b93abede00c79c68bde566bdcf947e" &&
    hash != "0dd83f1af66262f51871ab5eecf4e8a1da5798e5de3c4a5eb4b87f4a4dd8e305")
    throw new InvalidOperationException("Unrecognized client binary");
var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(args[0])));
resolver.AddSearchDirectory(Path.GetDirectoryName(typeof(object).Assembly.Location));
var constants = new ConstantMetadataResolver(resolver);
using var client = ModuleDefinition.ReadModule(args[0], new ReaderParameters { AssemblyResolver = resolver, MetadataResolver = constants });
constants.Record(client);
var controller = client.GetType("ClassicUO.GameController");
var parser = client.GetType("ClassicUO.Network.PacketHandlers.PacketParser");
var network = controller.Methods.Single(m => m.Name == "ProcessNetworkPackets");
var parse = parser.Methods.Single(m => m.Name == "ParsePackets" && m.Parameters.Count == 3);
if (args.Contains("--inspect")) {
    foreach (var method in new[] { network, parse }) {
        Console.WriteLine(method.FullName);
        foreach(var v in method.Body.Variables) Console.WriteLine("LOCAL " + v.Index + " " + v.VariableType.FullName);
        foreach(var i in method.Body.Instructions) Console.WriteLine(i);
    }
    foreach(var typeName in new[]{"ClassicUO.Game.Scenes.GameScene", "ClassicUO.Game.Managers.AudioManager"})
        foreach(var m in client.GetType(typeName).Methods.Where(m=>m.Name is "Load" or "Update" or "FillGameObjectList")) Console.WriteLine(m.FullName);
    foreach(var m in client.GetType("ClassicUO.Network.LoginHandshake").Methods.Where(m=>m.Name is "Connect" or "AfterRelayConnect")) {
        Console.WriteLine(m.FullName);foreach(var ins in m.Body.Instructions.Take(65)) Console.WriteLine(ins);
    }
    return;
}
using var helper = ModuleDefinition.ReadModule(args[1]);
var budget = helper.GetType("Memento.FrameBudget");
MethodReference Import(string name) => client.ImportReference(budget.Methods.Single(m => m.Name == name));
var branches = typeof(OpCodes).GetFields().Where(f => f.FieldType == typeof(OpCode))
    .Select(f => (OpCode)f.GetValue(null)!).ToDictionary(op => op.Name);
void Widen(MethodDefinition method) {
    foreach (var ins in method.Body.Instructions)
        if (ins.OpCode.OperandType == OperandType.ShortInlineBrTarget) ins.OpCode = branches[ins.OpCode.Name[..^2]];
}
// Wrap void boundaries with a finally so diagnostics and budget state cannot
// suppress exceptions or leave a parser budget active after a failed handler.
void Time(MethodDefinition method, int stage, bool isNetwork = false) {
    if (method.ReturnType.FullName != "System.Void") throw new Exception("Expected void boundary");
    Widen(method); var body = method.Body; var il = body.GetILProcessor();
    var began = new VariableDefinition(client.TypeSystem.Int64); body.Variables.Add(began); body.InitLocals = true;
    var first = body.Instructions[0];
    if (!isNetwork) il.InsertBefore(first, il.Create(OpCodes.Ldc_I4, stage));
    il.InsertBefore(first, il.Create(OpCodes.Call, Import(isNetwork ? "BeginNetwork" : "Begin")));
    il.InsertBefore(first, il.Create(OpCodes.Stloc, began));
    var done = il.Create(OpCodes.Ret);
    foreach (var ret in body.Instructions.Where(i => i.OpCode == OpCodes.Ret).ToArray()) { ret.OpCode = OpCodes.Leave; ret.Operand = done; }
    var cleanup = isNetwork ? il.Create(OpCodes.Ldloc, began) : il.Create(OpCodes.Ldc_I4, stage);
    foreach(var h in body.ExceptionHandlers) { if(h.TryEnd == null) h.TryEnd = cleanup; if(h.HandlerEnd == null) h.HandlerEnd = cleanup; }
    il.Append(cleanup); if (!isNetwork) il.Append(il.Create(OpCodes.Ldloc, began));
    il.Append(il.Create(OpCodes.Call, Import(isNetwork ? "EndNetwork" : "End"))); il.Append(il.Create(OpCodes.Endfinally)); il.Append(done);
    body.ExceptionHandlers.Add(new ExceptionHandler(ExceptionHandlerType.Finally) { TryStart = first, TryEnd = cleanup, HandlerStart = cleanup, HandlerEnd = done });
}
// Keep packet decoding, handlers, logging, locking and partial packet behavior
// exactly as imported. Only guard the start of a complete parsing iteration.
Widen(parse);
var pil = parse.Body.GetILProcessor();
var length = (MethodReference)parse.Body.Instructions.First(i => i.Operand is MethodReference m && m.Name == "get_Length").Operand;
var loopBranch = parse.Body.Instructions.Last(i => i.OpCode == OpCodes.Bgt);
var packetStart = (Instruction)loopBranch.Operand;
var loopExit = loopBranch.Next;
if (loopExit.OpCode != OpCodes.Leave) throw new Exception("Unexpected parser loop exit");
var guard = pil.Create(OpCodes.Ldarg_3);
foreach(var ins in new[]{ guard, pil.Create(OpCodes.Ldarg_2), pil.Create(OpCodes.Callvirt, length),
    pil.Create(OpCodes.Call, Import("CanParse")), pil.Create(OpCodes.Brfalse, loopExit) }) pil.InsertBefore(packetStart, ins);
loopBranch.Operand = guard;
var dequeue = parse.Body.Instructions.Single(i => i.Operand is MethodReference m && m.Name == "Dequeue");
if(dequeue.Next.OpCode != OpCodes.Pop) throw new Exception("Unexpected dequeue return");
var counted = pil.Create(OpCodes.Ldarg_3); pil.InsertAfter(dequeue.Next, counted);
pil.InsertAfter(counted, pil.Create(OpCodes.Call, Import("Consumed")));

// Replace the outer 25-message cap with the shared 5ms/1000-packet budget.
// An empty-span parse first drains retained bytes even if the socket is empty;
// it also preserves plugin delivery on frames without incoming network data.
var refs = network.Body.Instructions.Where(i => i.Operand is MethodReference).Select(i => (MethodReference)i.Operand).ToArray();
MethodReference Ref(string name) => refs.First(m => m.Name == name);
var instance = (FieldReference)network.Body.Instructions.Single(i => i.Operand is FieldReference f && f.Name == "Instance").Operand;
var world = new VariableDefinition(Ref("get_World").ReturnType);
var message = new VariableDefinition(new ArrayType(client.TypeSystem.Byte));
var total = new VariableDefinition(client.TypeSystem.Int32);
network.Body = new MethodBody(network) { InitLocals = true };
network.Body.Variables.Add(world); network.Body.Variables.Add(message); network.Body.Variables.Add(total);
var nil = network.Body.GetILProcessor();
void Emit(OpCode op) => nil.Append(nil.Create(op));
void Call(MethodReference m) => nil.Append(nil.Create(m.HasThis ? OpCodes.Callvirt : OpCodes.Call, m));
void ParseMessage(bool empty) {
    nil.Append(nil.Create(OpCodes.Ldloc, total)); nil.Append(nil.Create(OpCodes.Ldsfld, instance)); nil.Append(nil.Create(OpCodes.Ldloc, world));
    if(empty) Emit(OpCodes.Ldnull); else nil.Append(nil.Create(OpCodes.Ldloc, message));
    Call(Ref("op_Implicit")); Call(Ref("ParsePackets")); Emit(OpCodes.Add); nil.Append(nil.Create(OpCodes.Stloc, total));
}
Call(Ref("get_Game")); Call(Ref("get_UO")); Call(Ref("get_World")); nil.Append(nil.Create(OpCodes.Stloc, world));
ParseMessage(true);
var check = nil.Create(OpCodes.Call, Import("More")); var end = nil.Create(OpCodes.Call, Ref("get_Socket"));
nil.Append(check); nil.Append(nil.Create(OpCodes.Brfalse, end));
Call(Ref("get_Socket")); nil.Append(nil.Create(OpCodes.Ldloca, message)); Call(Ref("TryDequeuePacket")); nil.Append(nil.Create(OpCodes.Brfalse, end));
ParseMessage(false); nil.Append(nil.Create(OpCodes.Br, check));
nil.Append(end); Call(Ref("get_Statistics")); Emit(OpCodes.Dup); Call(Ref("get_TotalPacketsReceived"));
nil.Append(nil.Create(OpCodes.Ldloc, total)); Emit(OpCodes.Add); Call(Ref("set_TotalPacketsReceived")); Emit(OpCodes.Ret);
Time(network, 1, true);
Time(controller.Methods.Single(m => m.Name == "Update"), 0);
var scene = client.GetType("ClassicUO.Game.Scenes.GameScene");
Time(scene.Methods.Single(m => m.Name == "Update"), 2);
Time(scene.Methods.Single(m => m.Name == "Load"), 3);
Time(client.GetType("ClassicUO.Game.Managers.AudioManager").Methods.Single(m => m.Name == "Update"), 4);
Time(scene.Methods.Single(m => m.Name == "FillGameObjectList"), 5);
// Retained bytes must belong to one connection. Backport the prerequisite
// parser reset from upstream ce59683 as each login/relay socket is replaced.
var clear = new MethodDefinition("MementoClearBuffers", MethodAttributes.Assembly | MethodAttributes.HideBySig, client.TypeSystem.Void);
parser.Methods.Add(clear); clear.Body.InitLocals = true;
var locked = new VariableDefinition(client.TypeSystem.Object); var taken = new VariableDefinition(client.TypeSystem.Boolean);
clear.Body.Variables.Add(locked); clear.Body.Variables.Add(taken);
var cil = clear.Body.GetILProcessor();
var enter = (MethodReference)parse.Body.Instructions.Single(i=>i.Operand is MethodReference m && m.DeclaringType.FullName=="System.Threading.Monitor" && m.Name=="Enter").Operand;
var release = (MethodReference)parse.Body.Instructions.Single(i=>i.Operand is MethodReference m && m.DeclaringType.FullName=="System.Threading.Monitor" && m.Name=="Exit").Operand;
var clearBuffer = client.GetType("ClassicUO.Network.CircularBuffer").Methods.Single(m=>m.Name=="Clear");
foreach(var name in new[]{"_buffer","_pluginsBuffer"}) {
    var field = parser.Fields.Single(f=>f.Name==name);
    cil.Append(cil.Create(OpCodes.Ldarg_0)); cil.Append(cil.Create(OpCodes.Ldfld,field)); cil.Append(cil.Create(OpCodes.Stloc,locked));
    cil.Append(cil.Create(OpCodes.Ldc_I4_0)); cil.Append(cil.Create(OpCodes.Stloc,taken));
    var start = cil.Create(OpCodes.Ldloc,locked); cil.Append(start);cil.Append(cil.Create(OpCodes.Ldloca,taken));cil.Append(cil.Create(OpCodes.Call,enter));
    cil.Append(cil.Create(OpCodes.Ldarg_0));cil.Append(cil.Create(OpCodes.Ldfld,field));cil.Append(cil.Create(OpCodes.Callvirt,clearBuffer));
    var afterLock = cil.Create(OpCodes.Nop);cil.Append(cil.Create(OpCodes.Leave,afterLock));
    var cleanup = cil.Create(OpCodes.Ldloc,taken);var done = cil.Create(OpCodes.Endfinally);cil.Append(cleanup);
    cil.Append(cil.Create(OpCodes.Brfalse,done));cil.Append(cil.Create(OpCodes.Ldloc,locked));cil.Append(cil.Create(OpCodes.Call,release));cil.Append(done);cil.Append(afterLock);
    clear.Body.ExceptionHandlers.Add(new ExceptionHandler(ExceptionHandlerType.Finally){TryStart=start,TryEnd=cleanup,HandlerStart=cleanup,HandlerEnd=afterLock});
}
cil.Append(cil.Create(OpCodes.Ret));
foreach(var method in client.GetType("ClassicUO.Network.LoginHandshake").Methods.Where(m=>m.Name is "Connect" or "AfterRelayConnect")) {
    Widen(method);var mil=method.Body.GetILProcessor();
    var replace=method.Body.Instructions.Single(i=>i.Operand is MethodReference m && m.Name=="set_Socket");
    var load=mil.Create(OpCodes.Ldsfld,instance);mil.InsertAfter(replace,load);mil.InsertAfter(load,mil.Create(OpCodes.Callvirt,clear));
}
client.Write(args[2], new WriterParameters { DeterministicMvid = true, Timestamp = 0 });
Console.WriteLine("FRAME_PATCH_CREATED " + Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[2]))).ToLowerInvariant());
