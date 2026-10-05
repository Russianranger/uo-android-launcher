using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using Memento;

if (args.Length != 3 || args[1] is not ("enabled" or "disabled") || args[2] is not ("optimized" or "baseline"))
    throw new ArgumentException("fixture-folder enabled|disabled optimized|baseline");
string folder = Path.GetFullPath(args[0]); bool enabled = args[1] == "enabled", optimized = args[2] == "optimized";
Environment.SetEnvironmentVariable("MEMENTO_COLD_TRACE", enabled ? "1" : "0");
string previousDirectory = Environment.CurrentDirectory;
string vendorDirectory = Path.Combine(Path.GetTempPath(), "memento-map-metadata-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(Path.Combine(vendorDirectory, "Data", "Client")); Environment.CurrentDirectory = vendorDirectory;
try {
    AssemblyLoadContext.Default.Resolving += (_, name) => { string file = Path.Combine(folder, name.Name + ".dll"); return File.Exists(file) ? AssemblyLoadContext.Default.LoadFromAssemblyPath(file) : null; };
    ColdTrace.Announce();
    int prepared = 0;
    foreach (var target in new[] { ("TazUO.dll", "ClassicUO.Game.Map.Chunk", "Load"), ("ClassicUO.Assets.dll", "ClassicUO.Assets.MapLoader", "SanitizeMapIndex") }) {
        var assembly = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(folder, target.Item1));
        var method = assembly.GetType(target.Item2, true)!.GetMethod(target.Item3, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)!;
        RuntimeHelpers.PrepareMethod(method.MethodHandle); prepared++;
    }
    Console.WriteLine(MapMetadataProbe.Run(folder, enabled, optimized));
    Console.WriteLine("MAP_METADATA_PROBE_OK mode=" + args[1] + " optimization=" + args[2] + " jit_vendor_boundaries=" + prepared + " startup_getter_unchanged=true cpu_queries=false");
}
finally { Environment.CurrentDirectory = previousDirectory; Directory.Delete(vendorDirectory, true); }
