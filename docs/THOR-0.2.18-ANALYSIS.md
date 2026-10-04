# Thor 0.2.18 marked cold-load trace

## Scope and startup recovery

Input: `logs-5198232172520749206.zip`, SHA-256 `62b1098186958d4fd35de86f570fe6923b5cae9acac3882ae9b67983695e6e7e`. Current launch: 2026-10-04 13:27:33 UTC (08:27:33 America/Chicago). The export records app 0.2.18 and final phase `stopped`. Original SDL 3.2.27 is active, with the optional update OFF. Revision-3 managed cold/resource timing and revision-2 native Vulkan tracing are active. Retained Wine 10.13 ARM64EC/FEX-2510, Turnip, atlas batching and Smooth world loading remain active.

The startup diagnostic regression is substantially recovered. File loading begins at 13:28:02, tiledata opens at 13:28:04 and closes at 13:28:14, and complete file loading reports **13,332 ms** at 13:28:15. The first completed Update frame is reported at 13:28:18.949947, **45.95 seconds after launch**. Subtracting its 146.865 ms reported gap places the first Update boundary at approximately **45.8 seconds after launch**; UTC reporting/query delays limit that reconstruction. The next completed frame at 13:28:19.197531 includes the first Draw. This supports the user's approximate one-minute startup report. The failed 0.2.17 run spent about 132 seconds on tiledata alone and had not reached its first Update when exported.

Two startup resource windows execute 67,466 primitive reads in ten seconds with 94.111 ms combined reported observer overhead. Health samples at 13:28:04/12 show only 304 additional process read syscalls and 31,762 bytes of `rchar`, versus 328,230 syscalls over the previous prolonged tiledata interval. These are different sampling spans, not a normalized benchmark, but the excessive per-read CPU-query pattern is absent. Startup still has separate login/world-loading stalls: a pre-marker window reports a 9,125.533 ms gap with seven suppressed long records. Startup recovery does not establish smooth world entry or removal of the original traversal problem.

Older launches in the ZIP are excluded from the following traversal analysis. Markers identify intended phases, not exact doorway or movement coordinates. Frame counts use completed `COLD_FRAME` UTC records; Update-start gaps are not an FPS measurement.

## Marked phases and suppression

| Phase | UTC start | Duration to next marker | Emitted gaps >=50 / >=100 ms | Suppressed long details | Largest measured gap |
| --- | --- | ---: | ---: | ---: | ---: |
| Outdoor first traversal | 13:28:56.886216 | 18.668 s | 24 / 15 | 5 | 461.082 ms in window histogram; 446.728 ms in emitted detail |
| Outdoor retrace | 13:29:15.554113 | 19.249 s | 0 / 0 | 0 | No gap >=50 ms |
| Interior first entry | 13:29:34.803462 | 29.884 s | 18 / 12 | 0 | 6,874.590 ms |
| Interior exit | 13:30:04.687444 | 6.619 s | 0 / 0 | 0 | No gap >=50 ms |
| Same interior re-entry | 13:30:11.306764 | 5.784 s | 0 / 0 | 0 | No gap >=50 ms |

Three complete windows wholly inside outdoor cold contain **29 gaps >=50 ms and 17 >=100 ms**, including the five suppressed details. The surrounding boundary windows add no further cold-phase long records. The largest cold gap is suppressed, so it cannot be attributed to a particular stage from its individual record. Three complete windows wholly inside outdoor warm contain zero gaps >=50 ms and peak at **40.090 ms**.

Four complete windows wholly inside interior cold contain 15 gaps >=50 ms and ten >=100 ms; the remaining three emitted cold long records lie in boundary windows. There are no suppressed long details in windows overlapping interior cold, exit or re-entry. Exit and re-entry each lack a complete five-second window wholly inside the marked phase, but their covering windows and individual records contain no gaps >=50 ms. This is a short re-entry observation, not an all-session guarantee. No FNA/native slow details or Vulkan slow records are suppressed in the marked traversal.

This reproduces the cold/warm distinction. Route durations and instrumentation differ from 0.2.16; these counts do not establish a controlled performance change between releases.

## Directly identified chunk stalls

The largest interior hitch is frame **4175**, reported at **13:29:47.763945 UTC**:

| Observation | Duration |
| --- | ---: |
| Update-start gap | 6,874.590 ms |
| Update / network processing | 6,844.996 / 6,751.596 ms |
| Worst packet handler, 0xF3 | 6,750.521 ms |
| `chunk_load`, inside network processing | 6,749.949 ms wall / 6,749.945 ms self |
| Draw / EndDraw | 7.064 / 13.880 ms |
| All observed FNA native calls | 15.074 ms |
| Atlas staging / flush | 0.218 / 0.215 ms |
| Process GC pause delta | 34.879 ms |
| Managed current-thread allocation | 463,984 bytes |
| Managed frame-thread CPU / EndDraw CPU | 180 / 10 ms |
| Resource observer / frame bookkeeping | 7.565 / 72.835 ms |

These inclusive/nested boundaries must not be added together. The named chunk boundary accounts for essentially the entire registered 0xF3 handler stall. The preceding frame, 4174 at 13:29:40.934808, has a 728.404 ms gap, packet 0x20 at 255.830 ms and a nested chunk load at 250.400 ms. Numerous background threads also report chunk loads lasting hundreds of milliseconds to several seconds around the same transition.

Outdoor frame **2530** at **13:29:05.311254** adds a separate rendering-side example: gap 446.728 ms, Draw 412.340 ms, `world_render_target` 405.668 ms, nested `world_render_list` 400.544 ms and `chunk_load` **385.558 ms**. The chunk self time is 385.551 ms with no nested FNA time. This directly locates most of that measured Draw stall in chunk loading, rather than texture uploading or EndDraw.

Other graphics tails remain: eight emitted outdoor and eight interior cold records have EndDraw >=50 ms, including later interior frames with no atlas uploads. The two chunk examples do not explain every cold long frame.

## Health correlation and competing causes

In the middle of the main chunk stall, health samples from **13:29:42 to 13:29:46** show main-thread scheduled CPU increasing by only **35.037 ms**, runqueue wait by **169.986 ms**, while process CPU increases by **3.73 seconds**. The main thread is sampled in `ptrace_stop` at each endpoint and the intervening sample. Physical-read bytes remain unchanged at 299,786,240 during these four seconds. This supports a blocked main thread while other client work proceeds; coarse samples do not distinguish a managed lock, Wine synchronization, PRoot dispatch or another blocked resource operation.

Samples wholly inside outdoor cold accumulate 32,296,960 physical-read bytes over 17.09 seconds, versus 3,461,120 bytes over 17.10 seconds of outdoor warm. Interior cold accumulates 14,303,232 bytes over 28.05 sampled seconds. These process-wide counters do not identify files or assign a duration to disk I/O. Current sampled client/FEX RSS peaks at 906.219 MiB.

| Candidate cause | Evidence and limit |
| --- | --- |
| Synchronous texture/resource uploads | The main interior stall has 15.074 ms total FNA work and 0.215 ms atlas flush. The outdoor chunk call has no nested FNA work. Uploads do not account for these two stalls; deferred GPU work can still contribute to other frames. |
| Sprite/art/static/map decoding or disk I/O | Chunk loading is directly identified in Draw and packet handling. Cold phase physical reads exceed warm reads, but the middle four seconds of the largest chunk stall add no physical reads. Exact decode/read/serialization work inside the chunk boundary still needs source-level interpretation. |
| Managed allocations / GC | The largest marked gap has 463,984 current-thread allocated bytes and 34.879 ms process GC pause. These do not explain 6.75 seconds of chunk work. |
| FNA/SDL/Vulkan shader or pipeline creation | Whole-session observed graphics pipelines: eight calls, maximum 7.671 ms; shader modules: four calls, maximum 0.023 ms. There is no measured creation delay comparable to the chunk stalls. |
| Turnip synchronization / command submission | Four native calls reach 50 ms: three presents at 56.020, 62.715 and 86.351 ms, plus one 78.827 ms fence wait. No native slow records are suppressed. Whole-session submission maximum is 35.584 ms. EndDraw tails remain relevant, but the dominant interior chunk frame has EndDraw 13.880 ms. |
| Packet-driven object creation | Packet 0xF3 takes 6,750.521 ms, almost all inside the observed chunk boundary. The budget cannot preempt a single registered handler. This does not by itself select a packet-budget change. |
| Scene graph / world construction | The main chunk frame has Scene Update 12.691 ms and Fill 0.265 ms. Construction within packet/chunk work is not excluded by those short scene boundaries. |
| Interior/map-block loading | Directly measured `chunk_load` dominates the largest interior stall and the largest emitted outdoor Draw stall. Underlying synchronization/decoding behavior requires exact deployed method review. |
| Wine/FEX translation or scheduling | Low main-thread CPU, background activity and `ptrace_stop` samples accompany the long chunk interval. Runqueue delay is far smaller than its wall duration. The sampler cannot uniquely identify JIT or PRoot versus client synchronization. |
| Audio/music changes | Music is zero in marked long records; their Audio Update maximum is 0.815 ms. Those boundaries do not dominate the identified chunk stalls. |
| Android presentation | Current-launch windows record 2,948 posts, one geometry configuration, no fallback and zero Surface-work events >=50 ms. Lock/copy/post maxima are 10.913/2.825/11.268 ms. Capture reaches 84.488 ms and receive 258.452 ms; receive includes upstream waiting/pacing. These do not account for the 6.75-second chunk interval. |

Diagnostic contribution also remains bounded but visible: marked resource overhead peaks at 8.299 ms, while frame-boundary bookkeeping reaches 128.944 ms in another interior record. Individual gap durations can include observer/scheduling effects. The directly measured 6,749.949 ms chunk interval survives that qualification and remains the dominant located work in this test. No new optimization is claimed by this analysis.

## Native fence evidence and stability

The outdoor wait completed at 13:29:06.736 with 78.827 ms wall time and 0.090 ms native thread CPU. It matches device 1, fence 158, generation 525, prior successful submission 3040 on queue 1. That submission completed 145.168 ms before the wait began and took 0.328 ms itself. Observed submission commands include one transfer, 180 draws and eight render passes. The image identity is unknown and the command evidence is explicitly uncertain. Fence age is not GPU duration, and this record does not identify an atlas upload as the cause. Its enclosing FNA SwapBuffers call takes 142.723 ms in frame 2586; the frame detail was suppressed.

Native command/image tracking reached capacity before traversal (`tracking_overflow_total=520`), and missing-reference totals continue rising. Timing totals and the named fence lifetime remain useful; complete resource inventories and first-copy attribution are unavailable. Native metadata costs roughly 69–189 ms per five-second window, excluding log output. The largest chunk frame's enclosing native window has submission maximum 0.835 ms and fence-wait maximum 15.730 ms, independently separating that long packet/chunk delay from the earlier 0.2.16 seconds-long submission/fence pattern.

This launch stops after 181.66 seconds, with display/audio shutdown at 13:30:35–36. The Android-exit entries and old client crash files are historical; no current Android low-memory/crash exit is recorded. Whole-device/GPU memory and child-process discovery remain unavailable. Audio delivery gaps/underruns increase during the interruption, without a corresponding long synchronous music/audio-update call. Retain original SDL and the working audio/presentation paths.

## Exact client review and next measurement

The imported client originals were independently downloaded and checksum verified for read-only IL inspection: TazUO `b04066be1b1b475ca00e6982a980e2dd11b93abede00c79c68bde566bdcf947e`, Assets `1dd53cf0eea718aefeda33fba105c9797b138188be22562b47548c310524100d`, and IO `334d1932f6fefe22731cccbbd812a6761d55ffa607ff0a4a291c2bc796c78483`. The resource patcher retains these methods' original behavior while adding observations; timings above are from the installed diagnostic outputs, not executions of these originals during the device test.

Exact IL confirms that `Map.GetTileZ` calls `Map.GetIndex`, which calls `MapLoader.SanitizeMapIndex`. For map index 1, the sanitizer checks the lengths of the current map, statics and static-index files. `FileReader.Length` directly reads the underlying stream's length. `Land.ApplyStretch` contains 11 height queries for each valid textured land tile, and `Chunk.Load` visits 64 land tiles and sanitizes once initially. A chunk with 64 such tiles on map 1 can therefore issue 705 sanitizer calls and 2,115 file-length queries through this path. This is a source-derived upper case, not a count observed in these logs; early-return terrain and missing/empty files reduce it.

Exact `UOFile` constructor IL confirms `FileMode.Open`, `FileAccess.Read` and `FileShare.ReadWrite`, matching the [reference constructor](https://github.com/PlayTazUO/TazUO/blob/73768f6653d39788b00f5bce5b2a063dc76452aa/src/ClassicUO.IO/UOFile.cs). The [.NET 10.0.8 Windows handle implementation](https://github.com/dotnet/runtime/blob/v10.0.8/src/libraries/System.Private.CoreLib/src/Microsoft/Win32/SafeHandles/SafeFileHandle.Windows.cs) caches lengths only when writes are excluded. Write-shared lengths query `GetFileInformationByHandleEx`. That makes repeated length checks under Wine/FEX/PRoot a plausible source of blocked time. **The export does not record the active facet or length-query wall time**, so neither this mechanism nor a particular managed lock is proven as the cause. Loading `map1.mul` at startup does not establish that gameplay used map 1.

Generic `MMFileReader.ReadAt<T>` is pointer arithmetic plus `Unsafe.ReadUnaligned`, with no direct managed wait or file-length query; page faults remain possible. The current small bulk mapped-read timings therefore do not exclude all map-access cost, while the length-query amplification is a separate candidate upstream of those reads. Exact `Chunk.Load` has no explicit lock/wait. Normal synchronous and asynchronous chunk paths pass `updateWorldMap=false`; they skip its optional world-map texture update. Land/static/chunk factories construct new objects, while static-buffer rent/return uses the shared array pool. These facts do not select a pool or explicit-lock fix.

The next diagnostic refinement should keep the existing timing enabled and add bounded nested wall/count observations for the sanitizer and file-length getter, together with chunk ID, input/world map index, coordinates, radar-update flag and the land-height/construction/tile-insertion boundaries. Prefer one aggregate chunk summary over per-tile/per-length output; reserve parent/summary capacity so newly slow child calls cannot exhaust the existing eight-detail limit and hide the enclosing chunk. It must avoid resource CPU queries and preserve every original call/result/exception. That distinguishes repeated Wine file metadata work from map access, object construction or another wait inside `Chunk.Load` before selecting the performance change. Any caching proposal must account for UltimaLive file growth, map replacement and existing fallback behavior rather than globally freezing file lengths.

No gameplay code, runtime, signing identity or release asset changes are made by this analysis. No new branch, PR or APK is needed to record these findings. The priority is the measured synchronous chunk boundary; keep atlas batching, Surface delivery/cache, packet budget, diagnostics and warm-area behavior intact.
