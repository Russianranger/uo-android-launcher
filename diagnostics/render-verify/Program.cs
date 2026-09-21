using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Security.Cryptography;
using var original = ModuleDefinition.ReadModule(args[0]);
using var updated = ModuleDefinition.ReadModule(args[1]);
string Canonical(MethodDefinition method)
{
    if (!method.HasBody) return "";
    var b = method.Body;
    string Index(Instruction i) => i == null ? "end" : b.Instructions.IndexOf(i).ToString();
    string Operand(object o) => o switch {
        Instruction i => Index(i), Instruction[] a => string.Join(",", a.Select(Index)),
        VariableDefinition v => "local:"+v.Index, ParameterDefinition p => "arg:"+p.Index,
        MemberReference m => m.FullName, null => "", _ => o.ToString()
    };
    return string.Join("\n", b.Instructions.Select(i => i.OpCode.Name + " " + Operand(i.Operand))) +
        "\nlocals:" + string.Join(",", b.Variables.Select(v => v.VariableType.FullName)) +
        "\nhandlers:" + string.Join(";", b.ExceptionHandlers.Select(h => h.HandlerType + ":" + h.CatchType?.FullName + ":" +
            Index(h.TryStart) + ":" + Index(h.TryEnd) + ":" + Index(h.HandlerStart) + ":" + Index(h.HandlerEnd) + ":" + Index(h.FilterStart)));
}
var methods = updated.GetTypes().SelectMany(t => t.Methods).ToDictionary(m => m.FullName);
var changed = new List<string>(); int same = 0, constants = 0;
if (original.Assembly.Name.FullName != updated.Assembly.Name.FullName) throw new Exception("assembly identity changed");
foreach (var t in original.GetTypes())
{
    var target = updated.GetType(t.FullName);
    if (target == null || t.Attributes != target.Attributes) throw new Exception("type changed: " + t.FullName);
    foreach (var f in t.Fields)
    {
        var other = target.Fields.Single(x => x.FullName == f.FullName);
        if (f.Attributes != other.Attributes || f.HasConstant != other.HasConstant ||
            !Equals(f.Constant, other.Constant) || !f.InitialValue.SequenceEqual(other.InitialValue))
            throw new Exception("field changed: " + f.FullName);
        if (f.HasConstant) constants++;
    }
    foreach (var m in t.Methods)
    {
        var n = methods[m.FullName];
        if (m.Attributes != n.Attributes || m.ImplAttributes != n.ImplAttributes) throw new Exception("method attributes changed");
        foreach (var p in m.Parameters)
        {
            var q = n.Parameters[p.Index];
            if (p.Attributes != q.Attributes || p.HasConstant != q.HasConstant || !Equals(p.Constant, q.Constant))
                throw new Exception("parameter constant changed: " + m.FullName);
            if (p.HasConstant) constants++;
        }
        if (Canonical(m) != Canonical(n)) changed.Add(m.DeclaringType.FullName + "::" + m.Name); else same++;
    }
}
bool music = args.Contains("--music");
bool frame = args.Contains("--frame");
var expected = music ? new[] { "ClassicUO.Assets.SoundsLoader::Load", "ClassicUO.Assets.SoundsLoader::GetTrueFileName", "ClassicUO.Assets.SoundsLoader::ClearResources" } : frame ? new[] {
    "ClassicUO.GameController::ProcessNetworkPackets", "ClassicUO.GameController::Update",
    "ClassicUO.Network.PacketHandlers.PacketParser::ParsePackets", "ClassicUO.Game.Scenes.GameScene::Update",
    "ClassicUO.Game.Scenes.GameScene::Load", "ClassicUO.Game.Scenes.GameScene::FillGameObjectList", "ClassicUO.Game.Managers.AudioManager::Update",
    "ClassicUO.Network.LoginHandshake::Connect", "ClassicUO.Network.LoginHandshake::AfterRelayConnect"
} : new[] {"ClassicUO.Game.Scenes.GameScene::DrawRenderList", "ClassicUO.Game.Scenes.GameScene::FillGameObjectList"};
if (frame) {
    if (original.Architecture != updated.Architecture || original.Attributes != updated.Attributes ||
        original.GetTypes().Count() != updated.GetTypes().Count() ||
        original.GetTypes().Sum(t=>t.Methods.Count)+1 != updated.GetTypes().Sum(t=>t.Methods.Count) ||
        original.GetTypes().Sum(t=>t.Fields.Count) != updated.GetTypes().Sum(t=>t.Fields.Count)) throw new Exception("unexpected frame metadata change");
    var added = updated.AssemblyReferences.Select(a=>a.FullName).Except(original.AssemblyReferences.Select(a=>a.FullName)).ToArray();
    if (added.Length != 1 || !added[0].StartsWith("Memento.FrameBudget, Version=1.0.0.0,")) throw new Exception("unexpected frame dependency change");
    if (original.AssemblyReferences.Any(a=>!updated.AssemblyReferences.Any(b=>b.FullName==a.FullName))) throw new Exception("removed dependency");
    var newMethods=updated.GetTypes().SelectMany(t=>t.Methods).Select(m=>m.FullName).Except(original.GetTypes().SelectMany(t=>t.Methods).Select(m=>m.FullName)).ToArray();
    if(newMethods.Length!=1 || newMethods[0]!="System.Void ClassicUO.Network.PacketHandlers.PacketParser::MementoClearBuffers()") throw new Exception("unexpected frame member");
}
if (music) {
    if (original.Architecture != updated.Architecture || original.Attributes != updated.Attributes ||
        original.GetTypes().Count() != updated.GetTypes().Count() ||
        !original.AssemblyReferences.Select(a=>a.FullName).SequenceEqual(updated.AssemblyReferences.Select(a=>a.FullName)))
        throw new Exception("unexpected assembly metadata change");
    var addedMethods = updated.GetTypes().SelectMany(t=>t.Methods).Select(m=>m.FullName)
        .Except(original.GetTypes().SelectMany(t=>t.Methods).Select(m=>m.FullName)).ToArray();
    var addedFields = updated.GetTypes().SelectMany(t=>t.Fields).Select(f=>f.FullName)
        .Except(original.GetTypes().SelectMany(t=>t.Fields).Select(f=>f.FullName)).ToArray();
    if (addedMethods.Length != 1 || !addedMethods[0].Contains("SoundsLoader::MementoMusicFiles(") ||
        addedFields.Length != 1 || !addedFields[0].EndsWith("SoundsLoader::_mementoMusicFiles"))
        throw new Exception("unexpected added members");
}
if (!changed.Order().SequenceEqual(expected.Order())) throw new Exception("unexpected method changes: " + string.Join(",",changed));
foreach (var resource in original.Resources.OfType<EmbeddedResource>())
{
    var other = updated.Resources.OfType<EmbeddedResource>().Single(r => r.Name == resource.Name);
    if (!resource.GetResourceData().SequenceEqual(other.GetResourceData())) throw new Exception("resource changed");
}
Console.WriteLine($"{(music ? "MUSIC" : frame ? "FRAME" : "RENDER")}_PATCH_VERIFIED unchanged_methods={same} changed_methods={changed.Count} preserved_constants={constants} original_resources_preserved=true");
