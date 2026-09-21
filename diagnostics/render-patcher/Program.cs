using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Security.Cryptography;

// Offline patch generation only. Never run a patcher or Cecil inside Wine.
if (args.Length < 3) throw new ArgumentException("source.dll helper.dll output.dll [--fixture]");
string inputHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[0]))).ToLowerInvariant();
if (inputHash != "b04066be1b1b475ca00e6982a980e2dd11b93abede00c79c68bde566bdcf947e" && !args.Contains("--fixture"))
    throw new InvalidOperationException("Unrecognized client binary");
var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(args[0])));
resolver.AddSearchDirectory(Path.GetDirectoryName(typeof(object).Assembly.Location));
var constants = new ConstantMetadataResolver(resolver);
using var client = ModuleDefinition.ReadModule(args[0], new ReaderParameters { AssemblyResolver = resolver, MetadataResolver = constants });
constants.Record(client);
using var helper = ModuleDefinition.ReadModule(args[1]);
var trace = helper.Types.Single(t => t.FullName == "Memento.RenderTrace");
MethodReference Import(string name) => client.ImportReference(trace.Methods.Single(m => m.Name == name));
var scene = client.Types.Single(t => t.FullName == "ClassicUO.Game.Scenes.GameScene");
var fill = scene.Methods.Single(m => m.Name == "FillGameObjectList");
var draw = scene.Methods.Single(m => m.Name == "DrawRenderList");
var body = draw.Body;
var il = body.GetILProcessor();
var enumerator = body.Variables.Single(v => v.VariableType.FullName.Contains("List`1/Enumerator"));
var scope = new VariableDefinition(client.ImportReference(helper.Types.Single(t => t.FullName == "Memento.ReadScope")));
var result = new VariableDefinition(client.TypeSystem.Int32);
var exception = new VariableDefinition(new TypeReference("System", "InvalidOperationException", client, client.TypeSystem.CoreLibrary));
body.Variables.Add(scope); body.Variables.Add(result); body.Variables.Add(exception);
body.InitLocals = true;
// Widen relative branches before adding an outer catch/finally.
var branches = typeof(OpCodes).GetFields().Where(f => f.FieldType == typeof(OpCode))
    .Select(f => (OpCode)f.GetValue(null)!).ToDictionary(op => op.Name);
foreach (var ins in body.Instructions)
    if (ins.OpCode.OperandType == OperandType.ShortInlineBrTarget)
        ins.OpCode = branches[ins.OpCode.Name[..^2]];
var originalStart = body.Instructions[0];
foreach (var ins in new[] { il.Create(OpCodes.Ldarg_0), il.Create(OpCodes.Ldarg_2),
    il.Create(OpCodes.Call, Import("Begin")), il.Create(OpCodes.Stloc, scope) })
    il.InsertBefore(originalStart, ins);
var finalReturn = il.Create(OpCodes.Ldloc, result);
foreach (var ret in body.Instructions.Where(i => i.OpCode == OpCodes.Ret).ToArray())
{
    ret.OpCode = OpCodes.Stloc; ret.Operand = result;
    il.InsertAfter(ret, il.Create(OpCodes.Leave, finalReturn));
}
var catchStart = il.Create(OpCodes.Stloc, exception);
il.Append(catchStart);
il.Append(il.Create(OpCodes.Ldloc, scope));
il.Append(il.Create(OpCodes.Ldloc, enumerator));
il.Append(il.Create(OpCodes.Box, enumerator.VariableType));
il.Append(il.Create(OpCodes.Ldloc, exception));
il.Append(il.Create(OpCodes.Call, Import("Failed")));
il.Append(il.Create(OpCodes.Rethrow));
var finallyStart = il.Create(OpCodes.Ldloc, scope);
il.Append(finallyStart);
il.Append(il.Create(OpCodes.Call, Import("End")));
il.Append(il.Create(OpCodes.Endfinally));
il.Append(finalReturn); il.Append(il.Create(OpCodes.Ret));
body.ExceptionHandlers.Add(new ExceptionHandler(ExceptionHandlerType.Catch) {
    CatchType = exception.VariableType, TryStart = originalStart, TryEnd = catchStart,
    HandlerStart = catchStart, HandlerEnd = finallyStart
});
body.ExceptionHandlers.Add(new ExceptionHandler(ExceptionHandlerType.Finally) {
    TryStart = originalStart, TryEnd = finallyStart, HandlerStart = finallyStart, HandlerEnd = finalReturn
});
var fil = fill.Body.GetILProcessor();
var first = fill.Body.Instructions[0];
fil.InsertBefore(first, fil.Create(OpCodes.Ldarg_0));
fil.InsertBefore(first, fil.Create(OpCodes.Call, Import("Fill")));
// The original PDB offsets no longer describe this method. Do not emit a
// CodeView record pointing at it. The original file is retained for restore.
client.Write(args[2], new WriterParameters { DeterministicMvid = true, Timestamp = 0 });
Console.WriteLine("RENDER_PATCH_CREATED " + Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[2]))).ToLowerInvariant());
