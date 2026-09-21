# 0.1.13 world-entry freeze — 2026-09-21

Input: `logs-177119497344736850.zip`, SHA-256
`6e31ee927e1fcab2c4ad4f35e4e8e32a82511dde881daa1fc1fd1a4239ebf402`.
The screenshot shows the world and paperdoll, partly transparent scenery, and a colored boat edge. The user reports a freeze while objects were drawing. The screenshot alone cannot locate the blocked operation.

## Evidence

The attempt began at **01:03:09 UTC**, launcher PID 26538. Status identifies Recovery 0.1.13, Turnip/Vulkan, Native Surface, 1280x720 with gump space, SDL fixes and render tracing enabled, detailed diagnostics and memory compatibility disabled. Compatibility JSON and Box64's actual startup output both show `BOX64_DYNAREC_CALLRET=0`. Wine logs `RENDER_TRACE_ACTIVE revision=1 boundary_probes_only`.

- Assets finished at 01:05:29. Connection at 01:05:59; player creation at 01:06:18.
- 4096x4096 texture allocations at 01:06:31–32; 1280x720 screen target at 01:06:32; 2048x2048 allocations at 01:06:34–35. Wine logging then stops.
- Main-thread CPU increased by only 25 ticks during the sample ending 01:06:46. Every sample from 01:06:56 to 01:09:47 shows zero additional main-thread CPU and `pipe_read`. Other threads continue running.
- RSS remains 814.35 MiB from 01:06:46 onward. The client and server are still alive at export. There is no current process exit, fatal exception or OOM record.
- The native display bridge continues servicing requests, predominantly reporting unchanged frames. Thermal status is 0 and power saving is off.
- No `RENDER_ENUMERATOR_FAILURE` or `RENDER_WRITE_DURING_READ` record appears. The crash files in the export are from prior runs.

This establishes a client-side stall during early world play, rather than a dead display bridge. `pipe_read` identifies a Linux wait primitive, not the Wine/.NET/graphics function responsible. Fixed RSS does not prove the absence of every memory problem. The return workaround did not resolve this run's freeze.

## Diagnostic gap and 0.1.14

Revision 1 constructs a `StackTrace` before writing its overlapping-writer report and formats an exception before writing its enumerator report. A failure or stall in those operations can conceal the evidence. `System.Diagnostics.StackTrace.dll` loaded near world entry, but later texture logs appeared; **this does not prove the tracer caused the freeze**.

Revision 2 removes those stack walks and exception formatting. It writes a basic failure marker before reflection, retains the original exception and rethrow behavior, and publishes bounded render-list progress independently of console logging.

The launcher creates a fresh 1056-byte file in the private session directory for each traced launch. The helper maps it once. Up to 16 managed render threads each own a 64-byte record, updated with memory writes and sequence barriers. There are no periodic managed callbacks, per-frame disk/console writes, debugger attachments, graphics calls, or added rendering locks. Python reads stable records every 10 seconds into the existing bounded `client-health.log`. Missing, malformed or unavailable records do not abort the client or disable process health sampling. Old mappings cannot overwrite the new attempt's inode.

The record reports entry to FillGameObjectList, entry to the DrawRenderList probe, execution inside DrawRenderList, failure handling, or exit from DrawRenderList. Counters and per-thread time since the last observed change distinguish frozen boundaries from continued execution. Failure/overlap flags persist after finally executes. An exit count includes exceptional exits and is not a count of successful frames. A `draw_list_exit` boundary cannot distinguish later UI rendering, presentation, or update work; these are coarse boundaries, not a native stack trace. Managed thread IDs differ from Linux thread IDs.

The exact imported TazUO patch, FNA, SDL, driver, Box64, Wine, .NET settings and 1098x720/1280x720 layout remain unchanged. This is a **diagnostic improvement, not a confirmed fix for the device freeze**.

## Verification and next capture

The injected-IL fixture checks normal rendering, same/other-thread mutation, untracked mutation, unchanged versions, version overflow, original exception identity, finally cleanup and disabled tracing. An exception whose formatting/stack properties throw verifies that diagnostics do not access them. A deliberately blocked draw verifies that the independent observer sees a frozen `drawing_list` record, and that release resumes normally. Shared records retain failures and separate different render threads. These tests run under Wine 10 and self-contained Windows .NET 10.0.8 in CI; host checks are not a Thor reproduction.

For the next device run, retain the settings above. After a freeze, wait about 30 seconds and export from Journal before stopping or relaunching the client. This should preserve several independent process and render-boundary samples without another ten-minute wait.
