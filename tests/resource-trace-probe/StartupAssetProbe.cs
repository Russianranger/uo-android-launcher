using System.Diagnostics;
using System.Globalization;
using System.Reflection;
using System.Runtime.Loader;
using System.Runtime.InteropServices;
using System.Text;

// Execute the actual vendor startup loaders with a full tile table. Small read
// loops and JIT preparation do not reproduce the high call count reached before
// the first frame on Wine/FEX. Assets are synthetic and live only in a unique
// temporary directory; no fixture DLL or user asset is written by this probe.
internal static class StartupAssetProbe
{
    const BindingFlags Instance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
    const BindingFlags Static = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
    const int LandGroups = 512, StaticGroups = 2048, RecordsPerGroup = 32, SpeechCount = 4096;
    const ulong LandFlagBase = 0x100000000, StaticFlagBase = 0x200000000;

    internal static string Run(string folder, bool enabled)
    {
        var assets = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(Path.GetFullPath(folder), "ClassicUO.Assets.dll"));
        var managerType = assets.GetType("ClassicUO.Assets.UOFileManager", true)!;
        var tileType = assets.GetType("ClassicUO.Assets.TileDataLoader", true)!;
        var speechType = assets.GetType("ClassicUO.Assets.SpeechesLoader", true)!;
        string temporary = Path.Combine(Path.GetTempPath(), "memento-startup-assets-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temporary);
        object manager = null;
        try
        {
            WriteTileData(Path.Combine(temporary, "tiledata.mul"));
            WriteSpeech(Path.Combine(temporary, "speech.mul"));
            // 7.0.9.0 is the exact vendor branch threshold for 64-bit tile flags.
            var constructor = managerType.GetConstructors(Instance).Single();
            object version = Enum.ToObject(constructor.GetParameters()[0].ParameterType, 0x07000900);
            manager = constructor.Invoke(new[] { version, temporary });
            object tiles = managerType.GetProperty("TileData", Instance)!.GetValue(manager)!;
            object speeches = managerType.GetProperty("Speeches", Instance)!.GetValue(manager)!;
            Check(tiles.GetType() == tileType && speeches.GetType() == speechType, "The actual startup loaders were not constructed");

            // Only the vendor Load calls are timed. File generation, manager
            // construction and verification are outside these measurements.
            double tileMs = Time(tileType.GetMethod("Load", Instance)!, tiles);
            double speechMs = Time(speechType.GetMethod("Load", Instance)!, speeches);
            int staticStorageCount = ValidateTiles(tileType, assets, new FileInfo(Path.Combine(temporary, "tiledata.mul")).Length);
            ValidateSpeech(speechType, speeches, assets);
            return "RESOURCE_STARTUP_ASSETS_OK mode=" + (enabled ? "enabled" : "disabled") +
                " actual_tile_loader=true actual_speech_loader=true land_count=" + LandGroups * RecordsPerGroup +
                " static_decoded_count=" + StaticGroups * RecordsPerGroup + " static_storage_count=" + staticStorageCount + " speech_count=" + SpeechCount +
                " names=true flags=true values=true tile_ms=" + tileMs.ToString("F3", CultureInfo.InvariantCulture) +
                " speech_ms=" + speechMs.ToString("F3", CultureInfo.InvariantCulture);
        }
        finally
        {
            // Original TileDataLoader uses static arrays. Clear only the arrays
            // created by this isolated probe after validation to avoid retaining
            // a synthetic world for the rest of the resource test process.
            if (manager != null) managerType.GetMethod("Dispose", Instance)!.Invoke(manager, null);
            foreach (string name in new[] { "_landData", "_staticData" })
            {
                var field = tileType.GetField(name, Static)!;
                field.SetValue(null, Array.CreateInstance(field.FieldType.GetElementType()!, 0));
            }
            Directory.Delete(temporary, true);
        }
    }

    static double Time(MethodInfo method, object target)
    {
        long start = Stopwatch.GetTimestamp();
        method.Invoke(target, null);
        return Stopwatch.GetElapsedTime(start).TotalMilliseconds;
    }

    static void WriteTileData(string path)
    {
        using var stream = File.Create(path);
        using var writer = new BinaryWriter(stream, Encoding.UTF8);
        for (int group = 0; group < LandGroups; group++)
        {
            writer.Write((uint)group);
            for (int slot = 0; slot < RecordsPerGroup; slot++)
            {
                int index = group * RecordsPerGroup + slot;
                writer.Write(LandFlagBase + (uint)index);
                writer.Write((ushort)index);
                WriteName(writer, "land_" + index.ToString(CultureInfo.InvariantCulture));
            }
        }
        for (int group = 0; group < StaticGroups; group++)
        {
            writer.Write((uint)group);
            for (int slot = 0; slot < RecordsPerGroup; slot++)
            {
                int index = group * RecordsPerGroup + slot;
                writer.Write(StaticFlagBase + (uint)index);
                writer.Write((byte)(index % 251)); // weight
                writer.Write((byte)(index % 29));  // layer
                writer.Write(index * 3);          // count
                writer.Write((ushort)index);      // animation
                writer.Write((ushort)(index ^ 0x1234)); // hue
                writer.Write((ushort)(index ^ 0x4321)); // light index
                writer.Write((byte)(index % 127)); // height
                WriteName(writer, "static_" + index.ToString(CultureInfo.InvariantCulture));
            }
        }
        Check(stream.Length == LandGroups * (4 + RecordsPerGroup * 30) + StaticGroups * (4 + RecordsPerGroup * 41), "Synthetic tiledata format/length mismatch");
    }

    static void WriteName(BinaryWriter writer, string name)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(name);
        Check(bytes.Length < 20, "Synthetic tile name exceeds the vendor fixed field");
        writer.Write(bytes);
        writer.Write(new byte[20 - bytes.Length]);
    }

    static void WriteSpeech(string path)
    {
        using var stream = File.Create(path);
        using var writer = new BinaryWriter(stream, Encoding.UTF8);
        for (int index = 0; index < SpeechCount; index++)
        {
            byte[] text = Encoding.UTF8.GetBytes("*speech_" + index.ToString(CultureInfo.InvariantCulture) + "*");
            // Speech headers use big-endian ushort id and body byte count.
            writer.Write((byte)(index >> 8)); writer.Write((byte)index);
            writer.Write((byte)(text.Length >> 8)); writer.Write((byte)text.Length);
            writer.Write(text);
        }
    }

    static int ValidateTiles(Type loader, Assembly assets, long length)
    {
        var land = (Array)loader.GetField("_landData", Static)!.GetValue(null)!;
        var statics = (Array)loader.GetField("_staticData", Static)!.GetValue(null)!;
        // The verified vendor DLL declares LPStr tile names in its marshalled
        // group structs, then reads fixed 20-byte names in Load. Preserve that
        // existing group-count calculation, including zeroed unused tail entries.
        int landGroupSize = Marshal.SizeOf(assets.GetType("ClassicUO.Assets.LandGroupNew", true)!);
        int staticGroupSize = Marshal.SizeOf(assets.GetType("ClassicUO.Assets.StaticGroupNew", true)!);
        int expectedStorage = checked((int)((length - LandGroups * landGroupSize) / staticGroupSize) * RecordsPerGroup);
        Check(land.Length == LandGroups * RecordsPerGroup && statics.Length == expectedStorage &&
            statics.Length >= StaticGroups * RecordsPerGroup, "Actual tile loader returned wrong storage counts land=" + land.Length + " static=" + statics.Length);
        var landType = assets.GetType("ClassicUO.Assets.LandTiles", true)!;
        var staticType = assets.GetType("ClassicUO.Assets.StaticTiles", true)!;
        var landName = landType.GetField("Name", Instance)!;
        var landFlags = landType.GetField("Flags", Instance)!;
        var landTex = landType.GetField("TexID", Instance)!;
        var staticFields = new[] { "Name", "Flags", "Weight", "Layer", "Count", "AnimID", "Hue", "LightIndex", "Height" }
            .ToDictionary(name => name, name => staticType.GetField(name, Instance)!);
        for (int index = 0; index < land.Length; index++)
        {
            object value = land.GetValue(index)!;
            Check((string)landName.GetValue(value)! == "land_" + index.ToString(CultureInfo.InvariantCulture) &&
                Convert.ToUInt64(landFlags.GetValue(value), CultureInfo.InvariantCulture) == LandFlagBase + (uint)index &&
                (ushort)landTex.GetValue(value)! == index, "Actual land record differs at " + index);
        }
        for (int index = 0; index < StaticGroups * RecordsPerGroup; index++)
        {
            object value = statics.GetValue(index)!;
            Check((string)staticFields["Name"].GetValue(value)! == "static_" + index.ToString(CultureInfo.InvariantCulture) &&
                Convert.ToUInt64(staticFields["Flags"].GetValue(value), CultureInfo.InvariantCulture) == StaticFlagBase + (uint)index &&
                (byte)staticFields["Weight"].GetValue(value)! == index % 251 &&
                (byte)staticFields["Layer"].GetValue(value)! == index % 29 &&
                (int)staticFields["Count"].GetValue(value)! == index * 3 &&
                (ushort)staticFields["AnimID"].GetValue(value)! == (ushort)index &&
                (ushort)staticFields["Hue"].GetValue(value)! == (ushort)(index ^ 0x1234) &&
                (ushort)staticFields["LightIndex"].GetValue(value)! == (ushort)(index ^ 0x4321) &&
                (byte)staticFields["Height"].GetValue(value)! == index % 127, "Actual static record differs at " + index);
        }
        for (int index = StaticGroups * RecordsPerGroup; index < statics.Length; index++)
        {
            object value = statics.GetValue(index)!;
            Check(staticFields["Name"].GetValue(value) == null &&
                Convert.ToUInt64(staticFields["Flags"].GetValue(value), CultureInfo.InvariantCulture) == 0 &&
                (int)staticFields["Count"].GetValue(value)! == 0 &&
                (byte)staticFields["Height"].GetValue(value)! == 0, "Unused vendor tile tail changed at " + index);
        }
        return statics.Length;
    }

    static void ValidateSpeech(Type loader, object target, Assembly assets)
    {
        var speech = (Array)loader.GetField("_speech", Instance)!.GetValue(target)!;
        Check(speech.Length == SpeechCount, "Actual speech loader returned wrong count");
        var entry = assets.GetType("ClassicUO.Assets.SpeechEntry", true)!;
        var id = entry.GetProperty("KeywordID", Instance)!;
        var keywords = entry.GetProperty("Keywords", Instance)!;
        var start = entry.GetProperty("CheckStart", Instance)!;
        var end = entry.GetProperty("CheckEnd", Instance)!;
        for (int index = 0; index < speech.Length; index++)
        {
            object value = speech.GetValue(index)!;
            Check((short)id.GetValue(value)! == index &&
                ((string[])keywords.GetValue(value)!).SequenceEqual(new[] { "speech_" + index.ToString(CultureInfo.InvariantCulture) }) &&
                (bool)start.GetValue(value)! && (bool)end.GetValue(value)!, "Actual speech record differs at " + index);
        }
    }

    static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
