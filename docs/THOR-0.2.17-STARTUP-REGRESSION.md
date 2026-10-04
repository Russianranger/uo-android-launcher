# Thor 0.2.17 startup diagnostic regression

## Device evidence

Input: `logs-4849745074048213633.zip`, SHA-256 `0bc204fd2ff9a128e8b3547fcd446380269263f58f6513328f618e3ab55cd962`. Current launch starts 2026-10-04 01:05:46 UTC (October 3, 20:05:46 America/Chicago). The user reports a black screen before login. Both revision-2 diagnostic activation records are present. Source baseline is `66a6b12`, the 0.2.17 diagnostic release.

The loader progresses slowly rather than remaining deadlocked. It opens `tiledata.mul` at 01:06:21, disposes it at 01:08:33, then continues into multi, skills, texmaps and speech. Resource windows continue through 01:08:51. No `COLD_FRAME` appears: this startup work precedes the first Update boundary. It cannot be assigned to an outdoor/interior phase.

The same ZIP retains earlier device logs:

| Launch | Tiledata open / dispose UTC | Approximate tiledata interval | Reported complete file-load time |
| --- | --- | ---: | ---: |
| Current 0.2.17 | 01:06:21 / 01:08:33, October 4 | 132 s | Not completed in current log |
| Original-SDL 0.2.16 recovery | 13:09:31 / 13:09:37, October 3 | 6 s | 8,427 ms |
| Original-SDL marked 0.2.16 test | 11:16:52 / 11:16:57, October 3 | 5 s | 6,438 ms |

These are separate launches with coarse one-second loader timestamps, not a controlled benchmark. The large regression is nevertheless directly visible on the same device and files.

## CPU-query overhead pattern

During the current tiledata interval, 26 completed resource windows report **80,697 `file_read` calls**, only **131.543 ms total inclusive duration**, and a maximum individual duration of 1.671 ms. Nearest health samples at 01:06:21 and 01:08:33 span 131.69 seconds and show:

- Main-thread scheduled CPU increases by **47.961 seconds**, runqueue wait by **6.824 seconds**, and scheduling slices by **999,128**.
- Process read-syscall count increases by **328,230**, with **62,108,726 bytes of `rchar`**, but **zero additional physical `read_bytes`**.
- Client/FEX sampled RSS peaks at **425.86 MiB** across the launch.

Nearby six-second loading samples in the original-SDL recovery and marked 0.2.16 logs show approximately 3.18/3.31 seconds of main-thread CPU and 3,080/3,639 process read syscalls respectively. Health samples do not align exactly with the coarse file-open/dispose lines, so these deltas describe nearby startup intervals rather than exact method profiles.

In the released 0.2.17 `ResourceTrace.Begin` and `End`, every outermost resource scope invokes `ColdTrace.ThreadCpu()`. On Windows/Wine this uses `GetThreadTimes`. The entry query precedes the operation start timestamp; the exit query follows its end timestamp. Both costs are excluded from `RESOURCE_WINDOW` inclusive time. The short preload reads have no enclosing observed resource scope, so each read becomes outermost. No frame record yet exists to expose their accumulated `resource_trace_overhead_ms`.

Exact pinned-client IL confirms the startup path: `TileDataLoader.Load` reads numeric fields through unwrapped `ReadUInt*` methods, then reads each entry's UTF-8 name through the observed `Read(Span<byte>)`. The loader itself has no resource wrapper, so every short name read is an outermost scope. Generic `Read<T>` also reaches that span-read boundary; numeric `ReadUInt*` methods do not.

The approximately four process read syscalls per observed short name read, large CPU/scheduling growth, tiny measured read work and zero physical-read growth strongly support repeated CPU queries as the new overhead source. They do not attribute every delayed millisecond or every Linux syscall to `GetThreadTimes`; that would require direct syscall tracing or a controlled before/after execution. This is a diagnostic regression, not evidence that tiledata decoding normally takes two minutes.

## Other boundaries and limits

Current presentation samples contain 39 posts (37 region / two full), two buffer configurations, no fallback, thermal status zero, and zero Surface-work or receive events at least 50 ms. Lock/copy/post maxima are 4.402/0.574/2.193 ms; capture/receive maxima are 8.995/26.638 ms. The capture bridge mostly skips unchanged images. These observations do not locate a new presentation bottleneck.

There is no native Vulkan call at least 50 ms. The only slow FNA call is startup device creation at 128.228 ms, before the prolonged file loading. Android exit history contains no exit for this October 4 launch; its latest retained entry is October 3 at 13:23:52. This export does not show a new low-memory kill or native crash. Historical crash files and earlier exits must not be assigned to the current run.

## Correction and qualification

The selected correction is **helper-only removal of all per-resource thread CPU queries**. Retain cheap resource wall/self/allocation/FNA timing and bounded records, existing 0.2.16 frame/EndDraw CPU sampling, native Vulkan CPU timing and Linux health sampling. Preserve all seven exact managed resource deltas and the original SDL/runtime/rendering/audio/input behavior. This corrects measurement overhead; it does not select a new gameplay optimization.

0.2.18 qualification must exercise an actual patched startup-shaped record-read loop under retained Wine/FEX/PRoot, in addition to the existing structural, forwarding, restoration and packaging checks. A host-only helper test or a loop that calls the helper directly does not establish the cost of the deployed patched reader. Device login and a subsequent marked cold/warm route remain required after the correction. Check results and physical-device recovery must be reported separately; this note does not claim those checks have passed or that the original cold first-visit stalls are solved.
