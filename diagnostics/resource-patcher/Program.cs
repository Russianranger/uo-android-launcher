using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Security.Cryptography;

if (args.Length != 3) throw new ArgumentException("verified-base.dll Memento.FrameBudget.dll output.dll");
string Hash(string file) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(file))).ToLowerInvariant();
using var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(args[0]))!);
resolver.AddSearchDirectory(Path.GetDirectoryName(typeof(object).Assembly.Location)!);
var constants = new ConstantMetadataResolver(resolver);
using var module = ModuleDefinition.ReadModule(args[0], new ReaderParameters { AssemblyResolver = resolver, MetadataResolver = constants });
constants.Record(module);
if (!ResourceContract.Bases.TryGetValue(module.Name, out var hashes) || !hashes.Contains(Hash(args[0])))
    throw new Exception("Only the verified TazUO 5.2 diagnostic bases are supported");
using var helper = ModuleDefinition.ReadModule(args[1]);
if (helper.Assembly.Name.Name != "Memento.FrameBudget" || helper.Assembly.Name.Version != new Version(1, 0, 0, 0)) throw new Exception("Unexpected helper identity");
var type = helper.GetType("Memento.ResourceTrace");
string[] abi = { "System.Int64 Memento.ResourceTrace::Begin(System.Int32)", "System.Void Memento.ResourceTrace::End(System.Int32,System.Int64)", "System.Void Memento.ResourceTrace::EnterLock(System.Object,System.Boolean&,System.Int32)" };
if (!abi.All(a => type.Methods.Any(m => m.FullName == a && !m.HasThis))) throw new Exception("Unexpected resource timing ABI");
var chunkType = helper.GetType("Memento.ChunkTrace");
string[] chunkAbi = { "System.Int64 Memento.ChunkTrace::Begin(System.Int32,System.Int32,System.Int32,System.Int32,System.Boolean)",
    "System.Void Memento.ChunkTrace::End(System.Int64)", "System.Void Memento.ChunkTrace::SetWorldMap(System.Int64,System.Int32)",
    "System.Int64 Memento.ChunkTrace::BeginPart(System.Int32)", "System.Void Memento.ChunkTrace::EndPart(System.Int32,System.Int64)" };
if (chunkType == null || !chunkAbi.All(a => chunkType.Methods.Any(m => m.FullName == a && !m.HasThis))) throw new Exception("Unexpected chunk timing ABI");
var reference = module.AssemblyReferences.FirstOrDefault(a => a.FullName == helper.Assembly.Name.FullName);
if (reference == null) { reference = AssemblyNameReference.Parse(helper.Assembly.Name.FullName); module.AssemblyReferences.Add(reference); }
var scope = new TypeReference("Memento", "ResourceTrace", module, reference);
var begin = new MethodReference("Begin", module.TypeSystem.Int64, scope); begin.Parameters.Add(new ParameterDefinition(module.TypeSystem.Int32));
var end = new MethodReference("End", module.TypeSystem.Void, scope); end.Parameters.Add(new ParameterDefinition(module.TypeSystem.Int32)); end.Parameters.Add(new ParameterDefinition(module.TypeSystem.Int64));
var enter = new MethodReference("EnterLock", module.TypeSystem.Void, scope); enter.Parameters.Add(new ParameterDefinition(module.TypeSystem.Object)); enter.Parameters.Add(new ParameterDefinition(new ByReferenceType(module.TypeSystem.Boolean))); enter.Parameters.Add(new ParameterDefinition(module.TypeSystem.Int32));
var chunkScope = new TypeReference("Memento", "ChunkTrace", module, reference);
MethodReference ChunkMethod(string name, TypeReference result, params TypeReference[] parameters) {
    var method = new MethodReference(name, result, chunkScope);
    foreach (var parameter in parameters) method.Parameters.Add(new ParameterDefinition(parameter));
    return method;
}
var chunkBegin = ChunkMethod("Begin", module.TypeSystem.Int64, module.TypeSystem.Int32, module.TypeSystem.Int32, module.TypeSystem.Int32, module.TypeSystem.Int32, module.TypeSystem.Boolean);
var chunkEnd = ChunkMethod("End", module.TypeSystem.Void, module.TypeSystem.Int64);
var worldMap = ChunkMethod("SetWorldMap", module.TypeSystem.Void, module.TypeSystem.Int64, module.TypeSystem.Int32);
var partBegin = ChunkMethod("BeginPart", module.TypeSystem.Int64, module.TypeSystem.Int32);
var partEnd = ChunkMethod("EndPart", module.TypeSystem.Void, module.TypeSystem.Int32, module.TypeSystem.Int64);
var targets = module.GetTypes().SelectMany(t => t.Methods).Where(m => ResourceContract.Operation(m) >= 0 || ResourceContract.ChunkPart(m) >= 0).ToArray();
if (targets.Length != ResourceContract.Expected(module.Name)) throw new Exception("Unexpected resource boundary set");
if (targets.Count(m => ResourceContract.Operation(m) >= 0) != ResourceContract.ExpectedResource(module.Name) ||
    targets.Count(m => ResourceContract.ChunkPart(m) >= 0) != ResourceContract.ExpectedParts(module.Name)) throw new Exception("Unexpected focused boundary set");
var branches = typeof(OpCodes).GetFields().Where(f => f.FieldType == typeof(OpCode)).Select(f => (OpCode)f.GetValue(null)!).ToDictionary(op => op.Name);
int locks = 0;
foreach (var method in targets)
{
    if (!method.HasBody || method.IsConstructor || method.HasGenericParameters || method.ReturnType.IsByReference || method.DeclaringType.IsValueType || method.IsSynchronized)
        throw new Exception("Unsupported resource method shape: " + method.FullName);
    int operation = ResourceContract.Operation(method), part = ResourceContract.ChunkPart(method);
    bool chunk = ResourceContract.IsChunk(method);
    if (operation >= 0 && part >= 0) throw new Exception("Overlapping diagnostic boundaries");
    var body = method.Body; var il = body.GetILProcessor();
    foreach (var instruction in body.Instructions) if (instruction.OpCode.OperandType == OperandType.ShortInlineBrTarget) instruction.OpCode = branches[instruction.OpCode.Name[..^2]];
    int lockOperation = ResourceContract.LockOperation(operation);
    if (lockOperation >= 0)
    {
        var calls = body.Instructions.Where(i => i.OpCode == OpCodes.Call && i.Operand is MethodReference m && m.FullName == "System.Void System.Threading.Monitor::Enter(System.Object,System.Boolean&)").ToArray();
        if (calls.Length != (operation == 17 ? 3 : 1)) throw new Exception("Unexpected lock boundary count");
        foreach (var call in calls) {
            if (body.Instructions.Any(i => i.Operand == call || i.Operand is Instruction[] destinations && destinations.Contains(call)))
                throw new Exception("A lock call is a direct branch target; explicit remapping is required");
            il.InsertBefore(call, il.Create(OpCodes.Ldc_I4, lockOperation)); call.Operand = enter; locks++;
        }
    }
    var first = body.Instructions[0]; var token = new VariableDefinition(module.TypeSystem.Int64); body.Variables.Add(token); body.InitLocals = true;
    VariableDefinition chunkToken = null;
    if (chunk) { chunkToken = new VariableDefinition(module.TypeSystem.Int64); body.Variables.Add(chunkToken); }
    VariableDefinition result = null;
    if (method.ReturnType.FullName != "System.Void") { result = new VariableDefinition(method.ReturnType); body.Variables.Add(result); }
    il.InsertBefore(first, il.Create(OpCodes.Ldc_I4, operation >= 0 ? operation : part));
    il.InsertBefore(first, il.Create(OpCodes.Call, operation >= 0 ? begin : partBegin)); il.InsertBefore(first, il.Create(OpCodes.Stloc, token));
    var outerStart = first;
    if (chunk)
    {
        var getMap = body.Instructions.Single(i => i.Operand is MethodReference m && m.FullName == "ClassicUO.Game.Map.Map ClassicUO.Game.World::get_Map()");
        var storeMap = getMap.Next;
        if (storeMap.OpCode != OpCodes.Stloc_0 || body.Variables[0].VariableType.FullName != "ClassicUO.Game.Map.Map") throw new Exception("Unexpected original chunk map acquisition");
        var mapType = module.GetType("ClassicUO.Game.Map.Map");
        var mapIndex = mapType.Fields.Single(f => f.Name == "Index" && f.FieldType.FullName == "System.Int32");
        var x = method.DeclaringType.Fields.Single(f => f.Name == "X" && f.FieldType.FullName == "System.Int32");
        var y = method.DeclaringType.Fields.Single(f => f.Name == "Y" && f.FieldType.FullName == "System.Int32");
        outerStart = il.Create(OpCodes.Ldarg, method.Parameters[0]);
        foreach (var instruction in new[] { outerStart, il.Create(OpCodes.Ldc_I4, -1), il.Create(OpCodes.Ldarg_0), il.Create(OpCodes.Ldfld, x),
            il.Create(OpCodes.Ldarg_0), il.Create(OpCodes.Ldfld, y), il.Create(OpCodes.Ldarg, method.Parameters[1]),
            il.Create(OpCodes.Call, chunkBegin), il.Create(OpCodes.Stloc, chunkToken) }) il.InsertBefore(first, instruction);
        // Observe the Map local produced by the original getter, without moving
        // or duplicating that getter and without adding a null-map exception.
        var hasMap = il.Create(OpCodes.Ldloc, body.Variables[0]); var setMap = il.Create(OpCodes.Call, worldMap);
        var observeAt = storeMap.Next;
        foreach (var instruction in new[] { il.Create(OpCodes.Ldloc, chunkToken), il.Create(OpCodes.Ldloc, body.Variables[0]),
            il.Create(OpCodes.Brtrue, hasMap), il.Create(OpCodes.Ldc_I4, -1), il.Create(OpCodes.Br, setMap), hasMap,
            il.Create(OpCodes.Ldfld, mapIndex), setMap }) il.InsertBefore(observeAt, instruction);
    }
    var done = il.Create(OpCodes.Nop);
    foreach (var ret in body.Instructions.Where(i => i.OpCode == OpCodes.Ret).ToArray())
    {
        if (result == null) { ret.OpCode = OpCodes.Leave; ret.Operand = done; }
        else { ret.OpCode = OpCodes.Stloc; ret.Operand = result; il.InsertAfter(ret, il.Create(OpCodes.Leave, done)); }
    }
    var cleanup = chunk ? il.Create(OpCodes.Ldloc, chunkToken) : il.Create(OpCodes.Ldc_I4, operation >= 0 ? operation : part);
    foreach (var handler in body.ExceptionHandlers) { if (handler.TryEnd == null) handler.TryEnd = cleanup; if (handler.HandlerEnd == null) handler.HandlerEnd = cleanup; }
    il.Append(cleanup);
    if (chunk) { il.Append(il.Create(OpCodes.Call, chunkEnd)); il.Append(il.Create(OpCodes.Ldc_I4, operation)); }
    il.Append(il.Create(OpCodes.Ldloc, token)); il.Append(il.Create(OpCodes.Call, operation >= 0 ? end : partEnd)); il.Append(il.Create(OpCodes.Endfinally)); il.Append(done);
    if (result != null) il.Append(il.Create(OpCodes.Ldloc, result)); il.Append(il.Create(OpCodes.Ret));
    body.ExceptionHandlers.Add(new ExceptionHandler(ExceptionHandlerType.Finally) { TryStart = outerStart, TryEnd = cleanup, HandlerStart = cleanup, HandlerEnd = done });
}
Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[2]))!); module.Write(args[2], new WriterParameters { Timestamp = 0 });
Console.WriteLine("RESOURCE_PATCH_CREATED library=" + module.Name + " methods=" + targets.Length + " resource_methods=" + ResourceContract.ExpectedResource(module.Name) + " chunk_parts=" + ResourceContract.ExpectedParts(module.Name) + " locks=" + locks + " sha256=" + Hash(args[2]));
