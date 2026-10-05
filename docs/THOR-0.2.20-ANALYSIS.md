# Physical 0.2.20 map-loading validation

Input: `logs-1911453420459501653.zip`, SHA-256 `3306fcddc305168180c97ad4c920036a3f41875699bd02c7a483b4ced19dac15`. The user reports that this run was substantially smoother. This export confirms that the first targeted optimization removes the repeated metadata work observed in 0.2.19 and that the marked cold outdoor/interior phases no longer contain multi-second frame gaps.

## Session and activation

`status.json` identifies app/runtime 0.2.20 on AYN Thor and the current client attempt beginning **2026-10-05 12:20:03 UTC**. Its stopped boundary is 193.49 seconds after attempt start. Current `client-wine.log`, `client-test-markers.log`, `client-health.log` and `client-audio.log` belong to this attempt. Rotated `.previous.log` Wine/markers/audio retain the already analyzed 0.2.19 attempt beginning **2026-10-05 02:28:58 UTC**; `.previous.2` and older sessions are not added to either run.

The cache is requested and active, revision 1, with `lifetime=chunk_load_call`, 16-reader/8-depth bounds, and the qualified diagnostic IO hash `bb86c8148cb572cd1a1623cbfac6a7215c01d803c2ac466811b5b67097acc34c`. Optimized TazUO and Assets hashes are `112f86ca39e99d0171feedc057130f6c0c7b9b1e780f444068d04e71a4962764` and `f4e554badfe284e63b5183682de87a5534017e1ceb870c5ee024194151f4eb19`. Cold-load diagnostics remain revision 4/native revision 2; resource-scoped CPU queries remain disabled. Smooth world/frame budget, music caching, atlas uploads, smooth audio and dirty regions are active. Optional SDL fixes and render trace are off. Presentation remains native Surface at 1280×720, with the accepted FEX-2510/Wine-10.13 ARM64EC runtime and Turnip.

## Metadata work is reduced on the physical device

All 56 emitted current `CHUNK_WINDOW` records account for **242 completed loads and 723 original file-length getters**. The first main-thread window contains one map-0 load with no length getters; the remaining counts are consistent with **241 map-1 loads × 3 getters**. Every subsequent window has exactly three original getters per completed load. Four identified worker details independently show three getters despite 705 sanitizations/704 height calls in three cases and 441 sanitizations/440 height calls in the fourth. Before this change a full map-1 chunk made 2,115 getters. This is a 99.86% reduction in repeated getter calls for that full-chunk case, measured through the preserved original-getter instrumentation, not an inferred cache-hit counter.

| Main-thread emitted windows | 0.2.19 | 0.2.20 |
| --- | ---: | ---: |
| Completed chunks | 19 | 22 |
| Original length calls | 38,070 | 63 |
| Serial chunk wall sum | 19,696.331 ms | 267.407 ms |
| Length self sum | 19,330.088 ms | 12.213 ms |
| Longest chunk, including map-0 startup | 6,578.185 ms | 197.991 ms |
| Longest main-thread map-1 chunk in cold-interior windows | 6,578.185 ms | 5.795 ms |

The current 197.991-ms startup chunk is map 0 at (115,258), with zero file-length calls. The initial mixed window contains that chunk plus 14 map-1 chunks whose combined wall time is 50.177 ms. Its single aggregate maximum cannot identify the largest of those 14. No main-thread map-1 chunk reached the 50-ms detail threshold, and all current chunk-window suppression/depth/part-depth counters are zero. The 5.795-ms figure is the maximum of the fully contained cold-interior window, not a claim about every map-1 chunk in the attempt.

The cold-interior fully contained main-thread window ending 12:22:25.153 contains four loads totaling 11.251 ms, 12 original length calls and 3.091 ms of length self. The preceding window ending 12:22:20.149 has one 2.001-ms load, three getters and 0.614 ms length self, but its 64-second aggregation span crosses earlier phase markers; keep that qualification when interpreting its count. No slow current detail records identify the old interior coordinate (463,435), because coordinates are emitted only for chunks at least 50 ms. Therefore the interior maxima are a phase-level before/after comparison, not a matched-coordinate stopwatch result. Routes and completed chunk totals differ between runs, so summed-work ratios are not a universal speedup estimate.

Workers account for 220 emitted completed loads, 660 getters, 1,792.124 ms summed chunk wall and 595.337 ms length self. Their longest chunk is 94.131 ms, before the outdoor marker; the corresponding three getters total 70.921 ms, including a 64.399-ms getter. Individual cold metadata misses can still be delayed, but their old multiplicative repetition is absent. Worker time overlaps other workers and the main thread: do not turn those sums into elapsed loading time or add them to frame/network durations. Final worker partial windows can remain unreported, so 242 is an emitted-window count, not the complete attempt count. Do not add five detail records to the window totals.

## Cold and warm phase behavior

Current markers and frame detail maxima are:

| Phase | Start UTC | Duration to next marker | Largest recorded frame gap |
| --- | --- | ---: | ---: |
| Outdoor cold | 12:21:18.398557 | 29.397 s | 143.663 ms |
| Outdoor warm | 12:21:47.795112 | 29.398 s | 51.337 ms |
| Interior cold | 12:22:17.193530 | 19.025 s | 134.741 ms |
| Interior exit | 12:22:36.218364 | 8.054 s | No frame detail ≥50 ms |
| Interior warm | 12:22:44.271967 | 7.317 s | 53.900 ms |
| Finished | 12:22:51.588660 | — | Outside measured traversal |

No marked traversal phase has a frame gap ≥250 ms or ≥1 second in the recorded details or surrounding preserved window aggregates. No long-frame details are suppressed in these phases. Windows crossing markers are not assigned solely to their ending phase. Fully contained outdoor-cold chunk windows account for 96 worker loads, maximum 29.536 ms; fully contained cold-interior chunk windows have maximum 33.752 ms across threads. Deferred windows also emitted during these phases contain earlier startup work and must not be used as exact phase counts.

The former marked cold-interior frame was 6,827.680 ms with a 6,578.185-ms chunk/6,558.669-ms length self inside packet F3. That pattern does not recur. Current cold-interior packet/frame-budget windows have packet maximum 12.918 ms and network maximum 14.165 ms. The 134.741-ms frame at 12:22:22.093 has 110 ms thread CPU, 0.013 ms network, zero process GC pause, 7.857 ms native total and 1.722 ms resource-root wall. The 91.779-ms frame at 12:22:20.346 includes a 59.934-ms world-render-target scope, self 9.486 ms, with its own nested work; it is not a long map chunk. The 50.734-ms frame at 12:22:23.511 includes 15.814 ms process GC pause. These are remaining modest frame hitches, not the old metadata stall.

Warm outdoor/interior continue smoothly with occasional ~51–54-ms frames. The interior-warm sample is only 7.3 seconds, similar to the short prior sample; this is validation of the tested routes, not proof that all unvisited areas behave identically.

## Remaining startup work is a separate measured boundary

The first emitted managed frame is **12:20:55.255682 UTC, 52.256 seconds after attempt start**, compared with 47.528 seconds in 0.2.19. The first identified initial-world chunk begins approximately 12:21:05.281 UTC, 62.281 seconds after attempt start, compared with ~62.152 seconds before. These are the same telemetry boundaries used previously; neither is an exact login-screen-ready stopwatch or a startup measurement excluding user input. The export supports successful startup/world entry, but does not establish a startup-time improvement.

The longest current frame is **5,215.163 ms at 12:21:11.669, before the outdoor marker**. Packet 55 handling is 4,651.909 ms; the enclosing network-processing resource scope has 4,655.076 ms wall and 4,288.236 ms self. The nearby 5.603-second resource window has 14 chunk wrappers totaling only 50.406 ms; metadata repetition cannot account for this startup frame. The frame includes 1,266.722 ms of scene load, 445.475 ms total FNA calls (maximum 45.405 ms), 5,389,224 allocated bytes and 84.584 ms process GC pause. Scene load and packet/resource scopes overlap; resource self excludes instrumented resource children but does not independently exclude every native call. They must not be added into a supposed complete elapsed-time breakdown. The precise function within packet 55's remaining self work is not measured, and this client-handler boundary is not evidence of a server-response wait.

Initial frame 1298 is 1,816.440 ms, including packet 1B, the map-0 chunk, 31.8 MB frame allocation and 47.905 ms GC pause. The next initial draw frame is 1,641.707 ms with 1,442.064 ms draw (including fill), 104.620 ms native total and 96.048 ms GC pause. There is also a 1,135.509-ms frame after the `finished` marker; it is outside the cold/warm route comparison and contains no chunk work. These observations do not justify adding an unqualified startup or renderer change to the official release.

## Native rendering, audio and shutdown

Current Vulkan windows have maximum fence wait 5.425 ms, queue submit 7.249 ms, present 13.826 ms and device-idle wait 0.271 ms; there is no observed multi-second Vulkan wait. Native Surface remains active in all 36 current presentation records. Surface lock/copy/post work has zero ≥50-ms events; there is one 51.362-ms receive event near initial world entry, before the outdoor marker. The presentation log contains older sessions, so these counts include only records from the current attempt. Diagnostic Vulkan command tracking explicitly has incomplete coverage and later tracker overflow; the call timings support the stated recorded maxima, not proof of complete native dependency attribution.

A background image-from-stream scope during outdoor cold takes 479.220 ms and includes 470.820 ms nested FNA calls, including a 379.610-ms image load and 71.430-ms texture upload. It overlaps main frames and is not a 479-ms main-thread frame pause. No graphics change is justified for this validated metadata fix.

Audio produces nonzero samples throughout, releases 6,583,680 written/played frames and closes its stream/bridge normally. The current audio log records 592 underruns, one producer delivery gap over 40 ms (maximum 63.836 ms) and none over 80 ms. The preserved prior log had 1,002 underruns, 255 delivery gaps over 40 ms and 59 over 80 ms (maximum 192.531 ms). Stream durations/options and route durations differ; these are observed counters, not an isolated audio benchmark or a claim of underrun-free sound.

Current input records relative movement/button traffic and consumer disconnection. Status reports client stopped and realm/session saved and closed; server log ends with save completion and `Exiting...done`. No current client crash/unhandled-exception record is present. Historical September crash files and pre-attempt launcher connection errors are retained in the archive and are not failures of this attempt.

## Release decision

The supplied physical evidence validates the targeted chunk-lifetime metadata reuse and preserves successful startup, cold traversal, warm revisits, native Surface rendering, audio delivery, input and saved session shutdown in this test. Together with the existing host/Wine/FEX/both-PRoot/Android qualification from 0.2.20, it supports issuing the next APK as an official release without speculative runtime or graphics changes. Preserve the cache-off path and revision-4 diagnostics for any future comparison; normal play can turn Cold-load timing off after validation.
