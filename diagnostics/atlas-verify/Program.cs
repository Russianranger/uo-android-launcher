using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Security.Cryptography;

if (args.Length != 2) throw new ArgumentException("original.dll patched.dll");
using var original = ModuleDefinition.ReadModule(args[0]);
using var patched = ModuleDefinition.ReadModule(args[1]);
string originalHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[0]))).ToLowerInvariant();
bool renderer = originalHash == AtlasBoundaryContract.RendererHash;
if (!renderer && originalHash != AtlasBoundaryContract.FnaHash) throw new Exception("Unrecognized original assembly");
void Require(bool condition, string detail) { if (!condition) throw new Exception(detail); }
string Attributes(IEnumerable<CustomAttribute> values) => string.Join(";", values.Select(a =>
    a.Constructor.FullName + ":" + Convert.ToHexString(a.GetBlob())));
string Marshal(MarshalInfo value) => value == null ? "" : value.GetType().FullName + ":" +
    string.Join(";", value.GetType().GetProperties().Where(p => p.CanRead && p.GetIndexParameters().Length == 0)
        .OrderBy(p => p.Name).Select(p => p.Name + "=" + p.GetValue(value)));
string Constant(object value) => value == null ? "null" : value.GetType().FullName + ":" +
    (value is byte[] bytes ? Convert.ToHexString(bytes) : value is double d ? BitConverter.DoubleToInt64Bits(d).ToString() :
    value is float f ? BitConverter.SingleToInt32Bits(f).ToString() : value.ToString());
string Parameter(ParameterDefinition p) => p.Name + ":" + p.ParameterType.FullName + ":" + p.Attributes + ":" +
    p.HasConstant + ":" + Constant(p.Constant) + ":" + Marshal(p.MarshalInfo) + ":" + Attributes(p.CustomAttributes);
string Return(MethodReturnType p) => p.ReturnType.FullName + ":" + p.Attributes + ":" + p.HasConstant + ":" +
    Constant(p.Constant) + ":" + Marshal(p.MarshalInfo) + ":" + Attributes(p.CustomAttributes);
string Import(PInvokeInfo value) => value == null ? "" : value.Attributes + ":" + value.EntryPoint + ":" + value.Module.Name;
string Canonical(MethodDefinition method, int skip = 0) {
    if (!method.HasBody) return "";
    var body = method.Body;
    var instructions = body.Instructions.Skip(skip).ToArray();
    string Index(Instruction i) => i == null ? "end" : Array.IndexOf(instructions, i).ToString();
    string Operand(object o) => o switch {
        Instruction i => Index(i), Instruction[] a => string.Join(",", a.Select(Index)),
        VariableDefinition v => "local:" + v.Index, ParameterDefinition p => "arg:" + p.Index,
        MemberReference m => m.FullName, null => "", _ => o.ToString()
    };
    return string.Join("\n", instructions.Select(i => i.OpCode.Name + " " + Operand(i.Operand))) +
        "\ninit:" + body.InitLocals + "\nlocals:" + string.Join(",", body.Variables.Select(v => v.VariableType.FullName)) +
        "\nhandlers:" + string.Join(";", body.ExceptionHandlers.Select(h => h.HandlerType + ":" + h.CatchType?.FullName + ":" +
            Index(h.TryStart) + ":" + Index(h.TryEnd) + ":" + Index(h.HandlerStart) + ":" + Index(h.HandlerEnd) + ":" + Index(h.FilterStart)));
}
bool FlushCall(Instruction i) => i.OpCode == OpCodes.Call && i.Operand is MethodReference m &&
    m.FullName == "System.Void Memento.AtlasUploads::Flush()";
Require(original.Assembly.Name.FullName == patched.Assembly.Name.FullName && original.Name == patched.Name &&
    original.Mvid == patched.Mvid && original.Architecture == patched.Architecture && original.Attributes == patched.Attributes &&
    original.Kind == patched.Kind && original.RuntimeVersion == patched.RuntimeVersion && original.EntryPoint?.FullName == patched.EntryPoint?.FullName,
    "assembly identity or module metadata changed");
Require(Attributes(original.Assembly.CustomAttributes) == Attributes(patched.Assembly.CustomAttributes) &&
    Attributes(original.CustomAttributes) == Attributes(patched.CustomAttributes), "assembly annotations changed");
Require(original.ModuleReferences.Select(m => m.Name).SequenceEqual(patched.ModuleReferences.Select(m => m.Name)), "native library references changed");
var originals = original.AssemblyReferences.Select(a => a.FullName).ToArray();
var references = patched.AssemblyReferences.Select(a => a.FullName).ToArray();
Require(originals.All(references.Contains) && references.Length == originals.Length + 1 &&
    references.Except(originals).Single().StartsWith("Memento.AtlasUploads, Version=1.0.0.0,"), "unexpected dependency change");
Require(original.Resources.Count == patched.Resources.Count, "resource count changed");
foreach (var resource in original.Resources) {
    var other = patched.Resources.Single(r => r.Name == resource.Name);
    Require(resource.Attributes == other.Attributes && resource.ResourceType == other.ResourceType, "resource metadata changed");
    if (resource is EmbeddedResource embedded)
        Require(embedded.GetResourceData().SequenceEqual(((EmbeddedResource)other).GetResourceData()), "resource bytes changed");
    else if (resource is AssemblyLinkedResource linked)
        Require(linked.Assembly.FullName == ((AssemblyLinkedResource)other).Assembly.FullName, "resource assembly changed");
    else if (resource is LinkedResource file)
        Require(file.File == ((LinkedResource)other).File && file.Hash.SequenceEqual(((LinkedResource)other).Hash), "linked resource changed");
}
var originalTypes = original.GetTypes().ToArray();
var patchedTypes = patched.GetTypes().ToDictionary(t => t.FullName);
Require(originalTypes.Length == patchedTypes.Count, "type count changed");
var originalMethods = originalTypes.SelectMany(t => t.Methods).ToDictionary(m => m.FullName);
var patchedMethods = patchedTypes.Values.SelectMany(t => t.Methods).ToDictionary(m => m.FullName);
var nativeTargets = renderer ? Array.Empty<MethodDefinition>() : AtlasBoundaryContract.NativeMethods(original);
Require(renderer || nativeTargets.Length == 26, "unexpected native target count");
var nativeNames = nativeTargets.Select(m => m.FullName).ToHashSet();
string disposal = renderer ? "" : AtlasBoundaryContract.TextureDispose(original).FullName;
string atlas = renderer ? original.GetType("ClassicUO.Renderer.TextureAtlas").Methods.Single(m => m.Name == "AddSprite").FullName : "";
int unchanged = 0, changed = 0, constants = 0;
foreach (var type in originalTypes) {
    Require(patchedTypes.TryGetValue(type.FullName, out var other), "missing type: " + type.FullName);
    Require(type.Attributes == other.Attributes && type.BaseType?.FullName == other.BaseType?.FullName &&
        type.ClassSize == other.ClassSize && type.PackingSize == other.PackingSize && Attributes(type.CustomAttributes) == Attributes(other.CustomAttributes) &&
        type.Interfaces.Select(i => i.InterfaceType.FullName).SequenceEqual(other.Interfaces.Select(i => i.InterfaceType.FullName)), "type metadata changed: " + type.FullName);
    Require(type.Fields.Count == other.Fields.Count && type.Properties.Count == other.Properties.Count && type.Events.Count == other.Events.Count,
        "type member counts changed: " + type.FullName);
    foreach (var field in type.Fields) {
        var target = other.Fields.Single(f => f.FullName == field.FullName);
        Require(field.Attributes == target.Attributes && field.Offset == target.Offset && field.HasConstant == target.HasConstant &&
            Constant(field.Constant) == Constant(target.Constant) && field.InitialValue.SequenceEqual(target.InitialValue) &&
            Marshal(field.MarshalInfo) == Marshal(target.MarshalInfo) && Attributes(field.CustomAttributes) == Attributes(target.CustomAttributes), "field changed: " + field.FullName);
        if (field.HasConstant) constants++;
    }
    foreach (var property in type.Properties) {
        var target = other.Properties.Single(p => p.FullName == property.FullName);
        Require(property.Attributes == target.Attributes && property.HasConstant == target.HasConstant && Constant(property.Constant) == Constant(target.Constant) &&
            property.GetMethod?.FullName == target.GetMethod?.FullName && property.SetMethod?.FullName == target.SetMethod?.FullName &&
            property.OtherMethods.Select(m => m.FullName).SequenceEqual(target.OtherMethods.Select(m => m.FullName)) &&
            Attributes(property.CustomAttributes) == Attributes(target.CustomAttributes), "property changed: " + property.FullName);
        if (property.HasConstant) constants++;
    }
    foreach (var ev in type.Events) {
        var target = other.Events.Single(e => e.FullName == ev.FullName);
        Require(ev.Attributes == target.Attributes && ev.AddMethod?.FullName == target.AddMethod?.FullName && ev.RemoveMethod?.FullName == target.RemoveMethod?.FullName &&
            ev.InvokeMethod?.FullName == target.InvokeMethod?.FullName && ev.OtherMethods.Select(m => m.FullName).SequenceEqual(target.OtherMethods.Select(m => m.FullName)) &&
            Attributes(ev.CustomAttributes) == Attributes(target.CustomAttributes), "event changed: " + ev.FullName);
    }
    foreach (var method in type.Methods) {
        Require(patchedMethods.TryGetValue(method.FullName, out var target), "missing method: " + method.FullName);
        Require(method.CallingConvention == target.CallingConvention && method.SemanticsAttributes == target.SemanticsAttributes &&
            Return(method.MethodReturnType) == Return(target.MethodReturnType) && method.Parameters.Select(Parameter).SequenceEqual(target.Parameters.Select(Parameter)) &&
            Attributes(method.CustomAttributes) == Attributes(target.CustomAttributes) &&
            method.Overrides.Select(m => m.FullName).SequenceEqual(target.Overrides.Select(m => m.FullName)), "method ABI changed: " + method.FullName);
        constants += method.Parameters.Count(p => p.HasConstant) + (method.MethodReturnType.HasConstant ? 1 : 0);
        if (nativeNames.Contains(method.FullName)) {
            Require(target.Attributes == (method.Attributes & ~MethodAttributes.PInvokeImpl) && !target.HasPInvokeInfo &&
                target.ImplAttributes == ((method.ImplAttributes & ~(MethodImplAttributes.CodeTypeMask | MethodImplAttributes.ManagedMask |
                MethodImplAttributes.InternalCall | MethodImplAttributes.ForwardRef)) | MethodImplAttributes.IL | MethodImplAttributes.Managed), "managed wrapper flags changed: " + method.FullName);
            var clone = other.Methods.Single(m => m.Name == AtlasBoundaryContract.CloneName(method) &&
                m.Parameters.Select(p => p.ParameterType.FullName).SequenceEqual(method.Parameters.Select(p => p.ParameterType.FullName)));
            Require(clone.Attributes == ((method.Attributes & ~MethodAttributes.MemberAccessMask) | MethodAttributes.Private) &&
                clone.ImplAttributes == method.ImplAttributes && clone.IsPInvokeImpl && !clone.HasBody && Import(clone.PInvokeInfo) == Import(method.PInvokeInfo) &&
                Return(clone.MethodReturnType) == Return(method.MethodReturnType) && clone.Parameters.Select(Parameter).SequenceEqual(method.Parameters.Select(Parameter)) &&
                Attributes(clone.CustomAttributes) == Attributes(method.CustomAttributes), "native import contract changed: " + method.FullName);
            var body = target.Body;
            Require(!body.HasVariables && !body.HasExceptionHandlers && body.Instructions.Count == method.Parameters.Count + 3 &&
                FlushCall(body.Instructions[0]) && body.Instructions[^2].OpCode == OpCodes.Call &&
                ((MethodReference)body.Instructions[^2].Operand).FullName == clone.FullName && body.Instructions[^1].OpCode == OpCodes.Ret,
                "unexpected native forwarding body: " + method.FullName);
            for (int index = 0; index < method.Parameters.Count; index++)
                Require(body.Instructions[index + 1].OpCode == OpCodes.Ldarg && body.Instructions[index + 1].Operand is ParameterDefinition parameter &&
                    parameter.Index == index, "native argument forwarding changed: " + method.FullName);
            changed++;
        } else {
            Require(method.Attributes == target.Attributes && method.ImplAttributes == target.ImplAttributes &&
                Import(method.PInvokeInfo) == Import(target.PInvokeInfo), "method attributes/import changed: " + method.FullName);
            if (method.FullName == disposal) {
                Require(FlushCall(target.Body.Instructions[0]) && Canonical(method) == Canonical(target, 1), "managed texture lifetime path changed");
                changed++;
            } else if (method.FullName == atlas) {
                var instructions = target.Body.Instructions.Where(i => i.Operand is MethodReference m && m.FullName ==
                    "System.Void Memento.AtlasUploads::Upload(Microsoft.Xna.Framework.Graphics.Texture2D,System.Int32,System.Nullable`1<Microsoft.Xna.Framework.Rectangle>,System.IntPtr,System.Int32)").ToArray();
                Require(instructions.Length == 1 && instructions[0].OpCode == OpCodes.Call, "unexpected renderer upload hook");
                var source = method.Body.Instructions.Single(i => i.Operand is MethodReference m && m.Name == "SetDataPointerEXT");
                var hook = instructions[0]; var opcode = hook.OpCode; var operand = hook.Operand;
                hook.OpCode = source.OpCode; hook.Operand = source.Operand;
                Require(Canonical(method) == Canonical(target), "renderer changed outside original upload call");
                hook.OpCode = opcode; hook.Operand = operand;
                changed++;
            } else {
                Require(Canonical(method) == Canonical(target), "unrelated method changed: " + method.FullName);
                unchanged++;
            }
        }
    }
}
var added = patchedMethods.Values.Where(m => !originalMethods.ContainsKey(m.FullName)).ToArray();
Require(added.Length == nativeTargets.Length && added.All(m => m.DeclaringType.FullName == AtlasBoundaryContract.NativeType &&
    m.Name.StartsWith(AtlasBoundaryContract.NativePrefix) && m.IsPrivate && m.IsPInvokeImpl), "unexpected added members");
Require(changed == (renderer ? 1 : 27), "unexpected modified member count");
Console.WriteLine($"ATLAS_{(renderer ? "RENDERER" : "FNA")}_PATCH_VERIFIED unchanged_methods={unchanged} changed_methods={changed} native_clones={added.Length} preserved_constants={constants} original_resources_preserved=true");
