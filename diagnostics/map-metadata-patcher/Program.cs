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
if (!MapMetadataContract.Bases.TryGetValue(module.Name, out var bases) || !bases.Contains(Hash(args[0])))
    throw new Exception("Only exact qualified TazUO 5.2 map metadata bases are supported");
using var helper = ModuleDefinition.ReadModule(args[1]);
if (helper.Assembly.Name.Name != "Memento.FrameBudget" || helper.Assembly.Name.Version != new Version(1, 0, 0, 0)) throw new Exception("Unexpected helper identity");
var helperType = helper.GetType("Memento.ChunkMetadata");
string[] abi = { "System.Int64 Memento.ChunkMetadata::Begin()", "System.Void Memento.ChunkMetadata::End(System.Int64)",
    "System.Boolean Memento.ChunkMetadata::TryGet(System.Object,System.Int64&)", "System.Void Memento.ChunkMetadata::Store(System.Object,System.Int64)" };
if (helperType == null || !abi.All(a => helperType.Methods.Any(m => m.FullName == a && !m.HasThis))) throw new Exception("Unexpected metadata cache ABI");
var reference = module.AssemblyReferences.FirstOrDefault(a => a.FullName == helper.Assembly.Name.FullName);
if (reference == null) { reference = AssemblyNameReference.Parse(helper.Assembly.Name.FullName); module.AssemblyReferences.Add(reference); }
var scope = new TypeReference("Memento", "ChunkMetadata", module, reference);
MethodReference Hook(string name, TypeReference result, params TypeReference[] parameters) {
    var method = new MethodReference(name, result, scope);
    foreach (var parameter in parameters) method.Parameters.Add(new ParameterDefinition(parameter));
    return method;
}
var begin = Hook("Begin", module.TypeSystem.Int64);
var end = Hook("End", module.TypeSystem.Void, module.TypeSystem.Int64);
var get = Hook("TryGet", module.TypeSystem.Boolean, module.TypeSystem.Object, new ByReferenceType(module.TypeSystem.Int64));
var store = Hook("Store", module.TypeSystem.Void, module.TypeSystem.Object, module.TypeSystem.Int64);
var branches = typeof(OpCodes).GetFields().Where(f => f.FieldType == typeof(OpCode)).Select(f => (OpCode)f.GetValue(null)!).ToDictionary(op => op.Name);
var target = module.GetTypes().SelectMany(t => t.Methods).Single(MapMetadataContract.IsTarget);
if (!target.HasBody || target.ReturnType.FullName != "System.Void" || target.IsSynchronized) throw new Exception("Unsupported map metadata boundary");
foreach (var instruction in target.Body.Instructions)
    if (instruction.OpCode.OperandType == OperandType.ShortInlineBrTarget) instruction.OpCode = branches[instruction.OpCode.Name[..^2]];
int lengthCalls = 0;
if (target.FullName == MapMetadataContract.Chunk)
{
    var body = target.Body; var il = body.GetILProcessor(); var first = body.Instructions[0];
    var token = new VariableDefinition(module.TypeSystem.Int64); body.Variables.Add(token); body.InitLocals = true;
    il.InsertBefore(first, il.Create(OpCodes.Call, begin)); il.InsertBefore(first, il.Create(OpCodes.Stloc, token));
    var done = il.Create(OpCodes.Nop);
    foreach (var ret in body.Instructions.Where(i => i.OpCode == OpCodes.Ret).ToArray()) { ret.OpCode = OpCodes.Leave; ret.Operand = done; }
    var cleanup = il.Create(OpCodes.Ldloc, token);
    foreach (var handler in body.ExceptionHandlers) { if (handler.TryEnd == null) handler.TryEnd = cleanup; if (handler.HandlerEnd == null) handler.HandlerEnd = cleanup; }
    il.Append(cleanup); il.Append(il.Create(OpCodes.Call, end)); il.Append(il.Create(OpCodes.Endfinally)); il.Append(done); il.Append(il.Create(OpCodes.Ret));
    body.ExceptionHandlers.Add(new ExceptionHandler(ExceptionHandlerType.Finally) { TryStart = first, TryEnd = cleanup, HandlerStart = cleanup, HandlerEnd = done });
}
else
{
    var calls = target.Body.Instructions.Where(i => i.Operand is MethodReference m && m.FullName == MapMetadataContract.Length).ToArray();
    if (calls.Length != 3 || calls.Any(i => i.OpCode != OpCodes.Callvirt)) throw new Exception("Map gate length call sites changed");
    var original = (MethodReference)calls[0].Operand;
    var wrapper = new MethodDefinition("MementoMapChunkLength", MethodAttributes.Private | MethodAttributes.Static, module.TypeSystem.Int64);
    wrapper.Parameters.Add(new ParameterDefinition("reader", ParameterAttributes.None, original.DeclaringType));
    target.DeclaringType.Methods.Add(wrapper);
    var body = wrapper.Body; body.InitLocals = true;
    var value = new VariableDefinition(module.TypeSystem.Int64); body.Variables.Add(value);
    var il = body.GetILProcessor(); var miss = il.Create(OpCodes.Ldarg_0); var done = il.Create(OpCodes.Ldloc, value);
    il.Append(il.Create(OpCodes.Ldarg_0)); il.Append(il.Create(OpCodes.Ldloca, value)); il.Append(il.Create(OpCodes.Call, get));
    il.Append(il.Create(OpCodes.Brfalse, miss)); il.Append(done); il.Append(il.Create(OpCodes.Ret));
    il.Append(miss); il.Append(il.Create(OpCodes.Callvirt, original)); il.Append(il.Create(OpCodes.Stloc, value));
    il.Append(il.Create(OpCodes.Ldarg_0)); il.Append(il.Create(OpCodes.Ldloc, value)); il.Append(il.Create(OpCodes.Call, store));
    il.Append(il.Create(OpCodes.Ldloc, value)); il.Append(il.Create(OpCodes.Ret));
    foreach (var call in calls) { call.OpCode = OpCodes.Call; call.Operand = wrapper; lengthCalls++; }
}
Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[2]))!); module.Write(args[2], new WriterParameters { Timestamp = 0 });
Console.WriteLine("MAP_METADATA_PATCH_CREATED library=" + module.Name + " target=" + target.FullName + " length_forwards=" + lengthCalls + " sha256=" + Hash(args[2]));
