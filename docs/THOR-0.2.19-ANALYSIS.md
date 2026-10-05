# Physical 0.2.19 cold-chunk attribution

Input: `logs-3033542933849450114.zip`, SHA-256 `c633407e92b1a7d6b99ac44b09a8c9a639e0b4cdd221656ec6e43b764946fd88`. Current `client-wine.log` activates managed revision 4 and native Vulkan revision 2. Current markers belong to the attempt beginning 2026-10-05 02:28:58 UTC. No old rotated session is needed for this attribution.

## Finding and first optimization

Repeated live `FileReader.Length` checks in `MapLoader.SanitizeMapIndex` dominate the slow map-1 chunks. Each fully textured map-1 chunk makes 705 sanitization calls, 704 neighboring height calls, 64 stretch calls and 2,115 original length getters (three per sanitization). Removing redundant length/availability metadata checks within a carefully bounded chunk-load lifetime is justified. The export does not justify changing the renderer or deferring gameplay/network processing.

| Main-thread scope | Chunk / stage / frame | Wall ms | Length self ms | Length share |
| --- | --- | ---: | ---: | ---: |
| Initial area fill | (430,428), fill, 2201 | 1,673.694 | 1,658.591 | 99.10% |
| Initial area draw | (432,427), draw, 2201 | 4,018.979 | 4,002.960 | 99.60% |
| Pre-marker area entry | (109,258), packet F3, 2394 | 3,556.655 | 3,542.013 | 99.59% |
| Marked cold interior | (463,435), packet F3, 5234 | 6,578.185 | 6,558.669 | 99.70% |

Map identity is input/world map 1 in all four. The initial map-0 chunk has zero length calls and does not exhibit this repetition.

Across the six emitted main-thread `CHUNK_WINDOW` records, 19 completed chunks account for 19,696.331 ms inclusive chunk wall; length self totals 19,330.088 ms (98.14%), with 38,070 length calls. This is summed serial main-thread work over the attempt, not one hitch duration. The three-part length checks are also ~97.98% of all emitted per-thread window chunk work. Background-thread durations overlap each other and main-thread durations: their sums must never be presented as elapsed loading time.

## Exact cold interior attribution

Marker `interior_cold` is 02:31:26.241332 UTC. Chunk 5234 ran approximately 02:31:29.956289 through 02:31:36.534474 UTC, reconstructed from `utc - end_to_log_ms - wall_ms`.

| Work requested for comparison | Evidence in/around this cold chunk |
| --- | --- |
| File lengths / filesystem metadata | 2,115 getters, 6,558.669 ms self, maximum one getter 151.165 ms; dominant. |
| Actual bulk reads | Chunk unassigned work is 0.703 ms; terrain-height self includes uninstrumented generic map-block pointer access. Resource window spanning the cold chunks has 49,504 `file_read` calls totaling 14.951 ms and two `mapped_read_at` calls totaling 0.045 ms. Initial generic map reads are not fully covered; those resource categories must not be summed as complete map I/O attribution. |
| MUL/UOP lookup | No separate complete lookup probe. Existing resource art lookup window self is 0.017 ms; animation-MUL decode self 1.101 ms. The chunk's non-length remainder is only 19.516 ms, so uninstrumented lookup cannot explain its 6.58 seconds. |
| Terrain / height processing | 704 `get_tile_z` calls, inclusive 6,571.406 ms but self only 5.927 ms; nearly all inclusive cost is its nested sanitize/length work. |
| Stretch calculation | 64 calls, inclusive 6,573.799 ms but self only 2.393 ms. |
| Land/static object construction | 64 lands self 0.252 ms, 8 statics self 0.021 ms. |
| Tile insertion | 72 calls self 0.245 ms; markers self 0.054 ms. |
| Texture/resource decode | Nearby resource window land decode self 5.263 ms, static decode self 4.282 ms; no decode dominates the cold chunk. |
| Allocation / GC | Chunk resource scope allocates 16,536 bytes; whole frame 579,888 bytes. Whole-process GC pause measured across frame 44.754 ms (overlapping elapsed duration), insufficient for the 6.58-second chunk. |
| FNA / graphics upload | Chunk `nested_fna_ms=0`; frame native total 38.401 ms, max 36.553 ms; 33 atlas uploads / 434,796 bytes occur elsewhere in frame. |
| Native / Vulkan waits | At 02:31:36.547 the surrounding 10.056-second window has `vkWaitForFences` max 4.358 ms, queue-submit max 4.485 ms and present max 66.160 ms. No multi-second native wait appears; accumulated present timing includes normal presentation across many frames. |
| Server / network wait | Packet F3 max 6,578.426 ms; enclosing network resource wall 6,578.450 ms, self only 0.194 ms, nested chunk 6,578.194 ms. This is a synchronous client map load performed inside packet handling, not measured time waiting for a server response. |

Chunk `sanitize_map_index` self is 9.921 ms; inclusive is 6,568.590 ms because it contains the original length getters. All child parts and resource/frame/network scopes overlap; use part self and root boundaries, not the sum of inclusive timings.

Whole cold frame gap is 6,827.680 ms; frame thread CPU 190 ms, frame bookkeeping 32.720 ms, resource observer 3.836 ms and chunk observer 10.559 ms. Chunk-scope observer is 9.331 ms. Observer figures also overlap and cannot be universally subtracted or added; none is remotely close to the six-second metadata contribution. Scope/part depth overflow is zero for all emitted windows.

Process health is ancillary: samples at 02:31:31, :33 and :35 show `read_bytes` fixed at 317,444,096 during the stall, consistent with the lack of large bulk reads. Child-process discovery is explicitly unavailable and samples are sparse; do not infer complete process-tree I/O or exact syscall cause from this alone.

## Startup baseline

The app attempt begins 02:28:58 UTC. First emitted managed frame is 02:29:45.528 UTC (47.528 seconds after attempt start), and first nonzero managed Draw frame is 02:29:45.782 UTC. First initial-world chunk begins approximately 02:30:00.152 UTC (62.152 seconds after attempt start). These are observed telemetry boundaries, not a direct login-screen-ready marker or a stopwatch excluding user input. Startup successfully progressed into world loading and both marked play phases; the export does not show a return to the previous startup black-screen regression. Compare the next build using the same physical stopwatch points.

## Outdoor and warm comparisons

Markers are outdoor cold 02:30:30.496, outdoor warm 02:31:05.679, interior cold 02:31:26.241, interior exit 02:31:55.840, interior warm 02:32:01.748, finished 02:32:08.981 UTC.

The initial area and pre-marker chunks happen before the first outdoor marker; do not relabel them as within the marked outdoor interval. They still demonstrate large map loads in fill/draw and packet stages. The initial area frame 2201 detail was capped, but `COLD_WINDOW` at 02:30:16.613 records max gap 12,106.955 ms and seven suppressed long-frame records. Two separately observed serial main-thread chunks explain 5,692.672 ms of that frame, 5,661.551 ms of which is length self; the rest of the 12.1 seconds is outside these two chunk boundaries and is not claimed as exclusively metadata.

The marked outdoor-cold interval has 117 recorded background chunk details, maximum 1,230.968 ms, but no slow main-thread chunk detail; frame gaps max 375.825 ms in recorded details. Background length self is 81,769.565 ms versus 83,463.404 ms summed chunk wall (~97.97%), concurrent across threads. Warm outdoor has no chunk loads recorded and no frame detail >=50 ms; complete windows inside the warm interval have maxima 44.982, 49.026 and 43.234 ms, with zero gaps >=50 ms.

Marked cold interior has two main-thread chunks, including the confirmed 6.58-second stall. Warm interior has no slow chunk details; its single long-frame detail is 50.972 ms with zero chunk trace work and no resource load dominating. The fully warm window ending 02:32:06.794 has max gap 42.014 ms. The previous window ending 02:32:01.792 crosses the warm marker and includes a 92.716-ms GC pause during the earlier exit phase; do not attribute that to warm re-entry.

## Comparison limits and preservation

`CHUNK_LOAD` details are capped; all window aggregates preserve suppressed calls but some worker-thread final partial windows are not emitted. There are 292 detail records, 89 window records and nine chunk-detail suppressions. Main thread has 14 details and six windows containing 19 completed loads; five suppressed main-thread details occur in its first window, and four other suppressions occur on worker threads. The main-thread 19 completed loads include one map-0 chunk without length checks and 18 map-1 chunks (18 × 2,115 = 38,070 length calls). Do not add detail plus window counts. All windows contain 299 completed calls across threads; that sum is not the complete attempted call total because final worker-thread partial windows are not necessarily emitted. Child IDs identify scopes per managed thread, not persistent map objects.

The finding supports reducing repeated metadata checks while keeping actual data reads, original fallback/short-circuit ordering, live growth/empty transitions, reader replacement/disposal and exceptions correct. Cache scope or immutable-reader snapshot semantics must be tested explicitly, with no process-wide permanent freezing of live lengths. Preserve revision-4 telemetry, original 0.2.19 fallback and disabled resource CPU queries so the physical next build can compare both paths.
