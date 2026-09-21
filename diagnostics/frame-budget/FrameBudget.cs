using System.Diagnostics;
using System.Globalization;

// Resolve the added reference without editing the imported client's deps.json.
internal static class StartupHook
{
    public static void Initialize() => Memento.FrameBudget.Announce();
}

namespace Memento
{
    // Main-thread boundaries only: no background worker, debugger, graphics
    // calls, stack walking, or per-packet logging. One summary per five seconds.
    public static class FrameBudget
    {
        public const int Update = 0, Network = 1, Scene = 2, Load = 3, Audio = 4, Fill = 5;
        public const int PacketLimit = 1000;
        static readonly long BudgetTicks = Math.Max(1, Stopwatch.Frequency / 200);
        [ThreadStatic] static State state;
        sealed class State
        {
            internal bool active;
            internal long deadline, packets, yields, backlog, lastUpdate, lastAudio, updateGap, audioGap, nextReport;
            internal int consumed, depth;
            internal readonly long[] calls = new long[6], total = new long[6], max = new long[6];
            internal readonly int[] gc = { GC.CollectionCount(0), GC.CollectionCount(1), GC.CollectionCount(2) };
        }
        static State Current => state ??= new State();
        public static void Announce() => Write("FRAME_BUDGET_ACTIVE revision=1 budget_ms=5 packet_limit=1000");
        public static long BeginNetwork()
        {
            var s = Current; long now = Stopwatch.GetTimestamp();
            if (s.depth++ == 0) { s.active = true; s.deadline = now + BudgetTicks; s.consumed = 0; }
            return now;
        }
        public static bool More()
        {
            var s = Current;
            return !s.active || (s.consumed < PacketLimit && Stopwatch.GetTimestamp() < s.deadline);
        }
        public static bool CanParse(bool network, int bufferedBytes)
        {
            if (!network || !Current.active) return true;
            var s = Current; s.backlog = Math.Max(s.backlog, bufferedBytes);
            bool more = More(); if (!more && bufferedBytes > 0) s.yields++;
            return more;
        }
        public static void Consumed(bool network)
        {
            if (network && Current.active) { Current.consumed++; Current.packets++; }
        }
        public static void EndNetwork(long began)
        {
            var s = Current; if (--s.depth == 0) s.active = false; End(Network, began);
        }
        public static long Begin(int stage)
        {
            var s = Current; long now = Stopwatch.GetTimestamp();
            if (stage == Update) { if (s.lastUpdate != 0) s.updateGap = Math.Max(s.updateGap, now - s.lastUpdate); s.lastUpdate = now; }
            if (stage == Audio) { if (s.lastAudio != 0) s.audioGap = Math.Max(s.audioGap, now - s.lastAudio); s.lastAudio = now; }
            return now;
        }
        public static void End(int stage, long began)
        {
            var s = Current; long now = Stopwatch.GetTimestamp(), elapsed = Math.Max(0, now - began);
            s.calls[stage]++; s.total[stage] += elapsed; s.max[stage] = Math.Max(s.max[stage], elapsed);
            if (stage != Update) return;
            if (s.nextReport == 0) { s.nextReport = now + 5 * Stopwatch.Frequency; return; }
            if (now < s.nextReport) return;
            s.nextReport = now + 5 * Stopwatch.Frequency;
            try
            {
                string line = "FRAME_BUDGET utc=" + DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture) +
                    " thread=" + Environment.CurrentManagedThreadId + " packets=" + s.packets + " budget_yields=" + s.yields +
                    " backlog_bytes_max=" + s.backlog + " update_gap_ms=" + Ms(s.updateGap) + " audio_update_gap_ms=" + Ms(s.audioGap);
                string[] names = { "update", "network", "scene", "load", "audio", "fill" };
                for (int i = 0; i < names.Length; i++)
                    line += " " + names[i] + "_calls=" + s.calls[i] + " " + names[i] + "_max_ms=" + Ms(s.max[i]) + " " + names[i] + "_total_ms=" + Ms(s.total[i]);
                for (int i = 0; i < 3; i++) { int count = GC.CollectionCount(i); line += " gc" + i + "=" + (count - s.gc[i]); s.gc[i] = count; }
                Write(line);
            }
            catch { } // Optional reporting must not alter game behavior.
            Array.Clear(s.calls); Array.Clear(s.total); Array.Clear(s.max);
            s.packets = s.yields = s.backlog = s.updateGap = s.audioGap = 0;
        }
        static string Ms(long ticks) => (ticks * 1000.0 / Stopwatch.Frequency).ToString("F3", CultureInfo.InvariantCulture);
        static void Write(string text) { try { Console.Error.WriteLine(text); } catch { } }
    }
}
