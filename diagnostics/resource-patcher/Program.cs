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
if (!abi.All(a => type.Methods.Any(m => m.FullName == a))) throw new Exception("Unexpected resource timing ABI");
var reference = module.AssemblyReferences.FirstOrDefault(a => a.FullName == helper.Assembly.Name.FullName);
if (reference == null) { reference = AssemblyNameReference.Parse(helper.Assembly.Name.FullName); module.AssemblyReferences.Add(reference); }
var scope = new TypeReference("Memento", "ResourceTrace", module, reference);
var begin = new MethodReference("Begin", module.TypeSystem.Int64, scope); begin.Parameters.Add(new ParameterDefinition(module.TypeSystem.Int32));
var end = new MethodReference("End", module.TypeSystem.Void, scope); end.Parameters.Add(new ParameterDefinition(module.TypeSystem.Int32)); end.Parameters.Add(new ParameterDefinition(module.TypeSystem.Int64));
var enter = new MethodReference("EnterLock", module.TypeSystem.Void, scope); enter.Parameters.Add(new ParameterDefinition(module.TypeSystem.Object)); enter.Parameters.Add(new ParameterDefinition(new ByReferenceType(module.TypeSystem.Boolean))); enter.Parameters.Add(new ParameterDefinition(module.TypeSystem.Int32));
var targets = module.GetTypes().SelectMany(t => t.Methods).Where(m => ResourceContract.Operation(m) >= 0).ToArray();
if (targets.Length != ResourceContract.Expected(module.Name)) throw new Exception("Unexpected resource boundary set");
var branches = typeof(OpCodes).GetFields().Where(f => f.FieldType == typeof(OpCode)).Select(f => (OpCode)f.GetValue(null)!).ToDictionary(op => op.Name);
int locks = 0;
foreach (var method in targets)
{
    if (!method.HasBody || method.IsConstructor || method.HasGenericParameters || method.ReturnType.IsByReference || method.DeclaringType.IsValueType || method.IsSynchronized)
        throw new Exception("Unsupported resource method shape: " + method.FullName);
    int operation = ResourceContract.Operation(method); var body = method.Body; var il = body.GetILProcessor();
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
    VariableDefinition result = null;
    if (method.ReturnType.FullName != "System.Void") { result = new VariableDefinition(method.ReturnType); body.Variables.Add(result); }
    il.InsertBefore(first, il.Create(OpCodes.Ldc_I4, operation)); il.InsertBefore(first, il.Create(OpCodes.Call, begin)); il.InsertBefore(first, il.Create(OpCodes.Stloc, token));
    var done = il.Create(OpCodes.Nop);
    foreach (var ret in body.Instructions.Where(i => i.OpCode == OpCodes.Ret).ToArray())
    {
        if (result == null) { ret.OpCode = OpCodes.Leave; ret.Operand = done; }
        else { ret.OpCode = OpCodes.Stloc; ret.Operand = result; il.InsertAfter(ret, il.Create(OpCodes.Leave, done)); }
    }
    var cleanup = il.Create(OpCodes.Ldc_I4, operation);
    foreach (var handler in body.ExceptionHandlers) { if (handler.TryEnd == null) handler.TryEnd = cleanup; if (handler.HandlerEnd == null) handler.HandlerEnd = cleanup; }
    il.Append(cleanup); il.Append(il.Create(OpCodes.Ldloc, token)); il.Append(il.Create(OpCodes.Call, end)); il.Append(il.Create(OpCodes.Endfinally)); il.Append(done);
    if (result != null) il.Append(il.Create(OpCodes.Ldloc, result)); il.Append(il.Create(OpCodes.Ret));
    body.ExceptionHandlers.Add(new ExceptionHandler(ExceptionHandlerType.Finally) { TryStart = first, TryEnd = cleanup, HandlerStart = cleanup, HandlerEnd = done });
}
Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[2]))!); module.Write(args[2], new WriterParameters { Timestamp = 0 });
Console.WriteLine("RESOURCE_PATCH_CREATED library=" + module.Name + " methods=" + targets.Length + " locks=" + locks + " sha256=" + Hash(args[2]));
