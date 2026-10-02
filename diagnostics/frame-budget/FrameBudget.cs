using System.Diagnostics;
using System.Globalization;

// Resolve the added reference without editing the imported client's deps.json.
internal static class StartupHook
{
    public static void Initialize() => Memento.FrameBudget.Announce();
}

namespace Memento
{
    public struct PacketScope
    {
        internal long began;
        internal int id;
        internal bool network, valid;
    }

    // Main-thread boundaries only: no background worker, debugger, graphics
    // calls, stack walking, or per-packet logging. One summary per five seconds.
    public static class FrameBudget
    {
        public const int Update = 0, Network = 1, Scene = 2, Load = 3, Audio = 4, Fill = 5,
            Draw = 6, EndDraw = 7, Music = 8;
        public const int PacketLimit = 1000;
        static readonly long BudgetTicks = Math.Max(1, Stopwatch.Frequency / 200);
        static readonly string[] StageNames = { "update", "network", "scene", "load", "audio", "fill", "draw", "enddraw", "music" };
        [ThreadStatic] static State state;
        sealed class State
        {
            internal bool active;
            internal long deadline, packets, yields, backlog, lastUpdate, lastAudio, updateGap, audioGap, nextReport;
            internal int consumed, depth;
            internal readonly long[] calls = new long[StageNames.Length], total = new long[StageNames.Length], max = new long[StageNames.Length];
            internal long packetCalls, packetMax, networkPacketCalls, networkPacketMax, pluginPacketCalls, pluginPacketMax;
            internal int packetId = -1, networkPacketId = -1, pluginPacketId = -1;
            internal bool packetNetwork;
            internal readonly int[] gc = { GC.CollectionCount(0), GC.CollectionCount(1), GC.CollectionCount(2) };
        }
        static State Current => state ??= new State();
        public static void Announce() => Write("FRAME_BUDGET_ACTIVE revision=2 budget_ms=5 packet_limit=1000 load_boundaries=true");
        // The parser supplies the actual queue origin. Plugin packets can be
        // dispatched inside a network scope, so scope depth cannot identify it.
        // Retain only the ID and timing, never packet bytes or a handler object.
        public static PacketScope BeginPacket(ReadOnlySpan<byte> packet, bool network)
            => packet.IsEmpty ? default : new PacketScope {
                began = Stopwatch.GetTimestamp(), id = packet[0], network = network, valid = true
            };
        public static void EndPacket(PacketScope scope)
        {
            if (!scope.valid) return;
            var s = Current; long elapsed = Math.Max(0, Stopwatch.GetTimestamp() - scope.began);
            s.packetCalls++;
            if (s.packetId < 0 || elapsed > s.packetMax) {
                s.packetMax = elapsed; s.packetId = scope.id; s.packetNetwork = scope.network;
            }
            if (scope.network) {
                s.networkPacketCalls++;
                if (s.networkPacketId < 0 || elapsed > s.networkPacketMax) {
                    s.networkPacketMax = elapsed; s.networkPacketId = scope.id;
                }
            } else {
                s.pluginPacketCalls++;
                if (s.pluginPacketId < 0 || elapsed > s.pluginPacketMax) {
                    s.pluginPacketMax = elapsed; s.pluginPacketId = scope.id;
                }
            }
        }
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
                for (int i = 0; i < StageNames.Length; i++)
                    line += " " + StageNames[i] + "_calls=" + s.calls[i] + " " + StageNames[i] + "_max_ms=" + Ms(s.max[i]) + " " + StageNames[i] + "_total_ms=" + Ms(s.total[i]);
                line += " packet_calls=" + s.packetCalls + " packet_max_ms=" + Ms(s.packetMax) +
                    " packet_id=" + Id(s.packetId) + " packet_network=" + (s.packetNetwork ? "true" : "false") +
                    " packet_network_calls=" + s.networkPacketCalls + " packet_network_max_ms=" + Ms(s.networkPacketMax) +
                    " packet_network_id=" + Id(s.networkPacketId) + " packet_plugin_calls=" + s.pluginPacketCalls +
                    " packet_plugin_max_ms=" + Ms(s.pluginPacketMax) + " packet_plugin_id=" + Id(s.pluginPacketId);
                for (int i = 0; i < 3; i++) { int count = GC.CollectionCount(i); line += " gc" + i + "=" + (count - s.gc[i]); s.gc[i] = count; }
                Write(line);
            }
            catch { } // Optional reporting must not alter game behavior.
            Array.Clear(s.calls); Array.Clear(s.total); Array.Clear(s.max);
            s.packets = s.yields = s.backlog = s.updateGap = s.audioGap = 0;
            s.packetCalls = s.packetMax = s.networkPacketCalls = s.networkPacketMax = s.pluginPacketCalls = s.pluginPacketMax = 0;
            s.packetId = s.networkPacketId = s.pluginPacketId = -1; s.packetNetwork = false;
        }
        static string Id(int id) => id < 0 ? "none" : id.ToString("X2", CultureInfo.InvariantCulture);
        static string Ms(long ticks) => (ticks * 1000.0 / Stopwatch.Frequency).ToString("F3", CultureInfo.InvariantCulture);
        static void Write(string text) { try { Console.Error.WriteLine(text); } catch { } }
    }
}
