using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Security.Cryptography;

if (args.Length != 3)
    throw new ArgumentException("original.dll helper.dll output.dll");
string originalHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[0]))).ToLowerInvariant();
bool patchRenderer = originalHash == AtlasBoundaryContract.RendererHash;
if (!patchRenderer && originalHash != AtlasBoundaryContract.FnaHash)
    throw new InvalidOperationException("Unrecognized original assembly: " + Path.GetFileName(args[0]));
using var helper = ModuleDefinition.ReadModule(args[1]);
if (helper.Assembly.Name.Name != "Memento.AtlasUploads" || helper.Assembly.Name.Version != new Version(1, 0, 0, 0))
    throw new Exception("Unexpected atlas helper identity");
var helperType = helper.GetType(AtlasBoundaryContract.HelperType) ?? throw new Exception("Missing atlas helper");
var upload = helperType.Methods.Single(m => m.Name == "Upload");
if (!upload.IsPublic || !upload.IsStatic || upload.ReturnType.FullName != "System.Void" ||
    !upload.Parameters.Select(p => p.ParameterType.FullName).SequenceEqual(new[] {
        "Microsoft.Xna.Framework.Graphics.Texture2D", "System.Int32",
        "System.Nullable`1<Microsoft.Xna.Framework.Rectangle>", "System.IntPtr", "System.Int32" }))
    throw new Exception("Unexpected atlas Upload ABI");
var flush = helperType.Methods.Single(m => m.Name == "Flush");
if (!flush.IsPublic || !flush.IsStatic || flush.ReturnType.FullName != "System.Void" || flush.Parameters.Count != 0)
    throw new Exception("Unexpected atlas Flush ABI");

// Construct signatures from each original module's existing type references.
// Importing net10 helper parameter scopes into net8 FNA must not add a second
// System.Runtime dependency or rewrite the imported assemblies' public ABI.
MethodReference HelperMethod(ModuleDefinition module, string name) =>
    new(name, module.TypeSystem.Void, module.ImportReference(helperType)) { HasThis = false };
var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(args[0])));
resolver.AddSearchDirectory(Path.GetDirectoryName(typeof(object).Assembly.Location));
var constants = new ConstantMetadataResolver(resolver);
using var module = ModuleDefinition.ReadModule(args[0], new ReaderParameters { AssemblyResolver = resolver, MetadataResolver = constants });
constants.Record(module);
if (patchRenderer) {
var renderer = module;
var addSprite = renderer.GetType("ClassicUO.Renderer.TextureAtlas").Methods.Single(m => m.Name == "AddSprite");
var calls = addSprite.Body.Instructions.Where(i => i.Operand is MethodReference m &&
    m.DeclaringType.FullName == "Microsoft.Xna.Framework.Graphics.Texture2D" && m.Name == "SetDataPointerEXT").ToArray();
if (calls.Length != 1 || calls[0].OpCode != OpCodes.Callvirt) throw new Exception("Unexpected atlas upload call");
var originalUpload = (MethodReference)calls[0].Operand;
if (!originalUpload.HasThis || originalUpload.ReturnType.FullName != "System.Void" ||
    originalUpload.Parameters.Count != 4) throw new Exception("Unexpected original upload ABI");
var uploadReference = HelperMethod(renderer, "Upload");
uploadReference.Parameters.Add(new ParameterDefinition(originalUpload.DeclaringType));
foreach (var p in originalUpload.Parameters) uploadReference.Parameters.Add(new ParameterDefinition(p.ParameterType));
calls[0].OpCode = OpCodes.Call;
calls[0].Operand = uploadReference;
} else {
var fna = module;
var nativeMethods = AtlasBoundaryContract.NativeMethods(fna);
if (nativeMethods.Length != 26 || nativeMethods.Any(m => !m.IsPInvokeImpl || !m.IsStatic || m.HasBody ||
    m.ReturnType.FullName != "System.Void" || m.HasGenericParameters || m.HasOverrides || m.HasSecurityDeclarations) ||
    !nativeMethods.Select(m => m.Name).ToHashSet().SetEquals(AtlasBoundaryContract.NativeNames))
    throw new Exception("Unexpected FNA native boundary set");
var flushReference = HelperMethod(fna, "Flush");
foreach (var method in nativeMethods) {
    // The new private extern retains the exact platform import contract. The
    // existing method/token/signature remains the managed call target.
    var native = new MethodDefinition(AtlasBoundaryContract.CloneName(method),
        (method.Attributes & ~MethodAttributes.MemberAccessMask) | MethodAttributes.Private, method.ReturnType) {
        ImplAttributes = method.ImplAttributes,
        PInvokeInfo = new PInvokeInfo(method.PInvokeInfo.Attributes, method.PInvokeInfo.EntryPoint, method.PInvokeInfo.Module)
    };
    CopyReturn(method.MethodReturnType, native.MethodReturnType);
    foreach (var attribute in method.CustomAttributes) native.CustomAttributes.Add(attribute);
    foreach (var parameter in method.Parameters) {
        var copy = new ParameterDefinition(parameter.Name, parameter.Attributes, parameter.ParameterType);
        if (parameter.HasConstant) copy.Constant = parameter.Constant;
        if (parameter.HasMarshalInfo) copy.MarshalInfo = parameter.MarshalInfo;
        foreach (var attribute in parameter.CustomAttributes) copy.CustomAttributes.Add(attribute);
        native.Parameters.Add(copy);
    }
    method.DeclaringType.Methods.Add(native);
    method.PInvokeInfo = null;
    method.Attributes &= ~MethodAttributes.PInvokeImpl;
    method.ImplAttributes = (method.ImplAttributes & ~(MethodImplAttributes.CodeTypeMask | MethodImplAttributes.ManagedMask |
        MethodImplAttributes.InternalCall | MethodImplAttributes.ForwardRef)) | MethodImplAttributes.IL | MethodImplAttributes.Managed;
    method.Body = new MethodBody(method);
    var il = method.Body.GetILProcessor();
    il.Append(il.Create(OpCodes.Call, flushReference));
    foreach (var parameter in method.Parameters) il.Append(il.Create(OpCodes.Ldarg, parameter));
    il.Append(il.Create(OpCodes.Call, native));
    il.Append(il.Create(OpCodes.Ret));
}
// Texture.Dispose clears its native handle before it reaches AddDisposeTexture.
// Flush while that handle still exists, before retaining the complete original
// lifetime path. Native disposal is also guarded for callers bypassing Texture.
var textureDispose = AtlasBoundaryContract.TextureDispose(fna);
if (!textureDispose.HasBody || !textureDispose.IsVirtual || textureDispose.ReturnType.FullName != "System.Void")
    throw new Exception("Unexpected managed texture disposal boundary");
textureDispose.Body.GetILProcessor().InsertBefore(textureDispose.Body.Instructions[0],
    Instruction.Create(OpCodes.Call, flushReference));
}
void CopyReturn(MethodReturnType source, MethodReturnType target) {
    target.Attributes = source.Attributes;
    if (source.HasConstant) target.Constant = source.Constant;
    if (source.HasMarshalInfo) target.MarshalInfo = source.MarshalInfo;
    foreach (var attribute in source.CustomAttributes) target.CustomAttributes.Add(attribute);
}
Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[2]))!);
module.Write(args[2]);
Console.WriteLine(Path.GetFileName(args[2]) + " " +
    Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[2]))).ToLowerInvariant());
