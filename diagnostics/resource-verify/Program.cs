using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Security.Cryptography;


if (args.Length != 2) throw new ArgumentException("original.dll patched.dll");
using var original = ModuleDefinition.ReadModule(args[0]);
using var patched = ModuleDefinition.ReadModule(args[1]);
string originalHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[0]))).ToLowerInvariant();

if (!ResourceContract.Bases.TryGetValue(original.Name, out var hashes) || !hashes.Contains(originalHash)) throw new Exception("Unrecognized resource base");
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
Require(original.Assembly.Name.FullName == patched.Assembly.Name.FullName && original.Name == patched.Name &&
    original.Mvid == patched.Mvid && original.Architecture == patched.Architecture && original.Attributes == patched.Attributes &&
    original.Kind == patched.Kind && original.RuntimeVersion == patched.RuntimeVersion && original.EntryPoint?.FullName == patched.EntryPoint?.FullName,
    "assembly identity or module metadata changed");
Require(Attributes(original.Assembly.CustomAttributes) == Attributes(patched.Assembly.CustomAttributes) &&
    Attributes(original.CustomAttributes) == Attributes(patched.CustomAttributes), "assembly annotations changed");
Require(original.ModuleReferences.Select(m => m.Name).SequenceEqual(patched.ModuleReferences.Select(m => m.Name)), "native library references changed");
var originals = original.AssemblyReferences.Select(a => a.FullName).ToArray();
var references = patched.AssemblyReferences.Select(a => a.FullName).ToArray();
Require(originals.All(references.Contains) && references.Except(originals).All(r => r.StartsWith("Memento.FrameBudget, Version=1.0.0.0,")) &&
    references.Length == originals.Length + (originals.Any(r => r.StartsWith("Memento.FrameBudget,")) ? 0 : 1), "unexpected dependency change");
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
int unchanged = 0, changed = 0, constants = 0, locks = 0;
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
        Require(method.Attributes == target.Attributes && method.ImplAttributes == target.ImplAttributes &&
            Import(method.PInvokeInfo) == Import(target.PInvokeInfo), "method attributes/import changed: " + method.FullName);
        int operation = ResourceContract.Operation(method);
        if (operation < 0) { Require(Canonical(method) == Canonical(target), "unrelated method changed: " + method.FullName); unchanged++; continue; }
        var body = target.Body; var instructions = body.Instructions; int cursor = 0;
        bool returns = method.ReturnType.FullName != "System.Void";
        int oldLocals = method.Body.Variables.Count;
        Require(body.InitLocals && body.Variables.Count == oldLocals + (returns ? 2 : 1) &&
            body.Variables.Take(oldLocals).Select(v => v.VariableType.FullName).SequenceEqual(method.Body.Variables.Select(v => v.VariableType.FullName)) &&
            body.Variables[oldLocals].VariableType.FullName == "System.Int64" && (!returns || body.Variables[oldLocals+1].VariableType.FullName == method.ReturnType.FullName), "Unexpected wrapper locals");
        bool Id(int id) { var i=instructions[cursor++]; return i.OpCode==OpCodes.Ldc_I4 && (int)i.Operand==id; }
        bool Call(string name) { var i=instructions[cursor++]; return i.OpCode==OpCodes.Call && i.Operand is MethodReference m && m.FullName==name; }
        bool Local(OpCode op,int n) { var i=instructions[cursor++];return i.OpCode==op && i.Operand is VariableDefinition v && v.Index==n; }
        Require(Id(operation) && Call("System.Int64 Memento.ResourceTrace::Begin(System.Int32)") && Local(OpCodes.Stloc,oldLocals), "Unexpected prefix");
        var map = new Dictionary<Instruction,Instruction>();
        var returnsRedirected = new List<Instruction>();
        var originalsInstructions = method.Body.Instructions.ToArray();
        foreach (var before in originalsInstructions) {
            bool monitor = ResourceContract.LockOperation(operation)>=0 && before.OpCode==OpCodes.Call && before.Operand is MethodReference m && m.FullName=="System.Void System.Threading.Monitor::Enter(System.Object,System.Boolean&)";
            if (monitor) { Require(Id(ResourceContract.LockOperation(operation)), "Lock operation ID changed"); locks++; }
            var after=instructions[cursor++]; map[before]=after;
            if (before.OpCode==OpCodes.Ret) {
                if (returns) { Require(after.OpCode==OpCodes.Stloc && after.Operand is VariableDefinition v && v.Index==oldLocals+1, "Return value not preserved"); after=instructions[cursor++]; }
                Require(after.OpCode==OpCodes.Leave,"Return did not execute cleanup"); returnsRedirected.Add(after);
            } else if (monitor) Require(after.OpCode==OpCodes.Call && after.Operand is MethodReference m2 && m2.FullName=="System.Void Memento.ResourceTrace::EnterLock(System.Object,System.Boolean&,System.Int32)", "Monitor forwarding changed");
            else Require(before.OpCode.Name.Replace(".s","")==after.OpCode.Name.Replace(".s",""), "Original opcode changed: "+before);
        }
        var cleanup=instructions[cursor];
        Require(Id(operation) && Local(OpCodes.Ldloc,oldLocals) && Call("System.Void Memento.ResourceTrace::End(System.Int32,System.Int64)") && instructions[cursor++].OpCode==OpCodes.Endfinally,"Unexpected cleanup");
        var done=instructions[cursor++];Require(done.OpCode==OpCodes.Nop && returnsRedirected.All(i=>i.Operand==done),"Return target changed");
        Require((!returns || Local(OpCodes.Ldloc,oldLocals+1)) && instructions[cursor++].OpCode==OpCodes.Ret && cursor==instructions.Count,"Unexpected tail");
        string Operand(object o,bool fromOriginal) => o switch {
            Instruction i => instructions.IndexOf(fromOriginal ? map[i] : i).ToString(),
            Instruction[] list => string.Join(",",list.Select(i=>instructions.IndexOf(fromOriginal ? map[i] : i))),
            VariableDefinition v => "local:"+v.Index, ParameterDefinition p => "arg:"+p.Index,
            MemberReference m => m.FullName,null=>"",_=>o.ToString()
        };
        foreach (var before in originalsInstructions) {
            if (before.OpCode==OpCodes.Ret) continue;
            if (ResourceContract.LockOperation(operation)>=0 && before.Operand is MethodReference m && m.FullName=="System.Void System.Threading.Monitor::Enter(System.Object,System.Boolean&)") continue;
            Require(Operand(before.Operand,true)==Operand(map[before].Operand,false),"Original operand/branch changed: "+before);
        }
        Require(body.ExceptionHandlers.Count==method.Body.ExceptionHandlers.Count+1,"Exception handler count changed");
        Instruction MapEnd(Instruction i)=>i==null?cleanup:map[i];
        for (int h=0;h<method.Body.ExceptionHandlers.Count;h++) {
            var before=method.Body.ExceptionHandlers[h];var after=body.ExceptionHandlers[h];
            Require(before.HandlerType==after.HandlerType && before.CatchType?.FullName==after.CatchType?.FullName && map[before.TryStart]==after.TryStart &&
                MapEnd(before.TryEnd)==after.TryEnd && map[before.HandlerStart]==after.HandlerStart && MapEnd(before.HandlerEnd)==after.HandlerEnd &&
                (before.FilterStart==null ? after.FilterStart==null : map[before.FilterStart]==after.FilterStart),"Original exception region changed");
        }
        var outer=body.ExceptionHandlers.Last();
        Require(outer.HandlerType==ExceptionHandlerType.Finally && outer.TryStart==map[originalsInstructions[0]] && outer.TryEnd==cleanup && outer.HandlerStart==cleanup && outer.HandlerEnd==done,"Outer diagnostic finally changed");
        changed++;

    }
}
Require(originalMethods.Count==patchedMethods.Count,"Unexpected added methods");
Require(changed==ResourceContract.Expected(original.Name),"Unexpected modified member count");
Console.WriteLine($"RESOURCE_PATCH_VERIFIED library={original.Name} unchanged_methods={unchanged} changed_methods={changed} lock_forwards={locks} preserved_constants={constants} original_resources_preserved=true");
