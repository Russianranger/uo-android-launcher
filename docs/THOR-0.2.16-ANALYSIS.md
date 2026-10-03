# Thor 0.2.16 cold-load trace

## Session and measurement scope

Input: `logs-6776336423862027242.zip`, SHA-256 `6d20e2bb3b9f83b45203c3a4a027e67d0167ce5f2b7ae6291dbe10fd97c461cb`. Current launch: 2026-10-03 11:16:38 UTC (06:16:38 America/Chicago), approximately 184 seconds. The export reports app 0.2.16 and AYN Thor. Source/release baseline is `78b6d11498e6fa624b5e2024b6b9f16591194ea5`.

The verified TazUO 5.2 pair, Wine 10.13 ARM64EC/FEX-2510, Turnip, Native Surface, changed regions, geometry caching, 60 FPS target, 1280x720 canvas/1098x720 world, Smooth world loading and music cache remain active. Cold timing is enabled; both `COLD_TRACE_ACTIVE` and native `VULKAN_TRACE_ACTIVE` are present. The diagnostic FNA hash is `18c88d506dbe15dcb4bb56f98e4b1756d9f8074ba8ab485ad36e10c087f168b1`. The native observer hash is `083c113887a43a912dc42f05e2d919fcafa816d5864f0d1512affc37eb5240b5`. Optional SDL remains OFF: the original 3.2.27 library is active. PRoot reports seccomp acceleration and memfd shared memory.

The archive contains older launches. This analysis uses the current Wine/health/audio/marker logs and filters both accumulated Android presentation files to this launch. Startup, first world draw, finished-phase activity and logout are separated from traversal. Markers identify the user's intended actions; they do not establish exact movement/doorway coordinates.

## Cold versus warm phases

| Marked phase | UTC start | Duration to next marker | Recorded gaps >=50 ms | Recorded gaps >=100 ms | Largest recorded long gap |
| --- | --- | ---: | ---: | ---: | ---: |
| Outdoor first pass | 11:17:32.636 | 32.271 s | 19 | 12 | 204.314 ms |
| Outdoor retrace | 11:18:04.907 | 30.861 s | 0 | 0 | No gap >=50 ms |
| Interior first entry | 11:18:35.769 | 14.328 s | 4 | 3 | 1,658.132 ms |
| Interior exit | 11:18:50.097 | 9.902 s | 0 | 0 | No gap >=50 ms |
| Same interior re-entry | 11:18:59.999 | 16.909 s | 0 | 0 | No gap >=50 ms |

These counts assign completed `COLD_FRAME` records by UTC between markers. There are no suppressed long-frame or native slow records in the marked traversal interval. Counts are measured Update-start gaps, not an FPS measurement: the client can Update more often than it Draws.

Menu/marker intervals need care. Excluding frames whose approximate start is within three seconds of a phase marker leaves 17 outdoor long records, including 11 gaps >=100 ms, and three interior long records. That conservative rule also excludes the main interior hitch because it begins roughly 2.1 seconds after the interior marker; its directly observed packet/graphics work is still reported below rather than discarded as menu activity. UTC reporting and CPU-query/logging delays limit exact reconstruction of a frame's start.

Complete five-second windows wholly inside the outdoor retrace have no gaps >=50 ms and a maximum gap of 28.641 ms. Equivalent complete interior re-entry windows have no gaps >=50 ms and a maximum of 42.273 ms. This short test confirms the cold/warm distinction; it does not establish all-session smoothness or a controlled improvement over 0.2.14.

## The main interior hitch

Frame 11967, reported at 11:18:39.563607 UTC:

| Boundary or observation | Duration |
| --- | ---: |
| Update-start gap | 1,658.132 ms |
| EndDraw | 1,477.149 ms |
| FNA3D_SwapBuffers inside that frame | 1,135.935 ms |
| vkWaitForFences, completed 11:18:39.164 | 765.943 ms wall / 0.077 ms native thread CPU |
| vkQueueSubmit, completed 11:18:39.391 | 226.619 ms wall / 1.310 ms native thread CPU |
| vkQueueSubmit, completed 11:18:39.502 | 111.155 ms wall / 1.393 ms native thread CPU |
| Update / worst registered packet handler 0x20 | 148.177 / 146.285 ms |
| Draw / FillGameObjectList / Scene Update | 4.099 / 0.840 / 1.061 ms |
| Atlas flush / staging | 0.107 / 0.120 ms |
| Process GC pause delta | 4.728 ms |
| Allocated bytes on the managed frame thread | 280,336 bytes |
| Music / Audio Update | 0.000 / 0.008 ms |
| Frame-boundary trace bookkeeping | 0.697 ms |

The three slow native calls are sequential on Linux PID/TID 7293, within the same FNA swap interval. Their combined wall time is 1,103.717 ms, approximately 97% of that measured FNA call. Their combined native thread CPU is 2.780 ms. Each returns Vulkan success. This directly locates most of the native swap pause in fence waiting and command submission. It does not prove whether the underlying delay is GPU execution, deferred resource work, driver/kernel synchronization or PRoot handling inside those boundaries.

EndDraw includes roughly 341 ms beyond the timed FNA swap, which remains unseparated. Windows thread CPU values appear quantized in 10 ms increments here; the reported EndDraw CPU of zero is not proof of absolutely no CPU work. Native clocks provide the finer per-call evidence.

The immediately following frame is 129.776 ms, with a 101.296 ms registered 0xF3 handler. A later 173.969 ms interior frame has EndDraw 165.759 ms, FNA swap 33.242 ms and no atlas uploads. Those secondary delays remain relevant after the largest native stall is addressed.

## Outdoor stalls and competing causes

Thirteen of the 19 marked outdoor long frames have EndDraw >=50 ms. Outdoor gaps peak at 204.314 ms; EndDraw peaks at 194.189 ms. Native fence calls include 56.270 and 51.114 ms waits, with about 0.08 ms CPU each. Other outdoor EndDraw tails substantially exceed their FNA swap duration, so the complete outdoor problem is not explained by those two fence records alone. One Draw reaches 98.840 ms. Three outdoor records have trace bookkeeping of 22.378, 61.041 and 46.606 ms; those observations contain a diagnostic contribution and should not all be attributed to gameplay work.

| Possible remaining cause | Measured evidence and decision |
| --- | --- |
| Synchronous texture/resource uploads | Largest traversal-frame atlas flush is 0.197 ms. The main interior frame has 21 sprite requests, 16 uploads and five merges. Post-marker FNA texture-upload summary maxima are 0.119 ms. No texture creation is recorded in the marked traversal interval. Direct upload work does not account for the large hitch; earlier uploads can still incur deferred GPU work. Retain batching. |
| Sprite/art/static/map decode or first-access disk I/O | Cold outdoor process physical-read counters increase by about 32.4 MB over the sampled phase, versus about 3.7 MB in the warm phase. Interior cold reads also increase. These process-wide counters include other activity and cannot locate files, decode routines or duration. The 98.840 ms Draw warrants follow-up if it survives the graphics comparison. |
| Managed allocation / GC | The largest traversal gap has about 274 KiB of current-thread allocation and 4.728 ms GC pause. The maximum GC pause among marked long records is 5.102 ms. GC does not explain the second-long native wait. Startup allocations/collections are a separate issue. |
| FNA/SDL/Vulkan shader or pipeline creation | Across the entire session, eight observed graphics-pipeline creations peak at 1.391 ms; four shader-module creations peak at 0.022 ms. Neither is newly recorded during the marked traversal. There is no evidence for a pipeline-creation optimization here. Deferred driver work inside another call is not excluded. |
| Turnip/Vulkan synchronization / submission | The dominant directly accounted interval is the 765.943 ms fence wait plus 337.774 ms in two submissions. This is the first graphics path to investigate. Low CPU means blocked/descheduled time in these calls, not a uniquely identified driver bug. |
| Packet-driven object creation | Handlers 0x20 and 0xF3 take 146.285 and 101.296 ms at first entry. The existing budget cannot preempt one registered handler. These are secondary stalls; construction/decoding inside each handler is not separately measured. |
| Scene graph / world construction | The largest entry hitch has Scene Update 1.061 ms and Fill 0.840 ms. Post-marker summary maxima are Scene 30.048 ms and Fill 8.088 ms. Those boundaries do not dominate the large entry frame. |
| Interior/map-block loading | The marked first-entry spike is explicit. Whole GameScene.Load is not called in the marked interval; per-block decode/read work can occur elsewhere and is not ruled out by Load=0. |
| Wine/FEX cold translation or scheduling | Native waits account for most of the timed FNA swap. Linux render-thread runqueue delay increases by about 28.6 ms in the two-second sample spanning the main stall, much less than the 1.1-second native wait/submission total. Adreno waits, pipe reads and ptrace stops also occur in warm samples. The two-second sampler cannot uniquely identify JIT, PRoot dispatch or GPU/kernel scheduling; no translated-block compilation timing is collected. |
| Audio/music transitions | Music is zero in the large entry frame; marked summary music maxima are under 10 ms and Audio Update under 5 ms. Audio delivery has a concurrent 559 ms gap, consistent with a wider interruption but not evidence that audio caused EndDraw to stall. Preserve the audio path. |
| Android presentation bridge | 5,471 posts, one initial geometry configuration, no fallback and thermal status 0. Weighted capture/lock/copy/post costs are 0.687/1.232/0.286/0.486 ms. Lock/copy/post maxima are 10.214/5.087/5.559 ms, with zero Surface-work >=50 ms events. Capture has a 170.591 ms tail and request/receive a 403.662 ms tail around entry. Capture/receive can wait for shared graphics/upstream work; neither is equivalent to Surface copying cost. Preserve changed regions and geometry caching. |

Initial world drawing before the outdoor marker contains a separate 2,384.797 ms gap, Draw 2,304.657 ms, Fill 892.557 ms and 55.224 ms GC pause. Earlier login packets are also expensive. Finished/logout gaps are excluded. These should not be conflated with recurring first-visit traversal.

## Next controlled comparison

The measured priority is the FNA/SDL Vulkan swapchain-fence and upload/render-submission path. A safe code change is not yet uniquely selected by these logs. Do not remove synchronization, change frames in flight or add another atlas/GC/pipeline optimization on this evidence alone.

The existing 0.2.16 APK already offers **Use SDL 3.4.16 (optional)**. Test that one option ON with Cold-load timing still ON and every other setting unchanged. The exact supported-library checks accept both SDL versions for batching and diagnostics, and retain a verified original backup. This comparison requires no new APK, branch, PR or performance patch. The existing CI exercises both SDL versions with real FNA3D under x64 Wine; the updated version's Thor Wine/FEX gameplay behavior still needs this device comparison.

Use a fresh client process, settle after world entry, then mark/repeat the same approximately 30-second outdoor first pass and retrace, first interior entry, exit/re-entry and finished phase. Close the marker menu and wait about three seconds before movement. Export the full Journal ZIP before another launch. Compare cold gaps >=100 ms, EndDraw maxima, native fence/submission tails, packet timing and warm-phase behavior. A material benefit should be confirmed against the original version before changing defaults. Turning the optional SDL setting OFF and relaunching restores the verified original; disable cold timing for ordinary play.

The FNA3D 25.11 [reference source](https://github.com/FNA-XNA/FNA3D/blob/de4870e6cd215ea97ea6109cc72c25c0276f1bec/src/FNA3D_Driver_SDL.c) acquires the swapchain before flushing upload and render command buffers in SwapBuffers. SDL's [3.2.28 reference Vulkan backend](https://github.com/libsdl-org/SDL/blob/release-3.2.28/src/gpu/vulkan/SDL_gpu_vulkan.c) waits on an in-flight fence during blocking swapchain acquisition. This matches the observed wait-then-two-submissions sequence but does not identify the waited fence in this export or establish source identity for the deployed 3.2.27 binary. The [3.4.16 backend](https://github.com/libsdl-org/SDL/blob/release-3.4.16/src/gpu/vulkan/SDL_gpu_vulkan.c) also retains that synchronization: the comparison tests the graphics implementation, not the removal of waits.

If the SDL comparison leaves the stall intact, the next targeted work is to identify the waited fence's submission/age and the upload/render batches around cold resource use, with finer driver/PRoot evidence if needed. No rendering/runtime/input/audio defaults or performance implementation are changed by this analysis.
