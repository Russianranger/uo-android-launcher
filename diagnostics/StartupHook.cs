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
    private static readonly System.Collections.Generic.HashSet<Assembly> observed = new System.Collections.Generic.HashSet<Assembly>();
    [ThreadStatic] private static bool writing;
    [ThreadStatic] private static bool inspecting;
    private static string path;
    private static int movementExceptions;
    private static int graphicsMessages;
    private static volatile Assembly clientAssembly;
    private static Timer sampler;
    private static int samples;

    public static void Initialize()
    {
        path = Environment.GetEnvironmentVariable("MEMENTO_MANAGED_LOG");
        Write("Hook active: " + RuntimeInformation.FrameworkDescription);
        AppDomain.CurrentDomain.AssemblyLoad += (_, args) => ObserveAssembly(args.LoadedAssembly);
        foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies()) ObserveAssembly(assembly);
        sampler = new Timer(_ => SampleClient(), null, 10000, 10000);
        AppDomain.CurrentDomain.FirstChanceException += FirstChance;
        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
            Write("UNHANDLED terminating=" + args.IsTerminating + "\n" + args.ExceptionObject);
    }

    private static void ObserveAssembly(Assembly assembly)
    {
        lock (Gate) { if (!observed.Add(assembly)) return; }
        try
        {
            string name = assembly.GetName().Name;
            if (name == "TazUO" || name == "ClassicUO")
            {
                clientAssembly = assembly;
                Write("Client: " + assembly.GetName() + " file version " +
                      assembly.GetCustomAttribute<AssemblyFileVersionAttribute>()?.Version);
            }
            if (name != "FNA") return;
            Type logger = assembly.GetType("Microsoft.Xna.Framework.FNALoggerEXT");
            if (logger == null) return;
            foreach (string level in new[] {"LogInfo", "LogWarn", "LogError"})
            {
                FieldInfo field = logger.GetField(level, BindingFlags.Public | BindingFlags.Static);
                if (field == null || field.FieldType != typeof(Action<string>)) continue;
                Action<string> capture = message =>
                {
                    if (Interlocked.Increment(ref graphicsMessages) <= 64)
                        Write("FNA " + level + ": " + Limit(message, 1024));
                };
                field.SetValue(null, Delegate.Combine(field.GetValue(null) as Delegate, capture));
            }
            Write("FNA graphics logging attached: " + assembly.GetName());
        }
        catch (Exception error) { Write("Optional graphics diagnostics unavailable: " + error.GetType().Name); }
    }

    // Read only cached managed properties. Never invoke native graphics/window
    // APIs or mutate game state from this timer thread.
    private static object Member(object target, string name)
    {
        if (target == null) return null;
        Type type = target as Type ?? target.GetType();
        object instance = target is Type ? null : target;
        const BindingFlags flags = BindingFlags.Public | BindingFlags.Static | BindingFlags.Instance;
        return type.GetProperty(name, flags)?.GetValue(instance) ?? type.GetField(name, flags)?.GetValue(instance);
    }

    private static void SampleClient()
    {
        if (Interlocked.Increment(ref samples) > 360) { sampler?.Dispose(); return; }
        try
        {
            Assembly assembly = clientAssembly;
            if (assembly == null) return;
            object game = Member(assembly.GetType("ClassicUO.Client"), "Game");
            if (game == null) return;
            object fps = Member(assembly.GetType("ClassicUO.CUOEnviroment"), "CurrentRefreshRate");
            object scene = Member(game, "Scene");
            Write("CLIENT SAMPLE fps=" + fps + " active=" + Member(game, "IsActive") +
                  " scene=" + scene?.GetType().Name + " managed_bytes=" + GC.GetTotalMemory(false) +
                  " gc_collections=" + GC.CollectionCount(0) + "/" + GC.CollectionCount(1) + "/" + GC.CollectionCount(2));
        }
        catch { }
    }

    private static void FirstChance(object sender, FirstChanceExceptionEventArgs args)
    {
        if (writing || inspecting || Volatile.Read(ref movementExceptions) >= 16) return;
        // File/assembly probes and script control-flow exceptions can be very
        // frequent. Do not construct a stack for those on every exception.
        if (!(args.Exception is InvalidOperationException || args.Exception is IndexOutOfRangeException ||
              args.Exception is NullReferenceException || args.Exception is AccessViolationException)) return;
        inspecting = true;
        try
        {
            // At first chance, the exception's own stack can still be empty.
            // Capture the throwing thread while it is still in Pathfinder.
            string stack = args.Exception.StackTrace ?? "";
            if (!Relevant(stack))
                stack = new System.Diagnostics.StackTrace(1, false).ToString();
            if (!Relevant(stack)) return;
            if (Interlocked.Increment(ref movementExceptions) <= 16)
                Write((stack.Contains("ClassicUO.Game.Pathfinder") ? "PATHFINDER" : "RENDER LIST") +
                      " FIRST CHANCE thread=" + Environment.CurrentManagedThreadId + "\n" +
                      Limit(args.Exception + "\nThrowing thread:\n" + stack, 4096));
        }
        catch { }
        finally { inspecting = false; }
    }

    private static bool Relevant(string stack) => stack.Contains("ClassicUO.Game.Pathfinder") ||
        stack.Contains("ClassicUO.Game.Scenes.GameScene.DrawRenderList");
    private static string Limit(string text, int length) => text == null ? "" : text.Length > length ? text.Substring(0,length) : text;

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
