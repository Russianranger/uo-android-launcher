using System.Diagnostics;
using System.Globalization;
using System.Text;

namespace Memento;

// Only active inside an observed Chunk.Load. Parts count original calls; their
// inclusive/self wall times are not CPU time. Fixed arrays avoid per-call
// allocations, and a separate record budget keeps child resource records from
// consuming the identifying chunk summary.
public static class ChunkTrace
{
    const int Capacity = 8, PartCapacity = 32, Limit = 8;
    [ThreadStatic] static State state;
    sealed class State
    {
        internal int depth, overflowDepth, partDepth, partOverflowDepth, pending, written;
        internal long serial, windowStarted, nextReport, calls, wall, peak, slowCalls, observer, suppressed, overflow, partOverflow, frameObserver;
        internal readonly Scope[] scopes = new Scope[Capacity];
        internal readonly Part[] parts = new Part[PartCapacity];
        internal readonly Record[] records = new Record[Limit];
        internal readonly long[] counts = new long[ResourceOperations.ChunkParts.Length], total = new long[ResourceOperations.ChunkParts.Length], self = new long[ResourceOperations.ChunkParts.Length], peaks = new long[ResourceOperations.ChunkParts.Length];
        internal State()
        {
            for (int i = 0; i < scopes.Length; i++) scopes[i] = new Scope();
            for (int i = 0; i < records.Length; i++) records[i] = new Record();
        }
    }
    sealed class Scope
    {
        internal long token, parentToken, began, frame, frameStart, rootParts, observer;
        internal int inputMap, worldMap, x, y, stage, depth;
        internal bool radar;
        internal readonly long[] counts = new long[ResourceOperations.ChunkParts.Length], total = new long[ResourceOperations.ChunkParts.Length], self = new long[ResourceOperations.ChunkParts.Length], peaks = new long[ResourceOperations.ChunkParts.Length];
    }
    struct Part
    {
        internal long token, began, children, ownerToken;
        internal int operation, owner;
        internal bool root;
    }
    sealed class Record
    {
        internal long token, parentToken, frame, frameStart, began, wall, rootParts, observer;
        internal int inputMap, worldMap, x, y, stage, depth;
        internal bool radar;
        internal readonly long[] counts = new long[ResourceOperations.ChunkParts.Length], total = new long[ResourceOperations.ChunkParts.Length], self = new long[ResourceOperations.ChunkParts.Length], peaks = new long[ResourceOperations.ChunkParts.Length];
    }
    public static long Begin(int inputMap, int worldMap, int x, int y, bool radar)
    {
        if (!ColdTrace.Enabled) return 0;
        long entered = Stopwatch.GetTimestamp();
        var s = state ??= new State();
        if (s.nextReport == 0) { s.windowStarted = entered; s.nextReport = entered + 5 * Stopwatch.Frequency; }
        long token = ++s.serial;
        if (s.depth == Capacity || s.overflowDepth != 0)
        {
            s.overflowDepth++; s.overflow++;
            AddObserver(s, null, Math.Max(0, Stopwatch.GetTimestamp() - entered));
            return -token;
        }
        int depth = s.depth++;
        var c = s.scopes[depth];
        c.depth = depth; c.parentToken = depth == 0 ? 0 : s.scopes[depth - 1].token;
        c.token = token; c.inputMap = inputMap; c.worldMap = worldMap; c.x = x; c.y = y; c.radar = radar;
        c.stage = ColdTrace.ActiveStage; c.frame = ColdTrace.ActiveFrame; c.frameStart = ColdTrace.FrameStarted;
        c.rootParts = c.observer = 0;
        Array.Clear(c.counts); Array.Clear(c.total); Array.Clear(c.self); Array.Clear(c.peaks);
        c.began = Stopwatch.GetTimestamp();
        AddObserver(s, c, Math.Max(0, c.began - entered));
        return token;
    }
    // The patcher passes Index from the Map local already initialized by the
    // original method. It neither evaluates World.Map early nor calls it twice.
    public static void SetWorldMap(long token, int map)
    {
        if (!ColdTrace.Enabled || token <= 0 || state is not { depth: > 0, overflowDepth: 0 } s) return;
        var c = s.scopes[s.depth - 1];
        if (c.token != token) return;
        long entered = Stopwatch.GetTimestamp(); c.worldMap = map;
        AddObserver(s, c, Math.Max(0, Stopwatch.GetTimestamp() - entered));
    }
    public static long BeginPart(int operation)
    {
        if (!ColdTrace.Enabled || (uint)operation >= ResourceOperations.ChunkParts.Length ||
            state is not { depth: > 0, overflowDepth: 0 } s) return 0;
        long entered = Stopwatch.GetTimestamp(), token = ++s.serial;
        if (s.partDepth == PartCapacity || s.partOverflowDepth != 0)
        {
            s.partOverflowDepth++; s.partOverflow++;
            AddObserver(s, s.scopes[s.depth - 1], Math.Max(0, Stopwatch.GetTimestamp() - entered));
            return -token;
        }
        int owner = s.depth - 1, depth = s.partDepth++;
        var c = s.scopes[owner];
        ref var p = ref s.parts[depth];
        p.token = token; p.operation = operation; p.owner = owner; p.ownerToken = c.token; p.children = 0;
        p.root = depth == 0 || s.parts[depth - 1].ownerToken != c.token;
        p.began = Stopwatch.GetTimestamp();
        AddObserver(s, c, Math.Max(0, p.began - entered));
        return token;
    }
    public static void EndPart(int operation, long token)
    {
        if (!ColdTrace.Enabled || token == 0 || state is not { } s) return;
        long entered = Stopwatch.GetTimestamp();
        if (token < 0)
        {
            if (s.partOverflowDepth > 0) s.partOverflowDepth--;
            AddObserver(s, s.depth > 0 && s.overflowDepth == 0 ? s.scopes[s.depth - 1] : null,
                Math.Max(0, Stopwatch.GetTimestamp() - entered));
            return;
        }
        int depth = s.partDepth - 1;
        if (depth < 0 || s.partOverflowDepth != 0) return;
        ref var p = ref s.parts[depth];
        if (p.token != token || p.operation != operation) return;
        var c = s.scopes[p.owner];
        if (c.token != p.ownerToken) return;
        long elapsed = Math.Max(0, entered - p.began), own = Math.Max(0, elapsed - p.children);
        s.partDepth = depth;
        c.counts[operation]++; c.total[operation] += elapsed; c.self[operation] += own; c.peaks[operation] = Math.Max(c.peaks[operation], elapsed);
        s.counts[operation]++; s.total[operation] += elapsed; s.self[operation] += own; s.peaks[operation] = Math.Max(s.peaks[operation], elapsed);
        if (p.root) c.rootParts += elapsed;
        if (depth > 0) s.parts[depth - 1].children += elapsed;
        AddObserver(s, c, Math.Max(0, Stopwatch.GetTimestamp() - entered));
    }
    public static void End(long token)
    {
        if (!ColdTrace.Enabled || token == 0 || state is not { } s) return;
        long entered = Stopwatch.GetTimestamp();
        if (token < 0)
        {
            if (s.overflowDepth > 0) s.overflowDepth--;
            AddObserver(s, null, Math.Max(0, Stopwatch.GetTimestamp() - entered));
            return;
        }
        int depth = s.depth - 1;
        if (depth < 0 || s.overflowDepth != 0) return;
        var c = s.scopes[depth];
        if (c.token != token) return;
        long elapsed = Math.Max(0, entered - c.began);
        s.depth = depth; s.calls++; s.wall += elapsed; s.peak = Math.Max(s.peak, elapsed);
        Record r = null;
        if (elapsed >= Stopwatch.Frequency / 20)
        {
            s.slowCalls++;
            if (s.written + s.pending < Limit)
            {
                r = s.records[s.pending++];
                r.token = c.token; r.parentToken = c.parentToken; r.depth = c.depth;
                r.inputMap = c.inputMap; r.worldMap = c.worldMap; r.x = c.x; r.y = c.y; r.radar = c.radar;
                r.frame = c.frame; r.frameStart = c.frameStart; r.stage = c.stage; r.began = c.began; r.wall = elapsed; r.rootParts = c.rootParts;
                Array.Copy(c.counts, r.counts, c.counts.Length); Array.Copy(c.total, r.total, c.total.Length);
                Array.Copy(c.self, r.self, c.self.Length); Array.Copy(c.peaks, r.peaks, c.peaks.Length);
            }
            else s.suppressed++;
        }
        AddObserver(s, c, Math.Max(0, Stopwatch.GetTimestamp() - entered));
        if (r != null) r.observer = c.observer;
        if (depth == 0 && !ResourceTrace.HasOpenScope) FlushPending();
    }
    // Output is deferred until the existing ResourceTrace root's finally has
    // finished, so child records and lock timing never print per inner call.
    internal static void FlushPending()
    {
        if (ResourceTrace.HasOpenScope) return;
        if (state is not { depth: 0, overflowDepth: 0 } s) return;
        if (s.pending == 0 && (s.calls == 0 || s.nextReport == 0 || Stopwatch.GetTimestamp() < s.nextReport)) return;
        long entered = Stopwatch.GetTimestamp();
        for (int i = 0; i < s.pending; i++)
        {
            var r = s.records[i];
            var line = new StringBuilder("CHUNK_LOAD utc=").Append(Utc()).Append(" thread=").Append(Environment.CurrentManagedThreadId)
                .Append(" frame=").Append(r.frame).Append(" stage=").Append(r.stage < 0 ? "none" : ColdTrace.Stages[r.stage])
                .Append(" chunk_id=").Append(r.token).Append(" parent_chunk_id=").Append(r.parentToken).Append(" depth=").Append(r.depth)
                .Append(" input_map=").Append(r.inputMap).Append(" world_map=").Append(r.worldMap).Append(" chunk_x=").Append(r.x).Append(" chunk_y=").Append(r.y)
                .Append(" radar=").Append(r.radar ? "true" : "false").Append(" wall_ms=").Append(Ms(r.wall))
                .Append(" parts_root_ms=").Append(Ms(r.rootParts)).Append(" unassigned_ms=").Append(Ms(Math.Max(0, r.wall - r.rootParts)))
                .Append(" scope_observer_overhead_ms=").Append(Ms(r.observer)).Append(" cpu_ms=unavailable cpu_unavailable_reason=observer_overhead")
                .Append(" mapblock_coverage=get_tile_z_initial_unassigned self_excludes=instrumented_chunk_parts")
                .Append(" end_to_log_ms=").Append(Ms(Math.Max(0, Stopwatch.GetTimestamp() - r.began - r.wall)))
                .Append(" start_offset_ms=").Append(r.frame == 0 || r.frameStart == 0 ? "unavailable" : Ms(r.began - r.frameStart));
            AppendParts(line, r.counts, r.total, r.self, r.peaks); Write(line.ToString()); s.written++;
        }
        s.pending = 0;
        long now = Stopwatch.GetTimestamp();
        AddObserver(s, null, Math.Max(0, now - entered));
        // Both slow records and window output wait for the original resource
        // root's cleanup. Never format or write from a high-frequency part hook
        // or from Chunk.Load's entry while a caller may hold an original lock.
        if (s.calls != 0 && s.nextReport != 0 && now >= s.nextReport)
        {
            Report(s, now);
            AddObserver(s, null, Math.Max(0, Stopwatch.GetTimestamp() - now));
        }
    }
    internal static void NewFrame() { if (state is { } s) s.frameObserver = 0; }
    internal static void AppendFrame(StringBuilder line)
    {
        if (state is { } s) line.Append(" chunk_trace_overhead_ms=").Append(Ms(s.frameObserver));
    }
    static void AddObserver(State s, Scope c, long elapsed)
    {
        s.observer += elapsed; s.frameObserver += elapsed;
        if (c != null) c.observer += elapsed;
    }
    static void Report(State s, long now)
    {
        var line = new StringBuilder("CHUNK_WINDOW utc=").Append(Utc()).Append(" thread=").Append(Environment.CurrentManagedThreadId)
            .Append(" window_ms=").Append(Ms(Math.Max(0, now - s.windowStarted))).Append(" calls=").Append(s.calls).Append(" inclusive_ms=").Append(Ms(s.wall))
            .Append(" max_ms=").Append(Ms(s.peak)).Append(" slow_calls=").Append(s.slowCalls);
        AppendParts(line, s.counts, s.total, s.self, s.peaks); Write(line.ToString());
        Write("CHUNK_LIMITS utc=" + Utc() + " thread=" + Environment.CurrentManagedThreadId + " window_ms=" + Ms(Math.Max(0, now - s.windowStarted)) +
            " window_observer_overhead_ms=" + Ms(s.observer) + " slow_suppressed=" + s.suppressed + " depth_overflow=" + s.overflow + " part_depth_overflow=" + s.partOverflow);
        Array.Clear(s.counts); Array.Clear(s.total); Array.Clear(s.self); Array.Clear(s.peaks);
        s.calls = s.wall = s.peak = s.slowCalls = s.observer = s.suppressed = s.overflow = s.partOverflow = 0; s.written = 0;
        s.windowStarted = now; s.nextReport = now + 5 * Stopwatch.Frequency;
    }
    static void AppendParts(StringBuilder line, long[] counts, long[] total, long[] self, long[] peaks)
    {
        for (int i = 0; i < counts.Length; i++)
            line.Append(' ').Append(ResourceOperations.ChunkParts[i]).Append("_calls=").Append(counts[i])
                .Append(' ').Append(ResourceOperations.ChunkParts[i]).Append("_ms=").Append(Ms(total[i]))
                .Append(' ').Append(ResourceOperations.ChunkParts[i]).Append("_self_ms=").Append(Ms(self[i]))
                .Append(' ').Append(ResourceOperations.ChunkParts[i]).Append("_max_ms=").Append(Ms(peaks[i]));
    }
    static string Utc() => DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture);
    static string Ms(long ticks) => (ticks * 1000.0 / Stopwatch.Frequency).ToString("F3", CultureInfo.InvariantCulture);
    static void Write(string text) { try { Console.Error.WriteLine(text); } catch { } }
}
