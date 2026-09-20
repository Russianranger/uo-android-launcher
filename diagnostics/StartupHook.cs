using System;
using System.IO;
using System.Reflection;
using System.Runtime.ExceptionServices;
using System.Runtime.InteropServices;
using System.Threading;

// .NET startup hooks require this exact type name and signature. No game code
// is changed; exceptions retain their normal propagation and termination.
internal static class StartupHook
{
    private static readonly object Gate = new object();
    [ThreadStatic] private static bool writing;
    [ThreadStatic] private static bool inspecting;
    private static string path;
    private static int movementExceptions;

    public static void Initialize()
    {
        path = Environment.GetEnvironmentVariable("MEMENTO_MANAGED_LOG");
        Write("Hook active: " + RuntimeInformation.FrameworkDescription);
        AppDomain.CurrentDomain.AssemblyLoad += (_, args) =>
        {
            try
            {
                var assembly = args.LoadedAssembly;
                string name = assembly.GetName().Name;
                if (name == "TazUO" || name == "ClassicUO")
                    Write("Client: " + assembly.GetName() + " file version " +
                          assembly.GetCustomAttribute<AssemblyFileVersionAttribute>()?.Version);
            }
            catch { }
        };
        AppDomain.CurrentDomain.FirstChanceException += FirstChance;
        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
            Write("UNHANDLED terminating=" + args.IsTerminating + "\n" + args.ExceptionObject);
    }

    private static void FirstChance(object sender, FirstChanceExceptionEventArgs args)
    {
        if (writing || inspecting || Volatile.Read(ref movementExceptions) >= 16) return;
        inspecting = true;
        try
        {
            string stack = args.Exception.StackTrace;
            if (stack == null || !stack.Contains("ClassicUO.Game.Pathfinder")) return;
            if (Interlocked.Increment(ref movementExceptions) <= 16)
                Write("PATHFINDER FIRST CHANCE\n" + args.Exception);
        }
        catch { }
        finally { inspecting = false; }
    }

    private static void Write(string message)
    {
        if (writing || string.IsNullOrEmpty(path)) return;
        writing = true;
        try
        {
            lock (Gate)
            {
                if (message.Length > 16000) message = message.Substring(0,16000);
                if (File.Exists(path) && new FileInfo(path).Length > 256*1024) return;
                File.AppendAllText(path, DateTime.UtcNow.ToString("O") + " " + message + "\n");
            }
        }
        catch { /* Diagnostics must not become another client failure. */ }
        finally { writing = false; }
    }
}
