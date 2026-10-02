using System.Diagnostics;
using System.Globalization;
using System.Reflection;
using Memento;

// Exercise the deployed helper without initializing game assets or a display.
// Force only the report deadline; retain the real clock, counters and output.
const BindingFlags PrivateStatic = BindingFlags.Static | BindingFlags.NonPublic;
const BindingFlags Fields = BindingFlags.Instance | BindingFlags.NonPublic;
var stateField = typeof(FrameBudget).GetField("state", PrivateStatic)!;
stateField.SetValue(null, null);
var originalError = Console.Error;
var output = new StringWriter(CultureInfo.InvariantCulture);
Console.SetError(output);

void Check(bool ok, string why) { if (!ok) throw new Exception(why); }
void Stage(int stage, int delay = 0) {
    long began = FrameBudget.Begin(stage);
    try { if (delay > 0) Thread.Sleep(delay); }
    finally { FrameBudget.End(stage, began); }
}
void Packet(byte id, bool network, long elapsedMilliseconds = 0) {
    var scope = FrameBudget.BeginPacket(new byte[] { id }, network);
    if (elapsedMilliseconds > 0) {
        // Control only this fixture's start timestamp, so scheduler jitter
        // cannot choose the worst packet. Retain the production ID, origin,
        // clock at completion, aggregation and output paths.
        object boxed = scope;
        typeof(PacketScope).GetField("began", Fields)!.SetValue(boxed,
            Stopwatch.GetTimestamp() - elapsedMilliseconds * Stopwatch.Frequency / 1000);
        scope = (PacketScope)boxed;
    }
    FrameBudget.EndPacket(scope);
}
Dictionary<string, string> Report() {
    // An Update establishes this thread's State. Reports still originate only
    // at Update completion, just as they do inside the patched client.
    long began = FrameBudget.Begin(FrameBudget.Update);
    var state = stateField.GetValue(null)!;
    state.GetType().GetField("nextReport", Fields)!.SetValue(state, 1L);
    FrameBudget.End(FrameBudget.Update, began);
    string line = output.ToString().Split('\n').Last(l => l.StartsWith("FRAME_BUDGET utc=", StringComparison.Ordinal));
    return line.Split(' ', StringSplitOptions.RemoveEmptyEntries).Skip(1)
        .Select(x => x.Split('=', 2)).ToDictionary(x => x[0], x => x[1].TrimEnd('\r'));
}
double Number(Dictionary<string, string> line, string key) => double.Parse(line[key], CultureInfo.InvariantCulture);

try {
    FrameBudget.Announce();
    Check(output.ToString().Contains("revision=2") && output.ToString().Contains("load_boundaries=true"), "Wrong helper revision");
    Stage(FrameBudget.Draw, 2); Stage(FrameBudget.EndDraw, 2); Stage(FrameBudget.Music, 2);

    long network = FrameBudget.BeginNetwork();
    try {
        Packet(0x6D, true, 60000);
        Packet(0xD6, false, 3600000); // Plugins can dispatch inside a network scope.
        Packet(0xF3, true, 1);
        var failed = FrameBudget.BeginPacket(new byte[] { 0x78 }, true);
        var expected = new InvalidOperationException("fixture packet handler");
        try {
            try { throw expected; }
            finally { FrameBudget.EndPacket(failed); }
        } catch (InvalidOperationException error) {
            Check(ReferenceEquals(error, expected), "Packet timing replaced the handler exception");
        }
    } finally { FrameBudget.EndNetwork(network); }
    Packet(0xFE, false, 1);
    FrameBudget.EndPacket(FrameBudget.BeginPacket(ReadOnlySpan<byte>.Empty, true));
    Thread.Sleep(8);
    Check(FrameBudget.More(), "Packet exception left the network budget active");

    var first = Report();
    Check(first["packet_calls"] == "5" && first["packet_network_calls"] == "3" && first["packet_plugin_calls"] == "2", "Packet queue origin or empty packet handling changed");
    Check(first["packet_id"] == "D6" && first["packet_network"] == "false", "Slowest packet was attributed to the active scope instead of its actual queue");
    Check(first["packet_network_id"] == "6D" && first["packet_plugin_id"] == "D6", "Queue-specific worst packet IDs were lost");
    Check(Number(first, "packet_max_ms") >= 3600000 && Number(first, "packet_network_max_ms") >= 60000, "Fixture handler duration was not retained");
    foreach (string name in new[] { "draw", "enddraw", "music" }) {
        Check(first[name + "_calls"] == "1" && Number(first, name + "_max_ms") > 0 && Number(first, name + "_total_ms") >= Number(first, name + "_max_ms"), "Missing distinct " + name + " duration");
    }
    Check(first["network_calls"] == "1" && first["packets"] == "0", "Handler diagnostics changed scheduling packet counters");

    var empty = Report();
    Check(empty["packet_calls"] == "0" && empty["packet_network_calls"] == "0" && empty["packet_plugin_calls"] == "0", "Packet summary counts leaked between windows");
    Check(empty["packet_id"] == "none" && empty["packet_network_id"] == "none" && empty["packet_plugin_id"] == "none" && empty["packet_network"] == "false", "Worst packet IDs leaked between windows");
    foreach (string name in new[] { "draw", "enddraw", "music" })
        Check(empty[name + "_calls"] == "0" && Number(empty, name + "_max_ms") == 0 && Number(empty, name + "_total_ms") == 0, "Stage data leaked between windows");

    byte[] packetBytes = { 0x54 };
    for (int i = 0; i < 100; i++) FrameBudget.EndPacket(FrameBudget.BeginPacket(packetBytes, true));
    Report();
    long before = GC.GetAllocatedBytesForCurrentThread();
    for (int i = 0; i < 10000; i++) FrameBudget.EndPacket(FrameBudget.BeginPacket(packetBytes, true));
    long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
    Check(allocated == 0, "Packet timing allocates during steady dispatch: " + allocated);
    var burst = Report();
    Check(burst["packet_calls"] == "10000" && burst["packet_id"] == "54", "Packet burst was truncated or sampled");

    var worker = Task.Run(() => {
        Stage(FrameBudget.Draw); Packet(0x20, true);
        return Report();
    }).GetAwaiter().GetResult();
    Check(worker["packet_calls"] == "1" && worker["packet_id"] == "20" && worker["draw_calls"] == "1", "Worker did not own a separate summary");
    var main = Report();
    Check(main["packet_calls"] == "0" && main["draw_calls"] == "0" && main["thread"] != worker["thread"], "Thread-local attribution leaked to the game thread");

    Console.SetError(new FailedWriter());
    Stage(FrameBudget.Music);
    long failedReport = FrameBudget.Begin(FrameBudget.Update);
    var failedState = stateField.GetValue(null)!;
    failedState.GetType().GetField("nextReport", Fields)!.SetValue(failedState, 1L);
    FrameBudget.End(FrameBudget.Update, failedReport);
    Console.SetError(output);
    Check(Report()["music_calls"] == "0", "Reporting failure prevented summary reset");
} finally { Console.SetError(originalError); }
Console.WriteLine("LOAD_TRACE_OK distinct_draw_enddraw_music=true network_plugin_origin=true worst_packet=true reset=true exception_cleanup=true thread_isolation=true allocation_free=true");

sealed class FailedWriter : TextWriter {
    public override System.Text.Encoding Encoding => System.Text.Encoding.UTF8;
    public override void WriteLine(string? value) => throw new IOException("fixture diagnostic output failure");
}
