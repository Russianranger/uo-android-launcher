using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text;

namespace Memento;

// Passive, opt-in observations. No extra graphics operations, workers, stack
// walks or packet payloads. Counters use fixed arrays on the originating thread.
public static class ColdTrace
{
    public static readonly bool Enabled = Environment.GetEnvironmentVariable("MEMENTO_COLD_TRACE") == "1";
    internal static readonly string[] Stages = { "update", "network", "scene", "load", "audio", "fill", "draw", "enddraw", "music" };
    internal static readonly int[] Thresholds = { 25, 50, 100, 250, 1000 };
    [ThreadStatic] static State state;
    [ThreadStatic] static int stageDepth;
    [ThreadStatic] static int[] stageStack;
    internal static long ActiveFrame => state?.frame ?? 0;
    internal static long FrameStarted => state?.began ?? 0;
    internal static int ActiveStage => stageDepth == 0 || stageDepth > stageStack.Length ? -1 : stageStack[stageDepth - 1];
    sealed class State
    {
        internal long frame, began, nextReport, allocated, cpu, endDrawCpuStart, endDrawCpu, frames, gapMax, bookkeeping;
        internal bool open;
        internal int longWritten, nativeWritten;
        internal long longSuppressed, nativeSuppressed, packetCalls, packetMax, nativeMax, nativeTotal, nativeCalls;
        internal int packetId = -1, nativeId = -1;
        internal bool packetNetwork;
        internal long atlasSprites, atlasUploads, atlasMerged, atlasStage, atlasFlush, atlasFlushCalls, atlasBytes;
        internal TimeSpan pause;
        internal readonly int[] gc = new int[3];
        internal readonly long[] stages = new long[9], nativeCounts = new long[GraphicsOperations.Names.Length], nativeTicks = new long[GraphicsOperations.Names.Length], nativePeaks = new long[GraphicsOperations.Names.Length];
        internal readonly long[] bins = new long[Thresholds.Length], updateBins = new long[Thresholds.Length], drawBins = new long[Thresholds.Length], endDrawBins = new long[Thresholds.Length];
    }
    static State Current => state ??= new State();
    public static void Announce()
    {
        if (Enabled) Write("COLD_TRACE_ACTIVE revision=2 long_frame_ms=50 max_long_records_per_5s=8 max_native_records_per_5s=8 max_resource_records_per_5s=8 resource_windows=deferred_until_next_root_scope resource_cpu_scope=outermost_thread resource_self_excludes=instrumented_resource_children frame_boundary=update_start cpu_scope=thread gc_pause_scope=process");
    }
    internal static void BeginStage(int stage, long now)
    {
        if (!Enabled) return;
        var s = Current;
        if (stage == FrameBudget.Update)
        {
            long cpu = ThreadCpu();
            long allocated = GC.GetAllocatedBytesForCurrentThread();
            TimeSpan pause = GC.GetTotalPauseDuration();
            if (s.open)
            {
                long gap = Math.Max(0, now - s.began); s.frames++; s.gapMax = Math.Max(s.gapMax, gap);
                Count(s.bins, gap); Count(s.updateBins, s.stages[FrameBudget.Update]);
                Count(s.drawBins, s.stages[FrameBudget.Draw]); Count(s.endDrawBins, s.stages[FrameBudget.EndDraw]);
                if (gap >= Stopwatch.Frequency / 20)
                {
                    if (s.longWritten < 8) { s.longWritten++; LongFrame(s, now, gap, cpu, allocated, pause); }
                    else s.longSuppressed++;
                }
            }
            if (s.nextReport == 0) s.nextReport = now + 5 * Stopwatch.Frequency;
            else if (now >= s.nextReport) { Summary(s); s.nextReport = now + 5 * Stopwatch.Frequency; }
            s.frame++; s.open = true; s.began = now; s.cpu = ThreadCpu(); s.allocated = GC.GetAllocatedBytesForCurrentThread(); s.pause = GC.GetTotalPauseDuration();
            for (int i = 0; i < 3; i++) s.gc[i] = GC.CollectionCount(i);
            Array.Clear(s.stages); s.endDrawCpu = 0;
            s.packetCalls = s.packetMax = s.nativeMax = s.nativeTotal = s.nativeCalls = 0;
            s.packetId = s.nativeId = -1; s.packetNetwork = false;
            s.atlasSprites = s.atlasUploads = s.atlasMerged = s.atlasStage = s.atlasFlush = s.atlasFlushCalls = s.atlasBytes = 0;
            s.bookkeeping = Math.Max(0, Stopwatch.GetTimestamp() - now);
            ResourceTrace.NewFrame();
        }
        if (stage == FrameBudget.EndDraw) s.endDrawCpuStart = ThreadCpu();
        stageStack ??= new int[16];
        if (stageDepth < stageStack.Length) stageStack[stageDepth] = stage;
        stageDepth++;
    }
    internal static void EndStage(int stage, long elapsed)
    {
        if (!Enabled) return;
        var s = Current; s.stages[stage] += elapsed;
        if (stageDepth > 0) stageDepth--;
        if (stage == FrameBudget.EndDraw)
        {
            long cpu = ThreadCpu();
            s.endDrawCpu = cpu >= 0 && s.endDrawCpuStart >= 0 ? s.endDrawCpu + Math.Max(0, cpu - s.endDrawCpuStart) : -1;
        }
    }
    internal static void Packet(int id, bool network, long elapsed)
    {
        if (!Enabled) return;
        var s = Current; s.packetCalls++;
        if (s.packetId < 0 || elapsed > s.packetMax) { s.packetId = id; s.packetNetwork = network; s.packetMax = elapsed; }
    }
    // Public only for the hash-checked FNA forwarding wrappers.
    public static long BeginNative(int operation) => Enabled ? Stopwatch.GetTimestamp() : 0;
    public static void EndNative(int operation, long began)
    {
        if (!Enabled || began == 0 || (uint)operation >= GraphicsOperations.Names.Length) return;
        long now = Stopwatch.GetTimestamp(), elapsed = Math.Max(0, now - began);
        var s = Current; s.nativeCounts[operation]++; s.nativeTicks[operation] += elapsed;
        ResourceTrace.Native(elapsed);
        s.nativePeaks[operation] = Math.Max(s.nativePeaks[operation], elapsed);
        s.nativeCalls++; s.nativeTotal += elapsed;
        if (s.nativeId < 0 || elapsed > s.nativeMax) { s.nativeId = operation; s.nativeMax = elapsed; }
        if (elapsed < Stopwatch.Frequency / 20) return;
        if (s.nativeWritten >= 8) { s.nativeSuppressed++; return; }
        s.nativeWritten++;
        Write("FNA_CALL utc=" + Utc() + " thread=" + Environment.CurrentManagedThreadId + " frame=" + s.frame +
            " op=" + GraphicsOperations.Names[operation] + " wall_ms=" + Ms(elapsed) + " start_offset_ms=" + Ms(began - s.began));
    }
    public static void Atlas(int sprites, int uploads, int merged, int bytes, long stagingTicks, long flushTicks, int flushes)
    {
        if (!Enabled) return;
        var s = Current; s.atlasSprites += sprites; s.atlasUploads += uploads; s.atlasMerged += merged;
        s.atlasBytes += bytes; s.atlasStage += stagingTicks; s.atlasFlush += flushTicks; s.atlasFlushCalls += flushes;
    }
    static void Count(long[] bins, long ticks)
    {
        for (int i = 0; i < Thresholds.Length; i++) if (ticks >= Stopwatch.Frequency * Thresholds[i] / 1000) bins[i]++;
    }
    static void LongFrame(State s, long now, long gap, long cpu, long allocated, TimeSpan pause)
    {
        try
        {
            var line = new StringBuilder("COLD_FRAME utc=").Append(Utc()).Append(" thread=").Append(Environment.CurrentManagedThreadId)
                .Append(" frame=").Append(s.frame).Append(" gap_ms=").Append(Ms(gap))
                .Append(" trace_bookkeeping_ms=").Append(Ms(s.bookkeeping))
                .Append(" thread_cpu_ms=").Append(cpu >= 0 && s.cpu >= 0 ? Ns(Math.Max(0, cpu - s.cpu)) : "unavailable")
                .Append(" enddraw_cpu_ms=").Append(s.endDrawCpu >= 0 ? Ns(s.endDrawCpu) : "unavailable")
                .Append(" allocated_bytes=").Append(Math.Max(0, allocated - s.allocated))
                .Append(" gc_pause_process_ms=").Append(Math.Max(0, (pause - s.pause).TotalMilliseconds).ToString("F3", CultureInfo.InvariantCulture));
            for (int i = 0; i < 3; i++) line.Append(" gc").Append(i).Append('=').Append(GC.CollectionCount(i) - s.gc[i]);
            for (int i = 0; i < Stages.Length; i++) line.Append(' ').Append(Stages[i]).Append("_ms=").Append(Ms(s.stages[i]));
            line.Append(" packet_calls=").Append(s.packetCalls).Append(" packet_max_ms=").Append(Ms(s.packetMax))
                .Append(" packet_id=").Append(s.packetId < 0 ? "none" : s.packetId.ToString("X2", CultureInfo.InvariantCulture))
                .Append(" packet_network=").Append(s.packetNetwork ? "true" : "false")
                .Append(" native_calls=").Append(s.nativeCalls).Append(" native_total_ms=").Append(Ms(s.nativeTotal))
                .Append(" native_max_ms=").Append(Ms(s.nativeMax)).Append(" native_op=").Append(s.nativeId < 0 ? "none" : GraphicsOperations.Names[s.nativeId])
                .Append(" atlas_sprites=").Append(s.atlasSprites).Append(" atlas_uploads=").Append(s.atlasUploads).Append(" atlas_merged=").Append(s.atlasMerged)
                .Append(" atlas_upload_bytes=").Append(s.atlasBytes).Append(" atlas_stage_ms=").Append(Ms(s.atlasStage))
                .Append(" atlas_flush_ms=").Append(Ms(s.atlasFlush)).Append(" atlas_flush_calls=").Append(s.atlasFlushCalls);
            ResourceTrace.AppendFrame(line);
            Write(line.ToString());
        }
        catch { }
    }
    static void Summary(State s)
    {
        try
        {
            var line = new StringBuilder("COLD_WINDOW utc=").Append(Utc()).Append(" thread=").Append(Environment.CurrentManagedThreadId)
                .Append(" frames=").Append(s.frames).Append(" gap_max_ms=").Append(Ms(s.gapMax))
                .Append(" long_records_suppressed=").Append(s.longSuppressed).Append(" native_records_suppressed=").Append(s.nativeSuppressed);
            for (int i = 0; i < Thresholds.Length; i++)
            {
                line.Append(" gap_ge_").Append(Thresholds[i]).Append("ms=").Append(s.bins[i]);
                line.Append(" update_ge_").Append(Thresholds[i]).Append("ms=").Append(s.updateBins[i]);
                line.Append(" draw_ge_").Append(Thresholds[i]).Append("ms=").Append(s.drawBins[i]);
                line.Append(" enddraw_ge_").Append(Thresholds[i]).Append("ms=").Append(s.endDrawBins[i]);
            }
            Write(line.ToString());
            for (int i = 0; i < s.nativeCounts.Length; i++) if (s.nativeCounts[i] != 0)
                Write("FNA_WINDOW utc=" + Utc() + " thread=" + Environment.CurrentManagedThreadId + " op=" + GraphicsOperations.Names[i] +
                    " calls=" + s.nativeCounts[i] + " total_ms=" + Ms(s.nativeTicks[i]) + " max_ms=" + Ms(s.nativePeaks[i]));
        }
        catch { }
        Array.Clear(s.bins); Array.Clear(s.updateBins); Array.Clear(s.drawBins); Array.Clear(s.endDrawBins);
        Array.Clear(s.nativeCounts); Array.Clear(s.nativeTicks); Array.Clear(s.nativePeaks);
        s.frames = s.gapMax = s.longSuppressed = s.nativeSuppressed = 0; s.longWritten = s.nativeWritten = 0;
    }
    static string Utc() => DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture);
    static string Ms(long ticks) => (ticks * 1000.0 / Stopwatch.Frequency).ToString("F3", CultureInfo.InvariantCulture);
    static string Ns(long ns) => (ns / 1e6).ToString("F3", CultureInfo.InvariantCulture);
    static void Write(string line) { try { Console.Error.WriteLine(line); } catch { } }
    static bool cpuUnavailable;
    [StructLayout(LayoutKind.Sequential)] struct Timespec { internal long seconds, nanos; }
    [DllImport("libc", EntryPoint = "clock_gettime")] static extern int Clock(int id, out Timespec value);
    [DllImport("kernel32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool GetThreadTimes(IntPtr thread, out long creation, out long exit, out long kernel, out long user);
    internal static long ThreadCpu()
    {
        if (cpuUnavailable) return -1;
        try
        {
            if (OperatingSystem.IsWindows()) return GetThreadTimes(new IntPtr(-2), out _, out _, out long kernel, out long user) ? (kernel + user) * 100 : -1;
            return Clock(3 /* Linux CLOCK_THREAD_CPUTIME_ID */, out var t) == 0 ? t.seconds * 1000000000 + t.nanos : -1;
        }
        catch { cpuUnavailable = true; return -1; }
    }
}
