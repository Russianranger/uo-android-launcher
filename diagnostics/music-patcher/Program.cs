using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Security.Cryptography;
if (args.Length < 2) throw new ArgumentException("source.dll output.dll");
string hash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[0]))).ToLowerInvariant();
if (hash != "1dd53cf0eea718aefeda33fba105c9797b138188be22562b47548c310524100d")
    throw new InvalidOperationException("Unrecognized Assets binary");
var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(args[0])));
resolver.AddSearchDirectory(Path.GetDirectoryName(typeof(object).Assembly.Location));
var constants = new ConstantMetadataResolver(resolver);
using var client = ModuleDefinition.ReadModule(args[0], new ReaderParameters { AssemblyResolver = resolver, MetadataResolver = constants });
constants.Record(client);
var sounds = client.GetType("ClassicUO.Assets.SoundsLoader");
var lookup = sounds.Methods.Single(m => m.Name == "GetTrueFileName");
var scan = lookup.Body.Instructions.Single(i => i.Operand is MethodReference m &&
    m.DeclaringType.FullName == "System.IO.Directory" && m.Name == "GetFiles");
var directory = (MethodReference)scan.Operand;
if (directory.Parameters.Count != 3 || directory.ReturnType.FullName != "System.String[]")
    throw new InvalidOperationException("Unexpected directory enumeration signature");
var cache = new FieldDefinition("_mementoMusicFiles", FieldAttributes.Private, directory.ReturnType);
sounds.Fields.Add(cache);
// One enumeration per Load; retain all original matching and result selection.
var cached = new MethodDefinition("MementoMusicFiles", MethodAttributes.Private | MethodAttributes.Static, directory.ReturnType);
foreach (var parameter in directory.Parameters) cached.Parameters.Add(new ParameterDefinition(parameter.ParameterType));
cached.Parameters.Add(new ParameterDefinition(sounds));sounds.Methods.Add(cached);
var il = cached.Body.GetILProcessor();var done = il.Create(OpCodes.Ret);
il.Append(il.Create(OpCodes.Ldarg_3));il.Append(il.Create(OpCodes.Ldfld, cache));
il.Append(il.Create(OpCodes.Dup));il.Append(il.Create(OpCodes.Brtrue, done));il.Append(il.Create(OpCodes.Pop));
il.Append(il.Create(OpCodes.Ldarg_3));
il.Append(il.Create(OpCodes.Ldarg_0));il.Append(il.Create(OpCodes.Ldarg_1));il.Append(il.Create(OpCodes.Ldarg_2));
il.Append(il.Create(OpCodes.Call, directory));il.Append(il.Create(OpCodes.Stfld, cache));
il.Append(il.Create(OpCodes.Ldarg_3));il.Append(il.Create(OpCodes.Ldfld, cache));il.Append(done);
lookup.Body.GetILProcessor().InsertBefore(scan, Instruction.Create(OpCodes.Ldarg_0));scan.Operand = cached;
foreach (string name in new[] { "Load", "ClearResources" }) {
    var method = sounds.Methods.Single(m => m.Name == name);
    var processor = method.Body.GetILProcessor();var first = method.Body.Instructions[0];
    processor.InsertBefore(first, processor.Create(OpCodes.Ldarg_0));
    processor.InsertBefore(first, processor.Create(OpCodes.Ldnull));
    processor.InsertBefore(first, processor.Create(OpCodes.Stfld, cache));
}
var branches = typeof(OpCodes).GetFields().Where(f => f.FieldType == typeof(OpCode))
    .Select(f => (OpCode)f.GetValue(null)!).ToDictionary(op => op.Name);
foreach (var method in new[] { lookup, sounds.Methods.Single(m => m.Name == "Load"), sounds.Methods.Single(m => m.Name == "ClearResources") })
    foreach (var ins in method.Body.Instructions)
        if (ins.OpCode.OperandType == OperandType.ShortInlineBrTarget) ins.OpCode = branches[ins.OpCode.Name[..^2]];
client.Write(args[1], new WriterParameters { DeterministicMvid = true, Timestamp = 0 });
Console.WriteLine("MUSIC_PATCH_CREATED " + Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[1]))).ToLowerInvariant());
