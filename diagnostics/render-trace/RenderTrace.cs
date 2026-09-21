using System;
using System.Collections.Concurrent;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Threading;

// Loaded once by the host so the added assembly reference resolves even when
// the imported client's deps.json does not list this diagnostic component.
internal static class StartupHook
{
    public static void Initialize() => Memento.RenderTrace.Announce();
}

namespace Memento
{
    public struct ReadScope
    {
        internal object List;
        internal SceneState State;
        internal int Version, Count, Thread, Readers;
        internal long Fill;
    }

    internal sealed class SceneState
    {
        internal long Fill;
        internal int LastWriter, Readers;
    }

    // No timer, first-chance handler, graphics call, or mutation of game state.
    public static class RenderTrace
    {
        static readonly ConditionalWeakTable<object, SceneState> scenes = new();
        static readonly ConcurrentDictionary<Type, FieldInfo> versions = new();
        static readonly ConcurrentDictionary<Type, FieldInfo> counts = new();
        static int messages;
        static bool active = Environment.GetEnvironmentVariable("MEMENTO_RENDER_TRACE") == "1";
        const BindingFlags Fields = BindingFlags.Instance | BindingFlags.NonPublic;

        public static void Announce()
        {
            if (active)
                Write("RENDER_TRACE_ACTIVE revision=2 boundary_probes_only progress=" + RenderProgress.Open());
        }

        static int Value(object list, ConcurrentDictionary<Type, FieldInfo> cache, string name)
            => (int)cache.GetOrAdd(list.GetType(), type => type.GetField(name, Fields)).GetValue(list);

        public static void Fill(object scene)
        {
            if (!active) return;
            RenderProgress.Record(1);
            try
            {
                SceneState state = scenes.GetOrCreateValue(scene);
                Volatile.Write(ref state.LastWriter, Environment.CurrentManagedThreadId);
                long fill = Interlocked.Increment(ref state.Fill);
                int readers = Volatile.Read(ref state.Readers);
                RenderProgress.Record(1, readers: readers, fill: fill, issue: readers > 0 ? 1 : 0);
                if (readers > 0 && Interlocked.Increment(ref messages) <= 8)
                    Write("RENDER_WRITE_DURING_READ fill=" + fill + " readers=" + readers +
                          " writer_thread=" + state.LastWriter);
            }
            catch { } // A diagnostic failure must not change the original failure.
        }

        public static ReadScope Begin(object scene, object list)
        {
            if (!active) return default;
            RenderProgress.Record(2);
            try
            {
                SceneState state = scenes.GetOrCreateValue(scene);
                var scope = new ReadScope {
                    List = list, State = state,
                    Version = Value(list, versions, "_version"),
                    Count = Value(list, counts, "_size"),
                    Thread = Environment.CurrentManagedThreadId,
                    Fill = Interlocked.Read(ref state.Fill)
                };
                scope.Readers = Interlocked.Increment(ref state.Readers);
                RenderProgress.Record(3, scope.Count, scope.Version, scope.Readers, scope.Fill);
                return scope;
            }
            catch { RenderProgress.Record(7); return default; }
        }

        public static void Failed(ReadScope scope, object enumerator, Exception error)
        {
            if (scope.State == null) return;
            RenderProgress.Record(4, scope.Count, scope.Version, scope.Readers, scope.Fill, 2, error.HResult);
            // Emit the fact before reflection/formatting can fail. Never call
            // Exception.ToString/StackTrace in this diagnostic error path.
            Write("RENDER_FAILURE_ENTER revision=2 hresult=" + error.HResult);
            try
            {
                Type type = enumerator.GetType();
                object capturedList = type.GetField("_list", Fields).GetValue(enumerator);
                object capturedVersion = type.GetField("_version", Fields).GetValue(enumerator);
                object index = type.GetField("_index", Fields).GetValue(enumerator);
                int currentVersion = Value(scope.List, versions, "_version");
                Write("RENDER_ENUMERATOR_FAILURE revision=2" +
                    " begin_version=" + scope.Version + " enumerator_version=" + capturedVersion +
                    " current_version=" + currentVersion + " enumerator_index=" + index +
                    " same_list=" + ReferenceEquals(scope.List, capturedList) +
                    " begin_count=" + scope.Count + " current_count=" + Value(scope.List, counts, "_size") +
                    " begin_thread=" + scope.Thread + " failure_thread=" + Environment.CurrentManagedThreadId +
                    " begin_fill=" + scope.Fill + " current_fill=" + Interlocked.Read(ref scope.State.Fill) +
                    " last_writer_thread=" + Volatile.Read(ref scope.State.LastWriter) +
                    " begin_readers=" + scope.Readers + " current_readers=" + Volatile.Read(ref scope.State.Readers) +
                    " exception_type=" + error.GetType().FullName + " hresult=" + error.HResult);
            }
            catch (Exception diagnosticError) { Write("RENDER_TRACE_UNAVAILABLE " + diagnosticError.GetType().Name); }
        }

        public static void End(ReadScope scope)
        {
            if (scope.State != null)
            {
                int readers = Interlocked.Decrement(ref scope.State.Readers);
                RenderProgress.Record(5, scope.Count, scope.Version, readers, scope.Fill);
            }
        }

        static void Write(string message)
        {
            try { Console.Error.WriteLine(message); } catch { }
        }
    }
}
