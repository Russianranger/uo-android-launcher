# Cold resource and fence diagnostics in 0.2.17

The original-SDL [marked 0.2.16 test](THOR-0.2.16-ANALYSIS.md) exposed a 1,658 ms interior frame dominated by EndDraw: native fence waiting and submission accounted for about 1.103 seconds of its 1.136-second FNA swap. The stable [recovery test](THOR-0.2.16-RECOVERY.md) also exposed a 1,120 ms Draw with a 2048-square texture creation whose 221 ms native submission explained only part of Draw. That recovery launch had no new phase markers, so it cannot establish a cold/warm comparison.

0.2.17 measures the two remaining gaps: which observed submission/resource preceded a native wait, and which resource, decode, loading or lock boundary consumed long Draw or packet work. It adds no performance optimization. The optional SDL test remains withdrawn after the [device low-memory exit](THOR-0.2.16-SDL-FAILURE.md).

## Activation and restoration

Use **Cold-load timing (Thor test) ON**, **Use SDL 3.4.16 (optional) OFF**, Turnip, Native Surface, changed regions and the existing Smooth world loading/atlas pair. Start a fresh client process. When cold timing and Turnip are selected, the launcher restores the verified original SDL before configuring diagnostics even if the optional update preference was accidentally left on. A known updated SDL without a valid original backup blocks that diagnostic launch. Unknown imported SDL is preserved and diagnostics remain inactive; ordinary cold-timing-OFF behavior is unchanged.

The manifest reports `revision=2`, `resource_boundaries=24`, `resource_locks=5` and the hashes of the five active resource libraries. Verify both `COLD_TRACE_ACTIVE revision=2` and `VULKAN_TRACE_ACTIVE revision=2` in `client-wine.log`; the checkbox alone does not prove coverage.

Resource deltas apply only to the exact verified TazUO 5.2 assemblies, including the existing frame/render and music-cache variants. All deltas and all known restoration backups are validated before activation writes. Reconfiguration first restores verified prior diagnostic outputs; turning cold timing off and relaunching restores the existing frame/atlas/music bases and removes the extra FNA/resource/native observers. Interrupted activation is repaired on the next configuration pass. Unknown assemblies or altered backups are never overwritten. No client reimport, cache reset, runtime reinstall or data clearing is needed.

The 0.2.13 summaries, 0.2.14 batching, 5 ms/1,000 packet budget, original SDL/FNA3D DLLs, Wine/FEX runtime, Surface delivery/cache, audio, server, input, layout and signing identity are retained. The quick-menu label remains **Back to Launcher Menu**.

## New records in the complete Journal ZIP

| Record | What it measures |
|---|---|
| `RESOURCE_CALL` | Observed methods taking at least 50 ms: frame/stage/thread, operation/parent/depth, inclusive wall time, self time excluding observed resource children, inclusive nested FNA time, thread allocations, outermost thread CPU, start offset and deferred log delay. |
| `RESOURCE_WINDOW` / `RESOURCE_LIMITS` | Per-operation count, inclusive/self/max/FNA totals, measured `window_ms`, suppressed slow records and depth overflow. Reports occur at the next outer resource entry after the five-second deadline; idle periods can make windows longer than five seconds. |
| `COLD_FRAME` additions | Root resource call count, inclusive root wall/FNA time and resource observation overhead for the current managed frame. Existing packet, Draw, EndDraw, GC, allocation, CPU and atlas fields remain. |
| `VULKAN_CALL` additions | Device/queue identities, submission attempt/prior successful submit IDs, observed command counts, first observed copy-image identity/extent; fence identity/generation/origin/age and bounded source-submission evidence; resource creation dimensions or memory allocation size. |
| `VULKAN_COUNTS` additions | Image/2048-square creation counts, allocation bytes, metadata time and explicit missing/overflow/truncated tracking counts. Thread timing totals span all its devices; tracker counters name their device separately. |

The 24 resource boundaries cover real art/land/static/gump/texmap/light and UOP/MUL/PNG decode methods; three bulk file-read methods; chunk loading; world render target/list construction; animation frame access; Item/Mobile creation; image loading; and FNA resource registration/removal. Five original `Monitor.Enter` sites measure animation and resource-lock acquisition. A helper-only enclosing `network_processing` scope samples CPU once per packet-processing pass. Primitive and generic per-value reads are not instrumented.

Managed state has a fixed depth of 32 and eight slow records per thread per reporting window. Nested lock records are formatted after the enclosing observed method has completed its original cleanup. Warm scope entry/exit allocates no managed objects after initialization; slow records and summaries allocate while formatting. Allocations can include diagnostic formatting from nested FNA records. Per-scope CPU is sampled only at the outermost resource boundary; nested CPU is explicitly unavailable.

The native observer retains successful fast submission/acquire metadata without logging each fast call. It adds no queries, waits, submissions or GPU commands and forwards original arguments/results exactly once. Device IDs and per-device object IDs are monotonic; fence generations advance after successful reset. Fixed per-device capacities are 16 queues, 256 fences, 512 command buffers and 512 images. Waits report at most eight fences; submissions inspect at most 64 batch headers and 64 command references. Omitted or unknown data is explicit. Metadata mutexes are never held across driver calls. Driver wall/CPU surrounds the forwarding call; `metadata_ms` excludes log formatting/writing. See the [native field reference](../native/graphics-diagnostics/README.md).

## Selecting the next change from device evidence

| Candidate | Evidence to compare in matching marked phases |
|---|---|
| Remaining synchronous texture/resource work | Resource/image/animation boundaries, atlas allocation/upload fields, FNA CreateTexture/SetTextureData/buffer calls, native image/memory creation and correlated transfer submissions/waits. Fast upload calls can defer cost to EndDraw. |
| Art/static/map decode or first-access I/O | Decode, bulk file reads and chunk loading versus nested FNA, thread CPU and available process I/O counters. File scopes identify a method, not a particular path or whether bytes came from disk/cache. |
| Allocations/GC | Resource thread-allocation deltas versus existing process GC collections/pause deltas; allocation alone does not prove the frame paused for GC. |
| Shader/pipeline creation | Existing Vulkan shader/graphics/compute pipeline call durations and counts, compared cold versus warm. |
| Driver submission/synchronization | Slow queue/fence/acquire/present wall versus CPU, prior submission evidence and resource identities. Low CPU supports waiting/descheduling; it does not uniquely prove GPU execution. |
| Packet object or scene/world construction | Network/handler durations, Item/Mobile counts and resource/render/chunk boundaries. Inclusive handler and child times must not be added together. |
| Interior/map block loading | First-entry versus re-entry chunk/decode/read/render activity; distinguish it from login/map-gump/menu work. |
| Wine/FEX/JIT or scheduling | Unaccounted managed/FNA/native intervals, thread CPU and available runqueue counters. These observations do not identify translated blocks or directly measure FEX JIT compilation. |
| Audio/music changes | Existing Music/Audio stage durations and audio logs aligned with phase/hitch notes. |
| Android presentation | Existing capture/receive/lock/copy/post maxima and slow counts against client gaps. Receive includes upstream waiting; it is not independently proof of bridge work. |

`nested_fna_ms` is inclusive and cannot be subtracted from resource `self_ms`. Fence age is time since an observed successful submit/acquire returned, not GPU execution time. Wait-any or multi-fence records do not identify the blocking fence. Command coverage is incomplete; secondary execution is uncertain. The first copy image is one observed resource, not proof that it dominates a submission. Allocation-byte totals do not subtract frees and are not a memory-leak census. Background resources can have frame 0 and unavailable stage/offset. Diagnostics themselves have overhead and device behavior remains decisive.

Use the [marked Thor procedure](UO-Memento-Mobile-0.2.17-Instructions.txt), then send the **complete ZIP before starting another client session**. Separate startup, marker/menu intervals and logout from traversal. Analyze the cold/warm phases before choosing an optimization.

## Validation

Local validation verifies all seven exact deltas, all 24 patched method bodies and five locks, JIT preparation of every patched method, actual bulk I/O/lock/exception behavior, nesting/network exceptions/stage overflow, bounded logging, warm zero-allocation observations, five-library activation/restoration, SDL safety and native forwarding/lifetimes/pixel parity/correlation. CI adds retained x64 Wine, ARM64 Wine/FEX and both PRoot modes, plus packaged APK imports, UI, signing, runtime, audio, Surface and server checks. CI and Thor gameplay results must be assessed separately.
