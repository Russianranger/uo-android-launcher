using System.Diagnostics;
using System.Buffers.Binary;
using System.Globalization;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using Memento;

if (args.Length != 2) throw new ArgumentException("fixture-folder enabled|disabled");
string folder = Path.GetFullPath(args[0]); bool enabled = args[1] == "enabled";
Environment.SetEnvironmentVariable("MEMENTO_COLD_TRACE", enabled ? "1" : "0");
const BindingFlags Instance = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
const BindingFlags StateFields = BindingFlags.Instance | BindingFlags.NonPublic;
const BindingFlags Static = BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public;
void Check(bool ok, string why) { if (!ok) throw new Exception(why); }
var output = new StringWriter(CultureInfo.InvariantCulture); var saved = Console.Error; Console.SetError(output);
try
{
    AssemblyLoadContext.Default.Resolving += (_, name) => { string file = Path.Combine(folder, name.Name + ".dll"); return File.Exists(file) ? AssemblyLoadContext.Default.LoadFromAssemblyPath(file) : null; };
    var io = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(folder, "ClassicUO.IO.dll"));
    // Prepare every actual wrapped vendor body without calling its game/GPU
    // behavior. This catches invalid IL involving byref-like return locals or
    // the original nested exception handlers on both host and Wine/FEX CLR.
    int prepared = 0;
    var boundaries = new Dictionary<string, Dictionary<string, string[]>> {
        ["TazUO.dll"] = new() {
            ["ClassicUO.Game.Map.Chunk"] = new[] { "Load" },
            ["ClassicUO.Game.Scenes.GameScene"] = new[] { "DrawWorldRenderTarget", "DrawRenderList" },
            ["ClassicUO.Game.GameObjects.Item"] = new[] { "Create" },
            ["ClassicUO.Game.GameObjects.Mobile"] = new[] { "Create" } },
        ["ClassicUO.Assets.dll"] = new() {
            ["ClassicUO.Assets.ArtLoader"] = new[] { "GetArt", "LoadLand", "LoadArt" },
            ["ClassicUO.Assets.GumpsLoader"] = new[] { "GetGump" },
            ["ClassicUO.Assets.TexmapsLoader"] = new[] { "GetTexmap" },
            ["ClassicUO.Assets.LightsLoader"] = new[] { "GetLight" },
            ["ClassicUO.Assets.AnimationsLoader"] = new[] { "ReadUOPAnimationFrames", "ReadMULAnimationFrames" },
            ["ClassicUO.Assets.PNGLoader"] = new[] { "LoadArtTexture", "LoadGumpTexture", "GetImageTexture" } },
        ["ClassicUO.IO.dll"] = new() {
            ["ClassicUO.IO.FileReader"] = new[] { "Read", "ReadAt" },
            ["ClassicUO.IO.MMFileReader"] = new[] { "ReadAt" } },
        ["ClassicUO.Renderer.dll"] = new() {
            ["ClassicUO.Renderer.Animations.Animations"] = new[] { "GetAnimationFrames" } },
        ["FNA.dll"] = new() {
            ["Microsoft.Xna.Framework.Graphics.Texture2D"] = new[] { "FromStream" },
            ["Microsoft.Xna.Framework.Graphics.GraphicsDevice"] = new[] { "AddResourceReference", "RemoveResourceReference" } }
    };
    foreach (var library in boundaries) {
        var assembly = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(folder, library.Key));
        foreach (var boundary in library.Value) foreach (var method in assembly.GetType(boundary.Key, true)!.GetMethods(Instance | Static | BindingFlags.DeclaredOnly)
            .Where(m => boundary.Value.Contains(m.Name) && !m.IsGenericMethod)) {
            RuntimeHelpers.PrepareMethod(method.MethodHandle); prepared++;
        }
    }
    Check(prepared == 24, "Not every patched resource body was JIT checked");
    var readerType = io.GetType("ClassicUO.IO.MMFileReader", true)!;
    string temporary = Path.Combine(Path.GetTempPath(), "memento-resource-" + Guid.NewGuid().ToString("N"));
    File.WriteAllBytes(temporary, new byte[] { 10, 20, 30, 40, 50, 60 });
    try
    {
        using var file = File.OpenRead(temporary);
        var reader = readerType.GetConstructors(Instance).Single().Invoke(new object[] { file });
        var readMethod = readerType.GetMethods(Instance).Single(m => m.Name == "Read" && !m.IsGenericMethod && m.GetParameters().Single().ParameterType == typeof(Span<byte>));
        Check(readMethod.DeclaringType!.FullName == "ClassicUO.IO.FileReader", "File read probe did not execute the patched FileReader body");
        var read = readMethod.CreateDelegate<Read>(reader);
        var readAt = readerType.GetMethods(Instance).Single(m => m.Name == "ReadAt" && !m.IsGenericMethod).CreateDelegate<ReadAt>(reader);
        var dispose = readerType.GetMethod("Dispose", Instance)!;
        var position = readerType.GetProperty("Position", Instance)!;
        byte[] data = new byte[3];
        long stage = FrameBudget.Begin(FrameBudget.Draw);
        Check(read(data) == 3 && data.SequenceEqual(new byte[] { 10, 20, 30 }) && (long)position.GetValue(reader)! == 3, "Actual file read return/bytes/position changed");
        readAt(1, data); Check(data.SequenceEqual(new byte[] { 20, 30, 40 }) && (long)position.GetValue(reader)! == 3, "Actual mapped read-at argument/bytes/position changed");
        FrameBudget.End(FrameBudget.Draw, stage);
        dispose.Invoke(reader, null);
        try { read(data); throw new Exception("Disposed read unexpectedly succeeded"); } catch (ObjectDisposedException) { }
        Check((int)(typeof(ResourceTrace).GetField("state", Static)?.GetValue(null)?.GetType().GetField("depth", StateFields)!.GetValue(typeof(ResourceTrace).GetField("state", Static)!.GetValue(null)) ?? 0) == 0, "Original file exception leaked a scope");
    }
    finally { File.Delete(temporary); }
    // Startup loaders are not enclosed in the world-rendering/network scopes.
    // Their numeric fields use the original primitive methods, followed by one
    // small Span read for each fixed-width name. Exercise that actual root shape
    // instead of hiding frequent reads beneath an artificial resource parent.
    const int StartupRows = 65536, NameBytes = 20, RecordBytes = 8 + 2 + NameBytes;
    byte[] records = new byte[StartupRows * RecordBytes];
    for (int i = 0; i < StartupRows; i++)
    {
        var row = records.AsSpan(i * RecordBytes, RecordBytes);
        BinaryPrimitives.WriteUInt64LittleEndian(row, 0xFEDCBA9800000000UL + (uint)i);
        BinaryPrimitives.WriteUInt16LittleEndian(row[8..], (ushort)i);
        row[10] = (byte)('a' + i % 26);
    }
    File.WriteAllBytes(temporary, records);
    double startupReadsMs;
    try
    {
        using var file = File.OpenRead(temporary);
        var reader = readerType.GetConstructors(Instance).Single().Invoke(new object[] { file });
        var read = readerType.GetMethods(Instance).Single(m => m.Name == "Read" && !m.IsGenericMethod).CreateDelegate<Read>(reader);
        var readFlags = readerType.GetMethod("ReadUInt64", Instance)!.CreateDelegate<Func<ulong>>(reader);
        var readGraphic = readerType.GetMethod("ReadUInt16", Instance)!.CreateDelegate<Func<ushort>>(reader);
        var resourceState = typeof(ResourceTrace).GetField("state", Static)!.GetValue(null);
        long before = enabled ? (long)resourceState!.GetType().GetField("frameRoots", StateFields)!.GetValue(resourceState)! : 0;
        Check(!enabled || (int)resourceState!.GetType().GetField("depth", StateFields)!.GetValue(resourceState)! == 0,
            "Startup record reads were enclosed in a resource scope");
        Check((int)typeof(ColdTrace).GetProperty("ActiveStage", Static)!.GetValue(null)! == -1,
            "Startup record reads were enclosed in a frame stage");
        Span<byte> name = stackalloc byte[NameBytes];
        long began = Stopwatch.GetTimestamp();
        for (int i = 0; i < StartupRows; i++)
        {
            Check(readFlags() == 0xFEDCBA9800000000UL + (uint)i && readGraphic() == (ushort)i,
                "Startup numeric field changed");
            Check(read(name) == NameBytes && name[0] == (byte)('a' + i % 26) && name[19] == 0,
                "Startup name bytes changed");
        }
        startupReadsMs = (Stopwatch.GetTimestamp() - began) * 1000.0 / Stopwatch.Frequency;
        Check(!enabled || (long)resourceState!.GetType().GetField("frameRoots", StateFields)!.GetValue(resourceState)! - before == StartupRows,
            "Startup root read counters lost calls");
        Check((long)readerType.GetProperty("Position", Instance)!.GetValue(reader)! == records.Length,
            "Startup reader position changed");
        readerType.GetMethod("Dispose", Instance)!.Invoke(reader, null);
    }
    finally { File.Delete(temporary); }
    Console.SetError(saved);
    Console.WriteLine("RESOURCE_STARTUP_READS_OK mode=" + args[1] + " rows=" + StartupRows + " root_span_calls=" + StartupRows +
        " numeric_fields=true name_bytes=20 elapsed_ms=" + startupReadsMs.ToString("F3", CultureInfo.InvariantCulture));
    Console.SetError(output);
    var startupState = typeof(ResourceTrace).GetField("state", Static)!.GetValue(null);
    long beforeAssets = enabled ? (long)startupState!.GetType().GetField("frameRoots", StateFields)!.GetValue(startupState)! : 0;
    string assetResult = StartupAssetProbe.Run(folder, enabled);
    const int StartupAssetReads = 16384 + 65536 + 4096 * 2;
    Check(!enabled || (long)startupState!.GetType().GetField("frameRoots", StateFields)!.GetValue(startupState)! - beforeAssets == StartupAssetReads,
        "Actual tile/speech loaders lost startup root read observations");
    Console.WriteLine(assetResult + " root_span_calls=" + StartupAssetReads);
    var fna = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(folder, "FNA.dll"));
    var deviceType = fna.GetType("Microsoft.Xna.Framework.Graphics.GraphicsDevice", true)!;
    var device = RuntimeHelpers.GetUninitializedObject(deviceType); GC.SuppressFinalize(device);
    var sync = new object();
    deviceType.GetField("resourcesLock", Instance)!.SetValue(device, sync);
    var references = deviceType.GetField("resources", Instance) ?? deviceType.GetField("resourceReferences", Instance)!;
    references.SetValue(device, Activator.CreateInstance(references.FieldType));
    var add = deviceType.GetMethod("AddResourceReference", Instance)!;
    var remove = deviceType.GetMethod("RemoveResourceReference", Instance)!;
    var handle = GCHandle.Alloc(new object(), GCHandleType.Weak);
    try
    {
        using var ready = new ManualResetEventSlim();
        var worker = Task.Run(() => { lock (sync) { ready.Set(); Thread.Sleep(80); } });
        ready.Wait(); long draw = FrameBudget.Begin(FrameBudget.Draw);
        add.Invoke(device, new object[] { handle }); FrameBudget.End(FrameBudget.Draw, draw); worker.GetAwaiter().GetResult();
        Check((bool)remove.Invoke(device, new object[] { handle })! && !(bool)remove.Invoke(device, new object[] { handle })!, "Actual resource registration/removal result changed");
    }
    finally { handle.Free(); }
    // Force the original method's Monitor.Enter validation to throw and verify
    // its exact exception plus the diagnostic finally's depth restoration.
    deviceType.GetField("resourcesLock", Instance)!.SetValue(device, null);
    try { add.Invoke(device, new object[] { default(GCHandle) }); throw new Exception("Null lock unexpectedly succeeded"); }
    catch (TargetInvocationException e) when (e.InnerException is ArgumentNullException) { }
    var stateField = typeof(ResourceTrace).GetField("state", Static)!;
    if (!enabled) Check(stateField.GetValue(null) == null && !output.ToString().Contains("RESOURCE_"), "Disabled resource observations allocated/logged");
    else
    {
        var state = stateField.GetValue(null)!;
        object Value(string name) => state.GetType().GetField(name, StateFields)!.GetValue(state)!;
        void Set(string name, object value) => state.GetType().GetField(name, StateFields)!.SetValue(state, value);
        Check((int)Value("depth") == 0, "Resource registration exception leaked scope");
        var coldType = typeof(ColdTrace);
        int ActiveStage() => (int)coldType.GetProperty("ActiveStage", Static)!.GetValue(null)!;
        long updateScope = FrameBudget.Begin(FrameBudget.Update), networkScope = FrameBudget.BeginNetwork();
        long networkResource = ResourceTrace.Begin(11); Check(ActiveStage() == FrameBudget.Network, "Network resource stage lost"); ResourceTrace.End(11, networkResource);
        FrameBudget.EndNetwork(networkScope);
        long exceptionalNetwork = FrameBudget.BeginNetwork();
        try { try { throw new InvalidDataException("simulated original packet handler failure"); } finally { FrameBudget.EndNetwork(exceptionalNetwork); } }
        catch (InvalidDataException e) when (e.Message == "simulated original packet handler failure") { }
        Check(ActiveStage() == FrameBudget.Update && (int)Value("depth") == 0, "Exceptional network cleanup corrupted stage/resource depth");
        long updateResource = ResourceTrace.Begin(11); Check(ActiveStage() == FrameBudget.Update, "Network cleanup popped enclosing update stage"); ResourceTrace.End(11, updateResource);
        FrameBudget.End(FrameBudget.Update, updateScope); Check(ActiveStage() == -1, "Stage cleanup leaked");
        var nestedStages = new Stack<long>();
        for (int i = 0; i < 18; i++) nestedStages.Push(FrameBudget.Begin(FrameBudget.Scene));
        Check(ActiveStage() == -1, "Overflowed stage falsely attributed");
        for (int i = 0; i < 3; i++) FrameBudget.End(FrameBudget.Scene, nestedStages.Pop());
        Check(ActiveStage() == FrameBudget.Scene, "Stage overflow did not recover");
        while (nestedStages.Count != 0) FrameBudget.End(FrameBudget.Scene, nestedStages.Pop());
        string[] slow = output.ToString().Split('\n').Where(l => l.StartsWith("RESOURCE_CALL ")).ToArray();
        Check(slow.Any(l => l.Contains("op=resource_register_lock_wait") && l.Contains("parent=resource_register") && l.Contains("stage=draw")), "Actual contended Monitor boundary/stage was not observed");
        Check(slow.All(l => l.Contains("cpu_ms=unavailable cpu_unavailable_reason=observer_overhead")), "Resource CPU fields imply a measurement");
        // Synthetic clock changes exercise nested accounting and rate caps
        // without extending the device test with multi-second artificial stalls.
        for (int i = 0; i < 12; i++)
        {
            long root = ResourceTrace.Begin(14), child = ResourceTrace.Begin(11);
            long[] begins = (long[])Value("began"); begins[1] = Stopwatch.GetTimestamp() - Stopwatch.Frequency * 60 / 1000;
            ColdTrace.EndNative(0, Stopwatch.GetTimestamp() - Stopwatch.Frequency / 100);
            ResourceTrace.End(11, child); begins[0] = Stopwatch.GetTimestamp() - Stopwatch.Frequency * 90 / 1000; ResourceTrace.End(14, root);
        }
        Check(output.ToString().Split('\n').Count(l => l.StartsWith("RESOURCE_CALL ")) == 8 && (long)Value("suppressed") > 0, "Resource slow records are not bounded");
        Check((long[])Value("nativeTotal") is var nested && nested[11] > 0 && nested[14] >= nested[11], "Nested FNA time was not propagated");
        Check(((long[])Value("self"))[14] < ((long[])Value("total"))[14], "Child time was not excluded from self");
        Set("nextReport", 1L); long flush = ResourceTrace.Begin(11); ResourceTrace.End(11, flush);
        Check(output.ToString().Contains("RESOURCE_WINDOW ") && output.ToString().Contains("inclusive_ms=") && output.ToString().Contains("RESOURCE_LIMITS ") &&
            output.ToString().Contains("window_observer_overhead_ms="), "Resource count/suppression/observer-cost windows missing");
        // Warm observations create no per-call objects, strings, delegates or
        // arrays; frequent resource scopes make no CPU queries.
        long outer = ResourceTrace.Begin(14);
        for (int i = 0; i < 10000; i++) { long token = ResourceTrace.Begin(11); ResourceTrace.End(11, token); }
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < 10000; i++) { long token = ResourceTrace.Begin(11); ResourceTrace.End(11, token); }
        long extra = GC.GetAllocatedBytesForCurrentThread() - before; Check(extra == 0, "Warm resource observations allocate bytes=" + extra); ResourceTrace.End(14, outer);
        Task.Run(() => { long token = ResourceTrace.Begin(11); ResourceTrace.End(11, token); Check(stateField.GetValue(null) != state, "Resource thread state shared"); }).GetAwaiter().GetResult();
        Console.SetError(new FailedWriter()); Set("nextReport", 1L); long fail = ResourceTrace.Begin(11); ResourceTrace.End(11, fail);
    }
}
finally { Console.SetError(saved); }
Console.WriteLine("RESOURCE_TRACE_OK mode=" + args[1] + " jit_all_scopes=24 actual_file_reads=true bytes=true positions=true actual_resource_lock=true original_exceptions=true nested=true bounded=true allocation_free=true thread_local=true");
delegate int Read(Span<byte> data);
delegate void ReadAt(long offset, Span<byte> data);
sealed class FailedWriter : TextWriter { public override System.Text.Encoding Encoding => System.Text.Encoding.UTF8; public override void WriteLine(string value) => throw new IOException("full fixture log"); }
