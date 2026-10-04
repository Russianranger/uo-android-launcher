using System.Buffers.Binary;
using System.Diagnostics;
using System.Globalization;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text;
using Memento;

// These fixtures execute the imported vendor bodies. Only world/file inputs
// are synthetic; no vendor method, constructor, return or IL is substituted.
internal static class ChunkDiagnosticProbe
{
    const BindingFlags Instance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
    const BindingFlags Static = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
    delegate void Sanitize(ref int index);
    static void Check(bool value, string why) { if (!value) throw new InvalidOperationException(why); }
    static FieldInfo Field(Type type, string name)
    {
        for (Type current = type; current != null; current = current.BaseType)
        {
            var field = current.GetField(name, Instance | Static | BindingFlags.DeclaredOnly);
            if (field != null) return field;
        }
        throw new Exception(type + " missing " + name);
    }
    static void Set(object target, string name, object value) => Field(target.GetType(), name).SetValue(target, value);
    static object Value(object target, string name) => Field(target.GetType(), name).GetValue(target)!;
    static object State(Type type) => Field(type, "state").GetValue(null)!;
    static void AgeScope(long milliseconds)
    {
        object state = State(typeof(ChunkTrace));
        object scope = ((Array)Value(state, "scopes")).GetValue((int)Value(state, "depth") - 1)!;
        Set(scope, "began", Stopwatch.GetTimestamp() - Stopwatch.Frequency * milliseconds / 1000);
    }
    static void AgePart(long milliseconds)
    {
        object state = State(typeof(ChunkTrace)); Array parts = (Array)Value(state, "parts"); int index = (int)Value(state, "partDepth") - 1;
        object part = parts.GetValue(index)!;
        Set(part, "began", Stopwatch.GetTimestamp() - Stopwatch.Frequency * milliseconds / 1000); parts.SetValue(part, index);
    }
    static Dictionary<string, string> Record(string line) => line.Split(' ', StringSplitOptions.RemoveEmptyEntries)
        .Skip(1).Where(x => x.Contains('=')).Select(x => x.Split('=', 2)).ToDictionary(x => x[0], x => x[1]);

    internal static string Run(string folder, bool enabled)
    {
        var resourceField = Field(typeof(ResourceTrace), "state"); var chunkField = Field(typeof(ChunkTrace), "state");
        object previousResource = resourceField.GetValue(null), previousChunk = chunkField.GetValue(null);
        resourceField.SetValue(null, null); chunkField.SetValue(null, null);
        var saved = Console.Error; var output = new StringWriter(CultureInfo.InvariantCulture); Console.SetError(output);
        string temporary = Path.Combine(Path.GetTempPath(), "memento-chunks-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(temporary);
        var disposables = new List<IDisposable>(); var readers = new List<object>();
        var globals = new List<(FieldInfo field, object before)>(); object manager = null;
        System.Collections.IDictionary marked = null; object location = null;
        try
        {
            var game = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(folder, "TazUO.dll"));
            var assets = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(folder, "ClassicUO.Assets.dll"));
            var io = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(folder, "ClassicUO.IO.dll"));
            var mapType = game.GetType("ClassicUO.Game.Map.Map", true)!; var chunkType = game.GetType("ClassicUO.Game.Map.Chunk", true)!;
            var worldType = game.GetType("ClassicUO.Game.World", true)!; var managerType = assets.GetType("ClassicUO.Assets.UOFileManager", true)!;
            var loaderType = assets.GetType("ClassicUO.Assets.MapLoader", true)!; var readerType = io.GetType("ClassicUO.IO.MMFileReader", true)!;
            var indexType = assets.GetType("ClassicUO.Assets.IndexMap", true)!; var tileType = assets.GetType("ClassicUO.Assets.TileDataLoader", true)!;
            object Uninitialized(Type type) { object o = RuntimeHelpers.GetUninitializedObject(type); GC.SuppressFinalize(o); return o; }
            void Global(Type type, string name, object value) { var field = Field(type, name); globals.Add((field, field.GetValue(null))); field.SetValue(null, value); }
            object Reader(string name, byte[] bytes, bool gate = false)
            {
                string path = Path.Combine(temporary, name); File.WriteAllBytes(path, bytes);
                FileStream stream = gate ? new GateStream(path) : new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
                disposables.Add(stream);
                // Sanitization gates need the real inherited virtual Length
                // getter, but never read bytes. Leave them unmapped so external
                // truncation/growth is legal on Windows as well as Linux.
                object reader = gate ? Uninitialized(readerType) : readerType.GetConstructors(Instance).Single().Invoke(new object[] { stream });
                if (gate) Set(reader, "_stream", stream);
                readers.Add(reader); return reader;
            }
            var constructor = managerType.GetConstructors(Instance).Single();
            manager = constructor.Invoke(new[] { Enum.ToObject(constructor.GetParameters()[0].ParameterType, 0x07000900), temporary });
            object loader = managerType.GetProperty("Maps", Instance)!.GetValue(manager)!;
            object world = Uninitialized(worldType), map = Uninitialized(mapType); Set(map, "Index", 1); Set(map, "_world", world); Set(world, "<Map>k__BackingField", map);
            var clientType = game.GetType("ClassicUO.Client", true)!; var controllerType = game.GetType("ClassicUO.GameController", true)!;
            object controller = Uninitialized(controllerType), uo = Uninitialized(game.GetType("ClassicUO.UltimaOnline", true)!);
            Set(controller, "<UO>k__BackingField", uo); Set(uo, "<FileManager>k__BackingField", manager); Set(uo, "<World>k__BackingField", world);
            Global(clientType, "<Game>k__BackingField", controller);
            Global(game.GetType("ClassicUO.Configuration.ProfileManager", true)!, "<ProfilePath>k__BackingField", temporary);
            // A real texture index selects ApplyStretch's existing full neighbor
            // lookup branch, without constructing a GPU or changing that body.
            var landType = assets.GetType("ClassicUO.Assets.LandTiles", true)!;
            var landData = Array.CreateInstance(landType, 16384); object landRecord = Activator.CreateInstance(landType)!; Set(landRecord, "TexID", (ushort)1); landData.SetValue(landRecord, 10);
            Global(tileType, "_landData", landData); Global(tileType, "_staticData", Array.CreateInstance(assets.GetType("ClassicUO.Assets.StaticTiles", true)!, 256));
            object texmaps = managerType.GetProperty("Texmaps", Instance)!.GetValue(manager)!;
            var fileType = io.GetType("ClassicUO.IO.UOFile", true)!; object texfile = Uninitialized(fileType);
            var entryType = io.GetType("ClassicUO.IO.UOFileIndex", true)!; var entries = Array.CreateInstance(entryType, 2); object entry = Activator.CreateInstance(entryType)!;
            Set(entry, "Offset", 0L); Set(entry, "Length", 1); entries.SetValue(entry, 1); Set(texfile, "Entries", entries);
            Set(texmaps, "_file", texfile);
            object[] mapReaders = { Reader("map0.mul", MapBytes(0)), Reader("map1.mul", MapBytes(7)) };
            object staticReader = Reader("statics.mul", new byte[] { 100, 0, 1, 2, 12, 0x23, 0x01 });
            var blockData = Array.CreateInstance(indexType.MakeArrayType(), 6); var sizes = new int[6, 2];
            for (int mapIndex = 0; mapIndex < 6; mapIndex++)
            {
                sizes[mapIndex, 0] = sizes[mapIndex, 1] = 4;
                var blocks = Array.CreateInstance(indexType, 16);
                for (int block = 0; block < 16; block++)
                {
                    object index = Activator.CreateInstance(indexType)!;
                    Set(index, "MapFile", mapReaders[mapIndex == 1 ? 1 : 0]); Set(index, "MapAddress", (ulong)(block * 196));
                    Set(index, "StaticFile", staticReader); Set(index, "StaticAddress", 0UL); Set(index, "StaticCount", block == 5 ? 1U : 0U); blocks.SetValue(index, block);
                }
                blockData.SetValue(blocks, mapIndex);
            }
            Set(loader, "<MapBlocksSize>k__BackingField", sizes); Set(loader, "<BlockData>k__BackingField", blockData);
            object[] gates = { Reader("gate-map.mul", new byte[] { 1 }, true), Reader("gate-static.mul", new byte[] { 2 }, true), Reader("gate-index.mul", new byte[] { 3 }, true) };
            var gateArrays = new Array[3]; string[] gateFields = { "_currentMapFiles", "_currentStaticsFiles", "_currentIdxStaticsFiles" };
            for (int i = 0; i < 3; i++) { gateArrays[i] = Array.CreateInstance(readerType.BaseType!, 6); gateArrays[i].SetValue(gates[i], 1); Set(loader, gateFields[i], gateArrays[i]); }
            var sanitize = loaderType.GetMethod("SanitizeMapIndex", Instance)!.CreateDelegate<Sanitize>(loader);
            var z = mapType.GetMethod("GetTileZ", Instance)!.CreateDelegate<Func<int, int, sbyte>>(map);
            for (int i = 0; i < 3; i++)
            {
                gateArrays[i].SetValue(null, 1); int index = 1; sanitize(ref index); Check(index == 0 && z(9, 10) == Z(9, 10, 0), "Null map1 gate did not preserve map0 fallback"); gateArrays[i].SetValue(gates[i], 1);
                var stream = (GateStream)Value(gates[i], "_stream"); stream.SetLength(0); index = 1; sanitize(ref index); Check(index == 0 && z(9, 10) == Z(9, 10, 0), "Empty map1 gate did not preserve fallback");
                stream.SetLength(1); index = 1; sanitize(ref index); Check(index == 1 && z(9, 10) == Z(9, 10, 7), "Live file growth was cached or ignored");
            }
            int unchanged = 2; sanitize(ref unchanged); Check(unchanged == 2 && z(-1, 3) == -125 && z(3, -1) == -125 && z(40, 40) == -125, "Original map index/invalid tile results changed");
            var length = readerType.GetProperty("Length", Instance)!.GetMethod!.CreateDelegate<Func<long>>(gates[0]);
            var firstGate = (GateStream)Value(gates[0], "_stream"); long calls = firstGate.LengthCalls; Check(length() == 1 && firstGate.LengthCalls == calls + 1, "File length called the original getter more than once");
            // External growth is visible through the original opened stream.
            using (var writer = new FileStream(firstGate.Name, FileMode.Open, FileAccess.Write, FileShare.ReadWrite)) writer.SetLength(5);
            Check(length() == 5, "External live file growth was not forwarded"); firstGate.SetLength(1);

            var markerType = game.GetType("ClassicUO.Game.Managers.TileMarkerManager", true)!; object marker = markerType.GetProperty("Instance", Static)!.GetValue(null)!;
            marked = (System.Collections.IDictionary)Value(marker, "markedTiles"); location = Activator.CreateInstance(game.GetType("ClassicUO.Game.Managers.TileLocation", true)!, new object[] { 9, 10, 1 })!; marked.Add(location, (ushort)0x555);
            var markerMethod = markerType.GetMethod("IsTileMarked", Instance)!; object[] markerArgs = { 9, 10, 1, (ushort)0 }; Check((bool)markerMethod.Invoke(marker, markerArgs)! && (ushort)markerArgs[3] == 0x555, "Original marked tile out argument changed");
            markerArgs = new object[] { 0, 0, 1, (ushort)999 }; Check(!(bool)markerMethod.Invoke(marker, markerArgs)! && (ushort)markerArgs[3] == 0, "Original missing marker out argument changed");

            object chunk = chunkType.GetConstructor(new[] { worldType })!.Invoke(new[] { world }); Set(chunk, "X", 1); Set(chunk, "Y", 1);
            var load = chunkType.GetMethod("Load", Instance)!.CreateDelegate<Action<int, bool>>(chunk);
            firstGate.DelayCalls = 3;
            long stage = FrameBudget.Begin(FrameBudget.Draw); load(0, false); FrameBudget.End(FrameBudget.Draw, stage);
            Check(!(bool)Value(chunk, "IsLoading") && !(bool)Value(chunk, "IsDestroyed"), "Actual Chunk.Load state/finally changed");
            string fingerprint0 = ValidateChunk(chunk, 0);
            if (enabled)
            {
                string record = output.ToString().Split('\n').Last(x => x.StartsWith("CHUNK_LOAD ")); var fields = Record(record);
                Check(fields["input_map"] == "0" && fields["world_map"] == "1" && fields["chunk_x"] == "1" && fields["chunk_y"] == "1" && fields["radar"] == "false" && fields["stage"] == "draw", "Actual chunk identity/stage was not preserved");
                Check(fields["land_create_calls"] == "64" && fields["static_create_calls"] == "1" && fields["tile_insert_calls"] == "65" && fields["tile_marker_calls"] == "65" && fields["apply_stretch_calls"] == "64", "Actual construction/insertion part counts changed");
                Check(fields["get_tile_z_calls"] == "704" && fields["sanitize_map_index_calls"] == "705" && fields["file_length_calls"] == "2112", "Actual repeated tile/length call graph was not counted");
                Check(double.Parse(fields["sanitize_map_index_self_ms"], CultureInfo.InvariantCulture) < double.Parse(fields["sanitize_map_index_ms"], CultureInfo.InvariantCulture), "Nested file length time was double-counted as sanitize self");
                Check(fields["cpu_ms"] == "unavailable" && fields["mapblock_coverage"] == "get_tile_z_initial_unassigned", "Chunk output implies unsupported CPU/map-block coverage");
                Console.WriteLine(record);
            }
            object map1Chunk = chunkType.GetConstructor(new[] { worldType })!.Invoke(new[] { world }); Set(map1Chunk, "X", 1); Set(map1Chunk, "Y", 1);
            chunkType.GetMethod("Load", Instance)!.Invoke(map1Chunk, new object[] { 1, false });
            string fingerprint1 = ValidateChunk(map1Chunk, 7);
            // Empty map1 gates must preserve the original full-chunk fallback
            // as well as the separate Sanitize/GetTileZ results tested above.
            firstGate.SetLength(0);
            object fallbackChunk = chunkType.GetConstructor(new[] { worldType })!.Invoke(new[] { world }); Set(fallbackChunk, "X", 1); Set(fallbackChunk, "Y", 1);
            chunkType.GetMethod("Load", Instance)!.Invoke(fallbackChunk, new object[] { 1, false });
            string fingerprintFallback = ValidateChunk(fallbackChunk, 0);
            firstGate.SetLength(1);
            string fingerprint = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(fingerprint0 + fingerprint1 + fingerprintFallback))).ToLowerInvariant();
            // Original early-return and exception paths must unwind both scopes.
            var map0 = (Array)blockData.GetValue(0)!; object valid = map0.GetValue(5)!; object invalid = Activator.CreateInstance(indexType)!; Set(invalid, "MapAddress", ulong.MaxValue); map0.SetValue(invalid, 5);
            object emptyChunk = chunkType.GetConstructor(new[] { worldType })!.Invoke(new[] { world }); Set(emptyChunk, "X", 1); Set(emptyChunk, "Y", 1); chunkType.GetMethod("Load", Instance)!.Invoke(emptyChunk, new object[] { 0, true }); Check(!(bool)Value(emptyChunk, "IsLoading"), "Invalid block early return left IsLoading set");
            Set(world, "<Map>k__BackingField", null);
            try { chunkType.GetMethod("Load", Instance)!.Invoke(emptyChunk, new object[] { 0, false }); Check(!(bool)Value(emptyChunk, "IsLoading"), "Original invalid-block/null-map return changed"); }
            finally { Set(world, "<Map>k__BackingField", map); map0.SetValue(valid, 5); }
            object broken = chunkType.GetConstructor(new[] { worldType })!.Invoke(new object[] { null });
            try { chunkType.GetMethod("Load", Instance)!.Invoke(broken, new object[] { 0, false }); throw new Exception("Null world succeeded"); } catch (TargetInvocationException e) when (e.InnerException is NullReferenceException) { }
            Check(!(bool)Value(broken, "IsLoading"), "Original exceptional Chunk.Load finally was not retained");
            firstGate.Dispose(); try { length(); throw new Exception("Disposed original length succeeded"); } catch (ObjectDisposedException) { }
            try { load(1, false); throw new Exception("Disposed gate Chunk.Load succeeded"); } catch (ObjectDisposedException) { }
            Check(!(bool)Value(chunk, "IsLoading"), "Disposed original length leaked chunk loading flag");
            if (enabled) Check((int)Value(State(typeof(ChunkTrace)), "depth") == 0 && (int)Value(State(typeof(ChunkTrace)), "partDepth") == 0 && (int)Value(State(typeof(ResourceTrace)), "depth") == 0, "Actual original exceptions leaked a diagnostic scope");
            else Check(chunkField.GetValue(null) == null && resourceField.GetValue(null) == null && !output.ToString().Contains("CHUNK_") && !output.ToString().Contains("RESOURCE_"), "Disabled vendor chunk paths allocated diagnostic state or output");
            if (enabled) QualifyAccounting(output);
            return "CHUNK_VENDOR_OK mode=" + (enabled ? "enabled" : "disabled") + " actual_chunk_load=true actual_tile_z=true actual_sanitize=true actual_live_length=true map0_map1=true null_empty_fallback=true land=64 statics=1 original_out=true original_exceptions=true fingerprint=" + fingerprint;
        }
        catch
        {
            saved.Write(output.ToString());
            throw;
        }
        finally
        {
            Console.SetError(saved); foreach (var reader in readers) try { reader.GetType().GetMethod("Dispose", Instance)!.Invoke(reader, null); } catch { }
            foreach (var stream in disposables) stream.Dispose();
            if (marked != null && location != null) marked.Remove(location);
            for (int i = globals.Count - 1; i >= 0; i--) globals[i].field.SetValue(null, globals[i].before);
            // Global test inputs are removed. Restore the outer suite's diagnostic
            // window rather than letting synthetic cap tests affect later probes.
            resourceField.SetValue(null, previousResource); chunkField.SetValue(null, previousChunk); Directory.Delete(temporary, true);
        }
    }

    static sbyte Z(int x, int y, int offset) => (sbyte)(x + 2 * y - 40 + offset);
    static byte[] MapBytes(int offset)
    {
        byte[] result = new byte[16 * 196];
        for (int bx = 0; bx < 4; bx++) for (int by = 0; by < 4; by++) for (int y = 0; y < 8; y++) for (int x = 0; x < 8; x++)
        {
            int position = (bx * 4 + by) * 196 + 4 + (y * 8 + x) * 3; BinaryPrimitives.WriteUInt16LittleEndian(result.AsSpan(position), 10); result[position + 2] = unchecked((byte)Z(bx * 8 + x, by * 8 + y, offset));
        }
        return result;
    }
    static string ValidateChunk(object chunk, int offset)
    {
        var objects = (Array)chunk.GetType().GetProperty("Tiles", Instance)!.GetValue(chunk)!; var bytes = new MemoryStream(); var writer = new BinaryWriter(bytes); int lands = 0, statics = 0;
        for (int y = 0; y < 8; y++) for (int x = 0; x < 8; x++)
        {
            object value = objects.GetValue(x, y); int count = 0;
            for (; value != null; value = Value(value, "TNext"))
            {
                Check(++count <= 2, "Insertion list was cyclic or duplicated"); ushort px = (ushort)Value(value, "X"), py = (ushort)Value(value, "Y"); sbyte z = (sbyte)Value(value, "Z"); ushort graphic = (ushort)value.GetType().GetProperty("Graphic", Instance)!.GetValue(value)!;
                bool land = value.GetType().FullName == "ClassicUO.Game.GameObjects.Land";
                if (land) { lands++; Check(px == x + 8 && py == y + 8 && z == Z(px, py, offset) && graphic == 10, "Actual land bytes/coordinates changed"); }
                else { statics++; Check(value.GetType().FullName == "ClassicUO.Game.GameObjects.Static" && px == 9 && py == 10 && z == 12 && graphic == 100, "Actual static bytes/coordinates changed"); }
                ushort hue = (ushort)value.GetType().GetProperty("Hue", Instance)!.GetValue(value)!; Check(hue == (px == 9 && py == 10 ? 0x555 : 0), "Actual marker hue forwarding changed");
                writer.Write(land); writer.Write(px); writer.Write(py); writer.Write(z); writer.Write(graphic); writer.Write(hue);
                if (land) { writer.Write((sbyte)Value(value, "AverageZ")); writer.Write((sbyte)Value(value, "MinZ")); }
            }
        }
        Check(lands == 64 && statics == 1, "Actual Chunk.Load object count changed"); writer.Flush(); return Convert.ToHexString(SHA256.HashData(bytes.ToArray())).ToLowerInvariant();
    }

    static void QualifyAccounting(StringWriter output)
    {
        var field = Field(typeof(ChunkTrace), "state"); var resource = Field(typeof(ResourceTrace), "state");
        field.SetValue(null, null); resource.SetValue(null, null); output.GetStringBuilder().Clear();
        long allocation = GC.GetAllocatedBytesForCurrentThread(); for (int i = 0; i < 10000; i++) Check(ChunkTrace.BeginPart(1) == 0, "Part active outside a chunk"); Check(GC.GetAllocatedBytesForCurrentThread() == allocation && field.GetValue(null) == null, "Outside-chunk hot path allocated state");
        long parent = ChunkTrace.Begin(1, 9, 2, 3, false), outerPart = ChunkTrace.BeginPart(3), child = ChunkTrace.Begin(7, 8, 10, 11, true);
        ChunkTrace.SetWorldMap(parent, 99); ChunkTrace.SetWorldMap(0, 99); ChunkTrace.SetWorldMap(child, 88);
        long length = ChunkTrace.BeginPart(1); AgePart(60); ChunkTrace.EndPart(1, length); AgeScope(80); ChunkTrace.End(child);
        AgePart(100); ChunkTrace.EndPart(3, outerPart); AgeScope(120); ChunkTrace.End(parent);
        var lines = output.ToString().Split('\n').Where(x => x.StartsWith("CHUNK_LOAD ")).Select(Record).ToArray(); Check(lines.Length == 2, "Nested chunk records lost");
        var nested = lines.Single(x => x["input_map"] == "7"); var root = lines.Single(x => x["input_map"] == "1");
        Check(nested["world_map"] == "88" && nested["parent_chunk_id"] == root["chunk_id"] && root["world_map"] == "9" && int.Parse(nested["depth"]) == int.Parse(root["depth"]) + 1, "Nested identities/setter token isolation changed");
        Check(nested["file_length_calls"] == "1" && root["file_length_calls"] == "0" && root["apply_stretch_calls"] == "1" && double.Parse(root["apply_stretch_self_ms"], CultureInfo.InvariantCulture) < double.Parse(root["apply_stretch_ms"], CultureInfo.InvariantCulture), "Nested owner/exclusive part accounting changed");
        object mainState = State(typeof(ChunkTrace)); Task.Run(() => { long token = ChunkTrace.Begin(5, 6, 7, 8, false); Check(State(typeof(ChunkTrace)) != mainState, "Chunk state shared between threads"); ChunkTrace.End(token); }).GetAwaiter().GetResult();
        var scopes = new Stack<long>(); for (int i = 0; i < 10; i++) scopes.Push(ChunkTrace.Begin(1, 2, i, i, false)); Check(scopes.Peek() < 0 && ChunkTrace.BeginPart(1) == 0, "Chunk overflow falsely attributed parts"); ChunkTrace.End(scopes.Pop()); ChunkTrace.End(scopes.Pop());
        var parts = new Stack<long>(); for (int i = 0; i < 34; i++) parts.Push(ChunkTrace.BeginPart(1)); Check(parts.Peek() < 0, "Part overflow not bounded"); while (parts.Count != 0) ChunkTrace.EndPart(1, parts.Pop()); while (scopes.Count != 0) ChunkTrace.End(scopes.Pop());
        Check((int)Value(mainState, "depth") == 0 && (int)Value(mainState, "partDepth") == 0 && (int)Value(mainState, "overflowDepth") == 0 && (int)Value(mainState, "partOverflowDepth") == 0, "Overflow cleanup did not recover");
        long warm = ChunkTrace.Begin(0, 0, 0, 0, false); for (int i = 0; i < 10000; i++) { long token = ChunkTrace.BeginPart(1); ChunkTrace.EndPart(1, token); }
        allocation = GC.GetAllocatedBytesForCurrentThread(); for (int i = 0; i < 10000; i++) { long token = ChunkTrace.BeginPart(1); ChunkTrace.EndPart(1, token); } Check(GC.GetAllocatedBytesForCurrentThread() == allocation, "Warm chunk part scopes allocate"); ChunkTrace.End(warm);
        // Child Resource records cannot exhaust the identifying chunk budget.
        field.SetValue(null, null); resource.SetValue(null, null); output.GetStringBuilder().Clear(); long enclosing = ResourceTrace.Begin(14), chunk = ChunkTrace.Begin(1, 2, 3, 4, false);
        Set(State(typeof(ChunkTrace)), "nextReport", Stopwatch.GetTimestamp() + 3600 * Stopwatch.Frequency);
        Set(State(typeof(ResourceTrace)), "nextReport", Stopwatch.GetTimestamp() + 3600 * Stopwatch.Frequency);
        for (int i = 0; i < 12; i++) { long token = ResourceTrace.Begin(11); var state = State(typeof(ResourceTrace)); ((long[])Value(state, "began"))[1] = Stopwatch.GetTimestamp() - Stopwatch.Frequency * 60 / 1000; ResourceTrace.End(11, token); }
        AgeScope(90); ChunkTrace.End(chunk); Check(output.ToString().Length == 0, "Child output printed before enclosing resource cleanup"); ResourceTrace.End(14, enclosing);
        Check(output.ToString().Split('\n').Count(x => x.StartsWith("RESOURCE_CALL ")) == 8 && output.ToString().Split('\n').Count(x => x.StartsWith("CHUNK_LOAD ")) == 1, "Resource cap consumed chunk parent record");
        field.SetValue(null, null); output.GetStringBuilder().Clear();
        for (int i = 0; i < 12; i++) { long token = ChunkTrace.Begin(1, 2, 3, 4, false); if (i == 0) Set(State(typeof(ChunkTrace)), "nextReport", Stopwatch.GetTimestamp() + 3600 * Stopwatch.Frequency); AgeScope(i == 8 ? 400 : 60); ChunkTrace.End(token); }
        Check(output.ToString().Split('\n').Count(x => x.StartsWith("CHUNK_LOAD ")) == 8 && (long)Value(State(typeof(ChunkTrace)), "suppressed") == 4, "Chunk slow detail cap changed");
        Set(State(typeof(ChunkTrace)), "nextReport", 1L); long flush = ChunkTrace.Begin(0, 0, 0, 0, false); ChunkTrace.End(flush);
        var window = Record(output.ToString().Split('\n').Single(x => x.StartsWith("CHUNK_WINDOW "))); Check(window["calls"] == "13" && window["slow_calls"] == "12" && double.Parse(window["max_ms"], CultureInfo.InvariantCulture) >= 400, "Suppressed worst chunk was lost from window histogram");
        Check(output.ToString().Contains("slow_suppressed=4") && output.ToString().Contains("window_observer_overhead_ms="), "Chunk suppression/observer limits missing");
        Console.WriteLine("CHUNK_ACCOUNTING_OK nested=true thread_local=true exception_unwind=true depth_caps=true independent_parent_budget=true suppressed_peak=true deferred=true warm_allocation_free=true cpu_queries=false");
    }
    sealed class GateStream : FileStream
    {
        internal long LengthCalls; internal int DelayCalls;
        internal GateStream(string path) : base(path, FileMode.Open, FileAccess.ReadWrite, FileShare.ReadWrite) { }
        public override long Length { get { LengthCalls++; if (DelayCalls > 0) { DelayCalls--; Thread.Sleep(60); } return base.Length; } }
    }
}
