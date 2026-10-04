# Corrected resource diagnostics in 0.2.18

0.2.17 introduced a diagnostic startup regression on Thor: loading `tiledata.mul` took about 132 seconds, compared with 5–6 seconds in the retained 0.2.16 runs. The client continued loading rather than reaching its first Update frame. See the [device evidence](THOR-0.2.17-STARTUP-REGRESSION.md).

The resource observer called Windows `GetThreadTimes` at both ends of every outermost read. `TileDataLoader.Load` reads each entry's short UTF-8 name through the observed `FileReader.Read(Span<byte>)`, with no enclosing observed resource scope; its numeric `ReadUInt*` methods are separate and unwrapped. The CPU queries therefore ran twice per short name read. Under retained Wine/FEX/PRoot those queries incur expensive Wine server and process-stat work. Both query costs lay outside the reported read-body time, and startup had no frame record to expose the accumulated observer overhead.

## Corrective change

0.2.18 removes **all resource-scoped CPU queries** from the helper. It retains the existing resource wall/self/FNA/allocation/lock records and the existing 0.2.16 frame/EndDraw CPU measurements, native Vulkan CPU measurements and available Linux process/thread health counters. Resource records explicitly report `cpu_ms=unavailable` with `cpu_unavailable_reason=observer_overhead`; use the retained enclosing frame and external observations for CPU evidence. No resource-scoped CPU duration should be inferred from that unavailable field.

`RESOURCE_LIMITS` now includes `window_observer_overhead_ms` for every reporting thread/window, including startup and background threads without a game frame. It measures observer bookkeeping/output intervals on entry/exit. Reporting remains deferred until the next outermost scope after the five-second deadline; use the actual `window_ms`. This overhead overlaps enclosing method/frame durations and is not an additive attribution or a safe universal subtraction from nested timings.

The managed activation record and backend report use **revision 3**; the unchanged native Vulkan observer remains **revision 2**, also identified by backend `native_revision`. All seven resource deltas and five resource-library hashes remain unchanged. Only the helper's observations change. Restoration still recognizes the previous .16/.17 diagnostic outputs, validates all backups/deltas before writes, and preserves unknown imported assemblies.

The 0.2.17 [resource and Vulkan field guide](DIAGNOSTICS-0.2.17.md) remains applicable except its per-resource CPU sampling description, which is superseded by this correction. Native fence/command/resource evidence, bounded logging and its uncertainty limits are unchanged. This corrects observation overhead; it does not choose another gameplay optimization or prove the original first-visit stutters are resolved.

## Qualification and Thor check

Structural validation must reject CPU-query paths reachable from resource observations while retaining the old frame CPU clocks. Actual patched startup-shaped readers/loaders must execute under .NET, x64 Wine, retained ARM64 Wine/FEX and both PRoot modes, with checked bytes/positions/results and bounded observation overhead. Existing nested-scope, exception, locking, activation/restoration, atlas, native, UI, Surface, signing and packaging gates remain.

Use the [launch-first procedure](UO-Memento-Mobile-0.2.18-Instructions.txt): install over the current app, keep original SDL with the optional update OFF, enable Cold-load timing, and first confirm login and world entry. Keep runtime, client and caches. If login still remains black after about one minute, stop and export the complete ZIP. If entry works, perform the marked outdoor/interior/retrace phases and export before another launch. Turn cold timing OFF and relaunch for normal play.

Automated compatibility/overhead checks and physical-device recovery are separate gates. The [October 4 Thor result](THOR-0.2.18-ANALYSIS.md) confirms launch/login recovery, while locating the largest remaining marked stall inside synchronous chunk loading. First-world loading and smaller graphics tails remain; this is not evidence that the original cold stutters are solved.
