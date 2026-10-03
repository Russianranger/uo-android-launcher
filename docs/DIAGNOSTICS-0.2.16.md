# Cold first-visit diagnostics in 0.2.16

The [0.2.14 Thor export](THOR-0.2.14-ANALYSIS.md) still contains EndDraw maxima of 1,365.524 and 1,653.006 ms, while recurring atlas flushes after entry are below 0.7 ms. Packet handlers also contribute 163–172 ms pauses. The next question is which native graphics operation or CPU work accounts for those waits. This release adds observations; it applies no further performance optimization.

## Activation and reversibility

Keep **Use SDL 3.4.16 (optional)** OFF for Thor testing. The [failed optional-SDL device comparison](THOR-0.2.16-SDL-FAILURE.md) was followed by an Android low-memory kill; it does not establish a specific SDL defect or memory leak. Continue with the original SDL 3.2.27 library. Turning the optional update off takes effect on the next fresh client launch, using the verified original backup.

**Cold-load timing (Thor test)** defaults off and requires the hash-verified TazUO 5.2 client, Turnip and the existing Smooth world loading/atlas pair. The launcher enables extra observations only in the game environment, after configuration checks. Prefix setup and .NET preflight do not inherit them. Unknown imported libraries remain unchanged.

The diagnostic FNA delta is based on the existing 0.2.14 atlas FNA (`d295aab6…`). It retains the existing flush boundaries and adds timing/finally around 43 FNA3D overloads: draw, upload/readback, presentation, resource/effect creation and selected binding operations. Every native call executes once with its original arguments, return/out values, import ABI and marshalling. No additional flush or synchronization is inserted. All 6,782 unrelated methods, 4,047 metadata constants, resources and existing atlas native imports are preserved by structural verification. Seventeen additional private native clones preserve the original imports for newly observed resource calls.

The intermediate atlas FNA is retained as `FNA.dll.before-memento-cold-trace`. Before every normal configuration pass the launcher restores that verified base, then lets the existing atlas/frame patches select the appropriate state. Turning the diagnostic option off and relaunching removes the additional instrumentation without disabling batching, revision 2 diagnostics or the packet budget. The untouched original atlas backup is required for restoration; unknown files and altered backups are never overwritten.

A small native ARM64 Vulkan loader layer forwards observed calls below Wine's Vulkan thunk. It retains the Turnip ICD, FNA3D/SDL DLLs, graphics arguments/results, device lifetime and queue behavior. It adds no validation, fences, waits, submissions, shader cache policy or rendering operations. Counters use thread-local fixed arrays; registry allocations occur only at instance/device creation. Native observer bytes are checksum verified and compiled against the retained runtime's Debian Bookworm libc.

## Records in the complete Journal export

| Record / file | Evidence |
|---|---|
| `COLD_TRACE_ACTIVE`, `VULKAN_TRACE_ACTIVE` in `client-wine.log` | Confirm managed and native observations actually activated. An option alone does not prove native coverage. |
| `COLD_FRAME` | Update-start-to-next-Update-start gap ≥50 ms, correlated stage durations, worst packet ID/origin, FNA calls, atlas sprites/uploads/merges/bytes/staging/flush, allocated bytes on this managed thread, GC collections, process GC pause delta, render-thread CPU and EndDraw CPU. |
| `COLD_WINDOW` | Counts of gaps and Update/Draw/EndDraw durations ≥25/50/100/250/1000 ms, total measured frames, gap maximum and suppressed detailed-record counts. |
| `FNA_CALL`, `FNA_WINDOW` | Slow individual native-boundary calls; count/total/max for each observed FNA operation. An atlas flush precedes the timed forwarding call so it is not counted twice as that subsequent draw. |
| `VULKAN_CALL`, `VULKAN_WINDOW` | Slow calls and per-operation count/total/max/thread CPU for shader modules, graphics/compute pipelines, pipeline/layout creation, memory/image/buffer creation, mapping/flushing, command buffer setup, queue submission/present, image acquisition and explicit waits. Native PID/TID and UTC allow alignment with managed and external observations. |
| Existing `FRAME_BUDGET`, `ATLAS_UPLOADS` | Revision 2 packet/load/scene/Draw/EndDraw/music summaries and revision 1 batching summaries are retained. |
| `client-test-markers.log` | Fixed outdoor/interior/exit/re-entry/retrace/finished markers, tap UTC, Android monotonic time and launch attempt ID. The overlay does not inject a command into the client. |
| `client-presentation.log`, `client-surface-trace.log` | Existing Android averages plus capture/receive/lock/copy/post maxima and ≥50 ms counts, with bounded slow delivery records. Receive includes upstream waiting and pacing. |
| `client-health.log` | In diagnostic mode, bounded external samples every two seconds instead of ten; optional numeric process read counters and per-thread scheduled CPU/runqueue wait/timeslice counters. Missing permissions are recorded as unavailable. |

Long-frame and slow FNA/native/Surface lines are limited to eight per five-second reporting window per originating thread. Frame histograms and operation totals still include suppressed events. Native windows are emitted when an observed call resumes after the deadline, and remaining counters on that thread are emitted at device destruction. This is not a periodic sampler inside the game. Hot native/atlas observations allocate no managed objects after initialization. Long records and existing summaries do allocate while formatting. `trace_bookkeeping_ms` exposes the diagnostic work at the frame boundary.

## Reading the next trace

| Suspected cause | Evidence to compare |
|---|---|
| Synchronous or deferred resource uploads | FNA SetTextureData / CreateTexture / buffer calls and atlas timing versus Vulkan allocation/mapping/submission/waits in the same UTC interval. A fast upload can still defer its cost to EndDraw. |
| Shader/pipeline creation | `vkCreateShaderModule`, `vkCreateGraphicsPipelines` or `vkCreateComputePipelines` duration/count, especially cold versus warm phases. Pipeline compilation can occur within the driver call. |
| Driver synchronization/submission | Queue submit/present/acquire/fence/semaphore/idle wall time versus native thread CPU. Low CPU during a wait supports blocked or descheduled time, but does not uniquely prove GPU work. |
| Art/static/map decode, file access or construction | Long Load/Fill/Scene/Update/Draw with short observed graphics calls; thread CPU, allocation/GC, optional process `rchar`/`read_bytes` and the phase markers refine the next targeted investigation. These counters do not identify a particular asset or decode routine. |
| Packet object creation bursts | Per-frame handler count, worst handler ID/time and its enclosing Network/Update/Scene timing, alongside creation/allocation activity. Handler and stage times are inclusive and must not be added together. |
| Audio/music transition | Music/Audio stage timing at the interior/outdoor marker, alongside the existing audio logs. |
| Wine/FEX cold paths or scheduling | FNA versus lower Vulkan wall time, render-thread CPU and any available native thread runqueue counters. These do not directly identify FEX JIT, translated basic blocks or kernel/driver scheduling. |
| Android bridge | Rare capture/lock/copy/post tails versus client frame gaps. A large receive time with cheap Surface work can simply mean waiting for an upstream frame. |

GC collection/pause totals are process-wide and do not by themselves locate an allocation site or prove the entire wall gap was GC. Frame gaps include pacing, menu activity and work outside named stages. CPU clocks measure CPU consumed by that thread, not GPU execution. Native API wall time includes any driver work, PRoot syscall handling and scheduling inside the observed boundary. Subtraction across threads or inclusive nested timings is not valid. Marker/menu intervals, startup, map-gump creation and logout must be separated from traversal.

Use the [short Thor procedure](UO-Memento-Mobile-0.2.16-Instructions.txt), then analyze the complete ZIP before choosing another optimization. CI covers structural ABI preservation, actual patched FNA under .NET/Wine/FEX, bounded counters and exceptions, GPU pixel/resource lifetime, and Vulkan-layer activation under Wine/FEX/PRoot. Thor gameplay remains the required performance evidence.
