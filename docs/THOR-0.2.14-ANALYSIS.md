# Thor 0.2.14 telemetry analysis

## Input and scope

Analyzed logs-5357802737288757568.zip from the AYN Thor, exported after the 2026-10-02 23:37:59 UTC client launch (18:37:59 America/Chicago). The app reports 0.2.14, TazUO 5.2.0, Wine 10.13 ARM64EC/FEX-2510, Turnip, Native Surface, changed-region delivery, 60 FPS and a 1098x720 world within the 1280x720 canvas. Smooth world loading/revision 2 boundaries, atlas batching revision 1 and music caching are active; managed diagnostics and render trace are off.

The archive includes historical launches. Analysis uses the current client-wine/client-health logs and timestamp-filters both Android presentation files to the current launch. There are no supplied route/action timestamps; later smooth windows cannot be definitively labeled as retracing or interior re-entry.

## Findings

- Across the current session, atlas summaries report 6,888 logical sprite requests, 6,614 native uploads and 274 merges: about 4.0% fewer upload calls overall. This is measured device upload reduction, not proof of a proportional frame-time improvement.
- After the initial-entry windows (using frame summaries after 23:38:50 UTC), atlas flush maxima stay below 0.7 ms. The aligned atlas summary interval contains approximately 2.9% fewer upload calls. Staging and flush totals are small compared with the longest graphics-boundary stalls.
- One early atlas flush reaches 737.765 ms at 23:38:44.399 UTC; the next five-second atlas window spends 27.282 ms staging. These occur around startup/world entry and should not be presented as recurring exploration costs.
- After entry, FNA EndDraw exceeds 100 ms in 15 measurement windows. It peaks at 1,365.524 ms (summary 23:39:02.759 UTC) and 1,653.006 ms (23:41:08.927 UTC). The latter window has Update 172.579 ms, Draw 5.243 ms and a 172.363 ms registered handler for packet 20.
- A separate window at 23:40:37.794 UTC has Update 121.190 ms, EndDraw 151.583 ms and one generation-2 collection. Collection counts alone cannot attribute either interval to GC.
- Initial entry includes a 4,345.509 ms update gap, 2,141.204 ms Draw and 485.166 ms FillGameObjectList. The preceding startup/entry window has Update 2,138.808 ms and a 1,767.468 ms handler for packet 55. Startup and steady exploration must be compared separately.
- Later active-world summaries from 23:42:03.952 through 23:45:04.067 UTC contain no Update/Draw/EndDraw maxima over 100 ms. Their median update gap is approximately 17 ms. An earlier one-second gap accompanies first use of WorldMapGump.LoadZones and ImageSharp loading; that association is not a measured loader duration. The final roughly 737 ms gap accompanies logout/profile saving and should not be counted as a terrain traversal stall.
- Android presentation posts 15,436 frames with one initial buffer configuration and no presentation fallback. Weighted costs are capture 0.628 ms, copy/conversion 0.277 ms, Surface lock 1.173 ms and Surface post 0.456 ms. Reported Android thermal status is 0 throughout. These are window averages, not tail-latency bounds. Request/receive time includes pacing and waiting for a frame and is not equivalent to copying cost.

## Remaining causes and evidence limits

| Possible cause | Current evidence and missing distinction |
| --- | --- |
| Synchronous texture/resource uploads | Batching is active and merges reduce calls. Flush cost is normally sub-millisecond after entry, with one large entry-time flush. Driver work caused by an earlier upload can complete later in EndDraw; low flush time does not exclude deferred upload-related stalls. Non-atlas uploads and texture allocation durations are not individually counted. |
| Sprite/art/static/map decode or first-access disk I/O | Early Draw/load/fill costs and a later WorldMap first-use gap are observable. There are no per-resource decode, file-read or map-block timings. |
| Managed allocations/GC during creation | Generation 0/1 collections recur; generation 2 collections occur in both slow and smooth windows. There are no allocated-byte or GC pause-duration measurements. |
| FNA/SDL/Vulkan shader or pipeline creation | Cold EndDraw stalls are compatible with this cause, but no shader/pipeline creation duration is recorded. |
| Turnip synchronization or command submission | EndDraw is the largest recurring measured boundary. It includes submission/presentation and possible waits; the logs do not distinguish CPU preparation, native submission and driver/fence waits. |
| Packet-driven object-creation bursts | Registered-handler timing identifies startup packet 55 and later packet 20 costs. Handler time does not isolate object allocation, art preparation or deferred graphics consequences. The 5 ms budget cannot interrupt a single handler. |
| Scene graph/world construction | Scene Update and FillGameObjectList separate some CPU work. Early fill is expensive; post-entry fill maxima are much smaller. Object construction outside these boundaries remains unseparated. |
| Interior/map-block loading | No interior entrance or block identity is marked. Whole GameScene.Load timing should not be treated as an individual interior/block load duration. |
| Wine/FEX translation/JIT or scheduling | All 51 current health snapshots are available, with process/thread CPU deltas, states and wait channels. Sampling is roughly every ten seconds and the Wine process's children are unavailable. PRoot ptrace stops, pipe reads and futex waits do not establish a JIT or scheduling bottleneck. No translator code-block compilation duration is measured. |
| Audio/music transitions | Music reaches 481.447 ms before gameplay; after entry the largest music switch is about 12 ms. Audio is not the dominant measured exploration boundary in this export. |
| Android presentation bridge | Geometry caching remains effective and average copy/post costs are low. Rare receiver waits cannot be excluded using averages, but these observations do not justify another presentation-bridge optimization. |

## Next performance decision

Retain batching and the working runtime/presentation/input/audio paths. The dominant recurring measured boundary is FNA EndDraw, with secondary packet-handler costs. These timings do not yet select a safe shader, driver or resource-loading optimization.

Before another performance change, split EndDraw's native submission/presentation timing from pipeline/resource creation and waits, while retaining the current summaries and adding bounded event correlation for long frames. Resource decode/read and handler object-creation timings are the next CPU distinctions if the graphics split does not account for the pauses. Prefer narrowly targeted counters over enabling broad managed/render tracing for the baseline.

Five-second window maxima are not an exact count of long frames; overlapping stage totals cannot be summed. Atlas and frame reports have separate window boundaries. This analysis supports selecting further measurement, not claiming that 0.2.14 eliminated first-visit stutters or that upload count alone explains the remaining waits.

## 0.2.15 scope

0.2.15 corrects the touch quick-menu and failure-message destination wording to "Back to Launcher Menu" and publishes this evidence. It introduces no new performance change or instrumentation. 0.2.14 remains intact as the tested release.
