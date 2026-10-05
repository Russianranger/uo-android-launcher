using System.Reflection;

namespace Memento;

// A synchronous Chunk.Load sees one successful map-gate Length snapshot per
// original reader identity. Snapshots end with that chunk, including exceptions
// and early returns. No FileReader getter, byte read, lookup, or startup path is
// replaced globally. Nested chunks start independent snapshots on their thread.
public static class ChunkMetadata
{
    const int DepthCapacity = 8, ReaderCapacity = 16;
    [ThreadStatic] static State state;
    sealed class State
    {
        internal int depth, overflowDepth;
        internal long serial;
        internal Type lastReaderType;
        internal FieldInfo streamField;
        internal readonly Scope[] scopes = new Scope[DepthCapacity];
        internal State() { for (int i = 0; i < scopes.Length; i++) scopes[i] = new Scope(); }
    }
    sealed class Scope
    {
        internal long token;
        internal int count;
        internal readonly object[] readers = new object[ReaderCapacity];
        internal readonly long[] lengths = new long[ReaderCapacity];
        internal readonly FileStream[] streams = new FileStream[ReaderCapacity];
    }
    public static long Begin()
    {
        var s = state ??= new State();
        long token = ++s.serial;
        if (s.depth == DepthCapacity || s.overflowDepth != 0) { s.overflowDepth++; return -token; }
        var scope = s.scopes[s.depth++];
        scope.token = token; scope.count = 0;
        return token;
    }
    public static void End(long token)
    {
        if (token == 0 || state is not { } s) return;
        if (token < 0) { if (s.overflowDepth > 0) s.overflowDepth--; return; }
        if (s.depth == 0 || s.overflowDepth != 0) return;
        var scope = s.scopes[s.depth - 1];
        if (scope.token != token) return;
        Array.Clear(scope.readers, 0, scope.count);
        Array.Clear(scope.streams, 0, scope.count);
        scope.count = 0; scope.token = 0; s.depth--;
    }
    public static bool TryGet(object reader, out long length)
    {
        length = 0;
        if (reader == null || state is not { depth: > 0, overflowDepth: 0 } s) return false;
        var scope = s.scopes[s.depth - 1];
        for (int i = 0; i < scope.count; i++)
            if (ReferenceEquals(scope.readers[i], reader)) {
                // CanRead is an in-memory handle/lifetime check on FileStream.
                // A disposed backing stream falls through to the original getter
                // so that its original ObjectDisposedException is preserved.
                try { if (!scope.streams[i].CanRead) return false; }
                catch { return false; }
                length = scope.lengths[i]; return true;
            }
        return false;
    }
    // Called only after the original callvirt getter returned successfully.
    // A failed getter is retried normally and its exception is never cached.
    public static void Store(object reader, long length)
    {
        if (reader == null || state is not { depth: > 0, overflowDepth: 0 } s) return;
        var scope = s.scopes[s.depth - 1];
        for (int i = 0; i < scope.count; i++) if (ReferenceEquals(scope.readers[i], reader)) return;
        // Unexpectedly many reader identities safely fall back to live Length.
        if (scope.count == ReaderCapacity) return;
        FileStream stream;
        try {
            var type = reader.GetType();
            if (s.lastReaderType != type) {
                s.lastReaderType = type; s.streamField = null;
                for (var current = type; current != null; current = current.BaseType) {
                    if (current.FullName != "ClassicUO.IO.FileReader") continue;
                    var field = current.GetField("_stream", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.DeclaredOnly);
                    if (field != null && field.IsPrivate && field.IsInitOnly && field.FieldType == typeof(FileStream)) s.streamField = field;
                    break;
                }
            }
            // Unknown shapes are never cached. Reflection observes only the
            // exact readonly reader backing field, never Length or filesystem
            // metadata. One bounded field descriptor is retained per thread.
            if (s.streamField == null || s.streamField.GetValue(reader) is not FileStream file || !file.CanRead) return;
            stream = file;
        }
        catch { return; } // Cache admission cannot alter an already successful getter.
        int index = scope.count++;
        scope.readers[index] = reader; scope.lengths[index] = length; scope.streams[index] = stream;
    }
}
