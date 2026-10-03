using System.Diagnostics;
using System.Globalization;
using System.Text;

namespace Memento;

// Fixed, originating-thread state. Nested wall time is explicitly inclusive;
// self excludes instrumented resource children, not unobserved callees.
public static class ResourceTrace
{
    const int Capacity = 32, Limit = 8;
    [ThreadStatic] static State state;
    sealed class State
    {
        internal int depth, pending, written;
        internal long serial, nextReport, windowStarted, suppressed, overflow, overhead, frameRoots, frameWall, frameNative;
        internal readonly long[] tokens = new long[Capacity], began = new long[Capacity], children = new long[Capacity], native = new long[Capacity], allocated = new long[Capacity], cpu = new long[Capacity];
        internal readonly int[] operations = new int[Capacity], parents = new int[Capacity];
        internal readonly int[] stages = new int[Capacity];
        internal readonly long[] frames = new long[Capacity], frameStarts = new long[Capacity];
        internal readonly long[] counts = new long[ResourceOperations.Names.Length], total = new long[ResourceOperations.Names.Length], self = new long[ResourceOperations.Names.Length], peaks = new long[ResourceOperations.Names.Length], nativeTotal = new long[ResourceOperations.Names.Length];
        internal readonly Record[] records = new Record[Limit];
    }
    struct Record
    {
        internal int operation, parent, depth, stage;
        internal long frame, frameStart, start, wall, self, native, allocated, cpu;
    }
    public static long Begin(int operation)
    {
        if (!ColdTrace.Enabled || (uint)operation >= ResourceOperations.Names.Length) return 0;
        long entered = Stopwatch.GetTimestamp();
        var s = state ??= new State();
        if (s.depth == 0 && s.nextReport != 0 && entered >= s.nextReport) Report(s, entered);
        if (s.nextReport == 0) { s.windowStarted = entered; s.nextReport = entered + 5 * Stopwatch.Frequency; }
        if (s.depth == Capacity) { s.overflow++; return 0; }
        int depth = s.depth++;
        long token = ++s.serial;
        s.tokens[depth] = token; s.operations[depth] = operation;
        s.stages[depth] = ColdTrace.ActiveStage; s.frames[depth] = ColdTrace.ActiveFrame; s.frameStarts[depth] = ColdTrace.FrameStarted;
        s.parents[depth] = depth == 0 ? -1 : s.operations[depth - 1];
        s.children[depth] = s.native[depth] = 0;
        s.allocated[depth] = GC.GetAllocatedBytesForCurrentThread();
        // Thread CPU on Windows/Wine is quantized. Sample outermost scopes only
        // to avoid two kernel calls for every cached animation or created item.
        s.cpu[depth] = depth == 0 ? ColdTrace.ThreadCpu() : -1;
        s.began[depth] = Stopwatch.GetTimestamp();
        s.overhead += Math.Max(0, s.began[depth] - entered);
        return token;
    }
    public static void End(int operation, long token)
    {
        if (!ColdTrace.Enabled || token == 0 || state == null) return;
        long now = Stopwatch.GetTimestamp(); var s = state;
        int depth = s.depth - 1;
        if (depth < 0 || s.tokens[depth] != token || s.operations[depth] != operation) return;
        long wall = Math.Max(0, now - s.began[depth]), own = Math.Max(0, wall - s.children[depth]);
        long allocated = Math.Max(0, GC.GetAllocatedBytesForCurrentThread() - s.allocated[depth]);
        long cpu = depth == 0 ? ColdTrace.ThreadCpu() : -1;
        cpu = cpu >= 0 && s.cpu[depth] >= 0 ? Math.Max(0, cpu - s.cpu[depth]) : -1;
        s.depth = depth;
        s.counts[operation]++; s.total[operation] += wall; s.self[operation] += own;
        s.peaks[operation] = Math.Max(s.peaks[operation], wall); s.nativeTotal[operation] += s.native[depth];
        if (depth > 0) { s.children[depth - 1] += wall; s.native[depth - 1] += s.native[depth]; }
        else { s.frameRoots++; s.frameWall += wall; s.frameNative += s.native[depth]; }
        if (wall >= Stopwatch.Frequency / 20)
        {
            if (s.pending + s.written < Limit)
                s.records[s.pending++] = new Record { operation = operation, parent = s.parents[depth], depth = depth,
                    stage = s.stages[depth], frame = s.frames[depth], frameStart = s.frameStarts[depth], start = s.began[depth],
                    wall = wall, self = own, native = s.native[depth], allocated = allocated, cpu = cpu };
            else s.suppressed++;
        }
        // A lock-wait scope may end while the original lock is now held. Delay
        // stderr formatting/output until its surrounding original method has
        // executed all cleanup and the outermost observed scope has returned.
        if (depth == 0) Flush(s);
        s.overhead += Math.Max(0, Stopwatch.GetTimestamp() - now);
    }
    public static void EnterLock(object value, ref bool taken, int operation)
    {
        long token = Begin(operation);
        try { Monitor.Enter(value, ref taken); }
        finally { End(operation, token); }
    }
    internal static void Native(long elapsed)
    {
        if (state is { depth: > 0 } s) s.native[s.depth - 1] += elapsed;
    }
    internal static void NewFrame()
    {
        if (state is { } s) s.overhead = s.frameRoots = s.frameWall = s.frameNative = 0;
    }
    internal static void AppendFrame(StringBuilder line)
    {
        if (state is not { } s) return;
        line.Append(" resource_root_calls=").Append(s.frameRoots).Append(" resource_root_wall_ms=").Append(Ms(s.frameWall))
            .Append(" resource_root_fna_ms=").Append(Ms(s.frameNative)).Append(" resource_trace_overhead_ms=").Append(Ms(s.overhead));
    }
    static void Flush(State s)
    {
        for (int i = 0; i < s.pending; i++)
        {
            var r = s.records[i];
            Write("RESOURCE_CALL utc=" + Utc() + " thread=" + Environment.CurrentManagedThreadId + " frame=" + r.frame +
                " stage=" + (r.stage < 0 ? "none" : ColdTrace.Stages[r.stage]) + " op=" + ResourceOperations.Names[r.operation] +
                " parent=" + (r.parent < 0 ? "none" : ResourceOperations.Names[r.parent]) + " depth=" + r.depth +
                " wall_ms=" + Ms(r.wall) + " self_ms=" + Ms(r.self) + " nested_fna_ms=" + Ms(r.native) +
                " allocated_bytes=" + r.allocated + " cpu_ms=" + (r.cpu < 0 ? "unavailable" : (r.cpu / 1e6).ToString("F3", CultureInfo.InvariantCulture)) +
                " cpu_scope=" + (r.depth == 0 ? "outermost_thread" : "not_sampled_nested") +
                " end_to_log_ms=" + Ms(Math.Max(0, Stopwatch.GetTimestamp() - r.start - r.wall)) +
                " start_offset_ms=" + (r.frame == 0 || r.frameStart == 0 ? "unavailable" : Ms(r.start - r.frameStart)));
            s.written++;
        }
        s.pending = 0;
    }
    static void Report(State s, long now)
    {
        for (int i = 0; i < s.counts.Length; i++) if (s.counts[i] != 0)
            Write("RESOURCE_WINDOW utc=" + Utc() + " thread=" + Environment.CurrentManagedThreadId + " op=" + ResourceOperations.Names[i] +
                " window_ms=" + Ms(Math.Max(0, now - s.windowStarted)) + " calls=" + s.counts[i] + " inclusive_ms=" + Ms(s.total[i]) + " self_ms=" + Ms(s.self[i]) +
                " max_ms=" + Ms(s.peaks[i]) + " nested_fna_ms=" + Ms(s.nativeTotal[i]));
        Write("RESOURCE_LIMITS utc=" + Utc() + " thread=" + Environment.CurrentManagedThreadId + " window_ms=" + Ms(Math.Max(0, now - s.windowStarted)) + " slow_suppressed=" + s.suppressed + " depth_overflow=" + s.overflow);
        Array.Clear(s.counts); Array.Clear(s.total); Array.Clear(s.self); Array.Clear(s.peaks); Array.Clear(s.nativeTotal);
        s.written = 0; s.suppressed = s.overflow = 0; s.windowStarted = now; s.nextReport = now + 5 * Stopwatch.Frequency;
    }
    static string Utc() => DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture);
    static string Ms(long ticks) => (ticks * 1000.0 / Stopwatch.Frequency).ToString("F3", CultureInfo.InvariantCulture);
    static void Write(string text) { try { Console.Error.WriteLine(text); } catch { } }
}
