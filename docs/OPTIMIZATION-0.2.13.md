# First-visit load diagnostics

## Device evidence

The latest 0.2.12 Thor support ZIP reports severe stutters on the first visit to an area or interior, followed by smooth movement once loaded. Steady-state `buffer_reconfigurations` are zero, so the repeated Native Surface setup corrected in 0.2.12 is no longer the evidenced cause of these pauses.

- A network-processing call reached about 4,489 ms within a 4,498 ms update. The existing packet budget cannot yield in the middle of a handler, so a single expensive dispatch remains possible.
- Other cold frame gaps reached approximately 419–980 ms while recorded update work was much smaller. Warm sections were around 29–44 ms. Drawing, texture creation/upload, presentation and other work outside the update interval were not separated by the previous summaries.
- Startup `GameScene.Load` and `FillGameObjectList` reached approximately 1,040 ms and 401 ms. These are startup costs, not proof that the same operations caused a later interior pause.

The first-visit pattern is consistent with cold work, but these logs do not establish whether it is file access/decompression, object creation, a packet handler, JIT/allocation, texture creation/upload, presentation or music switching. Adding asynchronous loading or prefetching before locating the work would risk moving the wrong operation or changing required main-thread behavior.

## Additional boundaries

The existing frame-budget helper is upgraded to revision 2. With **Smooth world loading** enabled on the exact supported client, it extends the existing `FRAME_BUDGET` lines in `client-wine.log`:

| Fields | Purpose |
|---|---|
| `draw_calls`, `draw_max_ms`, `draw_total_ms` | Original game drawing, including work after Update. |
| `enddraw_calls`, `enddraw_max_ms`, `enddraw_total_ms` | Original inherited FNA presentation boundary, separate from Draw. |
| `music_calls`, `music_max_ms`, `music_total_ms` | Music switching through the original `AudioManager.PlayMusic`. |
| `packet_calls`, `packet_max_ms`, `packet_id`, `packet_network` | Slowest registered packet-handler dispatch and its queue origin. |
| `packet_network_calls`, `packet_network_max_ms`, `packet_network_id` | Registered network packet-handler dispatches. |
| `packet_plugin_calls`, `packet_plugin_max_ms`, `packet_plugin_id` | Registered plugin packet-handler dispatches, including those inside network processing. |

Packet origin is supplied by the parser's actual network/plugin flag; a surrounding network timing scope alone cannot identify it. Packet IDs are hexadecimal; `none` means no qualifying dispatch. Empty packets are ignored. The helper retains no packet contents or handler objects, performs no per-packet logging and adds no graphics call or background worker. The original registered-handler dispatch, Draw, presentation and music behavior execute within timing wrappers that preserve exception propagation. The handler boundary covers `AnalyzePacket` and its reader/registered-handler call; it excludes packet logging, plugin receive filters and preceding parser lock/copy work. A long network maximum with a small handler maximum therefore points to work before that boundary rather than proving asset loading. The inherited `EndDraw` override delegates to the exact original FNA implementation and times submission/presentation.

Summaries remain approximately five seconds apart. The maximum packet ID is the ID of the slowest dispatch in that window, not a list of every packet. Stage totals can overlap and must not be added as independent frame costs. GC collection deltas are counts, not pause durations. Update gaps span work between updates; a gap by itself does not identify an asset loader. Cold work before the next summary is retained for that summary. The counters report window maxima, not samples at the exact UTC timestamp of a noted stutter, and do not identify every loader.

The existing 5 ms / 1,000-packet parsing budget is retained. It yields between complete packets and cannot interrupt a long handler. This pass adds evidence for a targeted loading change; it does not implement prefetching, asynchronous asset loading, allocation changes or new frame pacing.

## Exact-client upgrade and reversibility

The launcher recognizes both previous frame-budget revisions: ordinary budget and budget plus render instrumentation. It verifies the preserved original TazUO DLL before generating the new exact checksum-verified variant. It does not stack another patch onto a modified binary. Repeated preparation is idempotent, and switching the existing options continues to restore original or render-only states through the verified backup. A missing, altered or symbolic-link backup prevents an unsafe migration. Unrecognized clients remain unchanged.

The application ID, signing identity, installed runtime, assets, settings and client data are retained. Updating the APK and starting the supported client applies the revised helper. No runtime reinstall or client reimport is needed. **Render trace** and **Managed diagnostics** are unnecessary for this focused test and should remain off.

## Validation and device comparison

The verification paths exercise helper summaries, independent network/plugin maxima, empty packets, nested network scopes and timing-state reset. Exact fixture verification checks the new packet wrapper, Draw/music timing, the inherited presentation override and preserved unrelated method/metadata content. Existing .NET/Wine checks cover packet budgeting, exception propagation and composed render instrumentation. Migration tests cover both legacy variants, option transitions and invalid original backups. CI runs these checks before packaging and publication; their final results are reported with the release.

Follow the [0.2.13 device checklist](UO-Memento-Mobile-0.2.13-Instructions.txt) at the existing 60 FPS and unchanged resolution/renderer/audio settings. Start a fresh client so the first route is cold. At each large pause, note the clock time and whether you moved into an area, crossed an interior entrance or triggered music. Repeat the same route and interior two or three times in the same process, then export support logs. The comparison should show which boundary grows only on the first visit before a loading change or more specific loader instrumentation is selected.
