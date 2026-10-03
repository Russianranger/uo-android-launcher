using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Security.Cryptography;
using Memento;

if (args.Length != 3) throw new ArgumentException("atlas-FNA.dll Memento.FrameBudget.dll diagnostic-FNA.dll");
const string AtlasFna = "d295aab6eac90d404f4b8a584785545688c72e63a855c7bba492947814f6e61b";
string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
if (Hash(args[0]) != AtlasFna) throw new Exception("Only the verified 0.2.14 atlas FNA is supported");
using var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(args[0]))!);
resolver.AddSearchDirectory(Path.GetDirectoryName(typeof(object).Assembly.Location)!);
var constants = new ConstantMetadataResolver(resolver);
using var module = ModuleDefinition.ReadModule(args[0], new ReaderParameters { AssemblyResolver = resolver, MetadataResolver = constants });
constants.Record(module);
using var helper = ModuleDefinition.ReadModule(args[1]);
if (helper.Assembly.Name.Name != "Memento.FrameBudget" || helper.Assembly.Name.Version != new Version(1, 0, 0, 0))
    throw new Exception("Unexpected diagnostic helper identity");
var type = helper.GetType("Memento.ColdTrace");
if (type.Methods.Single(m => m.Name == "BeginNative").FullName != "System.Int64 Memento.ColdTrace::BeginNative(System.Int32)" ||
    type.Methods.Single(m => m.Name == "EndNative").FullName != "System.Void Memento.ColdTrace::EndNative(System.Int32,System.Int64)")
    throw new Exception("Unexpected timing ABI");
var reference = AssemblyNameReference.Parse(helper.Assembly.Name.FullName); module.AssemblyReferences.Add(reference);
var scope = new TypeReference("Memento", "ColdTrace", module, reference);
var begin = new MethodReference("BeginNative", module.TypeSystem.Int64, scope);
begin.Parameters.Add(new ParameterDefinition(module.TypeSystem.Int32));
var end = new MethodReference("EndNative", module.TypeSystem.Void, scope);
end.Parameters.Add(new ParameterDefinition(module.TypeSystem.Int32)); end.Parameters.Add(new ParameterDefinition(module.TypeSystem.Int64));
var fna = module.GetType("Microsoft.Xna.Framework.Graphics.FNA3D");
var methods = fna.Methods.Where(m => GraphicsOperations.Names.Contains(m.Name)).ToArray();
if (methods.Length != 43 || !methods.Select(m => m.Name).ToHashSet().SetEquals(GraphicsOperations.Names))
    throw new Exception("Unexpected graphics boundary set");
foreach (var method in methods)
{
    int operation = Array.IndexOf(GraphicsOperations.Names, method.Name);
    MethodReference native;
    MethodReference flush = null;
    if (method.HasBody)
    {
        // Keep the atlas flush at exactly its existing position. Timing starts
        // after it so a flush cannot be double-counted as the following draw.
        var instructions = method.Body.Instructions;
        if (instructions.Count != method.Parameters.Count + 3 || instructions[0].OpCode != OpCodes.Call ||
            instructions[0].Operand is not MethodReference f || f.FullName != "System.Void Memento.AtlasUploads::Flush()" ||
            instructions[^2].Operand is not MethodReference n || n.Name != "MementoNative_" + method.Name)
            throw new Exception("Unexpected existing atlas forwarding body");
        flush = f; native = n;
    }
    else
    {
        if (!method.IsPInvokeImpl || !method.IsStatic || method.HasGenericParameters || method.HasOverrides || method.HasSecurityDeclarations)
            throw new Exception("Unexpected native boundary");
        var clone = new MethodDefinition("MementoDiagnosticNative_" + method.Name,
            (method.Attributes & ~MethodAttributes.MemberAccessMask) | MethodAttributes.Private, method.ReturnType) {
            ImplAttributes = method.ImplAttributes,
            PInvokeInfo = new PInvokeInfo(method.PInvokeInfo.Attributes, method.PInvokeInfo.EntryPoint, method.PInvokeInfo.Module)
        };
        clone.MethodReturnType.Attributes = method.MethodReturnType.Attributes;
        if (method.MethodReturnType.HasMarshalInfo) clone.MethodReturnType.MarshalInfo = method.MethodReturnType.MarshalInfo;
        if (method.MethodReturnType.HasConstant) clone.MethodReturnType.Constant = method.MethodReturnType.Constant;
        foreach (var a in method.MethodReturnType.CustomAttributes) clone.MethodReturnType.CustomAttributes.Add(a);
        foreach (var a in method.CustomAttributes) clone.CustomAttributes.Add(a);
        foreach (var p in method.Parameters) {
            var copy = new ParameterDefinition(p.Name, p.Attributes, p.ParameterType);
            if (p.HasConstant) copy.Constant = p.Constant;
            if (p.HasMarshalInfo) copy.MarshalInfo = p.MarshalInfo;
            foreach (var a in p.CustomAttributes) copy.CustomAttributes.Add(a);
            clone.Parameters.Add(copy);
        }
        fna.Methods.Add(clone); native = clone;
        method.PInvokeInfo = null; method.Attributes &= ~MethodAttributes.PInvokeImpl;
        method.ImplAttributes = (method.ImplAttributes & ~(MethodImplAttributes.CodeTypeMask | MethodImplAttributes.ManagedMask |
            MethodImplAttributes.InternalCall | MethodImplAttributes.ForwardRef)) | MethodImplAttributes.IL | MethodImplAttributes.Managed;
    }
    method.Body = new MethodBody(method) { InitLocals = true };
    var began = new VariableDefinition(module.TypeSystem.Int64); method.Body.Variables.Add(began);
    VariableDefinition result = null;
    if (method.ReturnType.FullName != "System.Void") { result = new VariableDefinition(method.ReturnType); method.Body.Variables.Add(result); }
    var il = method.Body.GetILProcessor();
    if (flush != null) il.Append(il.Create(OpCodes.Call, flush));
    il.Append(il.Create(OpCodes.Ldc_I4, operation)); il.Append(il.Create(OpCodes.Call, begin)); il.Append(il.Create(OpCodes.Stloc, began));
    var first = il.Create(OpCodes.Nop); il.Append(first);
    foreach (var p in method.Parameters) il.Append(il.Create(OpCodes.Ldarg, p));
    il.Append(il.Create(OpCodes.Call, native));
    if (result != null) il.Append(il.Create(OpCodes.Stloc, result));
    var done = il.Create(OpCodes.Nop); il.Append(il.Create(OpCodes.Leave, done));
    var final = il.Create(OpCodes.Ldc_I4, operation); il.Append(final); il.Append(il.Create(OpCodes.Ldloc, began));
    il.Append(il.Create(OpCodes.Call, end)); il.Append(il.Create(OpCodes.Endfinally)); il.Append(done);
    if (result != null) il.Append(il.Create(OpCodes.Ldloc, result));
    il.Append(il.Create(OpCodes.Ret));
    method.Body.ExceptionHandlers.Add(new ExceptionHandler(ExceptionHandlerType.Finally) { TryStart = first, TryEnd = final, HandlerStart = final, HandlerEnd = done });
}
Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[2]))!); module.Write(args[2]);
Console.WriteLine("DIAGNOSTIC_FNA boundaries=" + methods.Length + " sha256=" + Hash(args[2]));
