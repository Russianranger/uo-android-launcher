using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;

// Same bundled .NET version and IL-only System.Runtime assembly as the reported
// TazUO installation. No game files, graphics driver or server are involved.
public static class ManagedProbe
{
    public static int Main(string[] args)
    {
        Assembly runtime=Assembly.LoadFrom(Path.Combine(AppContext.BaseDirectory,"System.Runtime.dll"));
        Console.WriteLine("MEMENTO_MANAGED_OK " + RuntimeInformation.FrameworkDescription + " " + runtime.GetName().Name);
        if (args.Length > 0)
        {
            // TazUO's JSON property names and Main.Boot directory/file checks:
            // PlayTazUO/TazUO commit 3212623f63436be1c0f4e3b308b202b29597c026.
            var settings=JsonSerializer.Deserialize<ClientSettings>(File.ReadAllText(args[0]));
            if (settings == null || !Directory.Exists(settings.Directory) ||
                !File.Exists(Path.Combine(settings.Directory,"tiledata.mul")))
            {
                Console.WriteLine("MEMENTO_CONFIG_INVALID UO directory");
                return 2;
            }
            if (settings.Version != "7.0.15.1" || settings.IP != "127.0.0.1" || settings.Port != 2593)
                return 3;
            Console.WriteLine("MEMENTO_CONFIG_OK " + settings.Directory + " " + settings.Version);
        }
        return 0;
    }
}

public sealed class ClientSettings
{
    [JsonPropertyName("ultimaonlinedirectory")] public string Directory { get; set; } = "";
    [JsonPropertyName("clientversion")] public string Version { get; set; } = "";
    [JsonPropertyName("ip")] public string IP { get; set; } = "";
    [JsonPropertyName("port")] public ushort Port { get; set; } = 2593;
}
