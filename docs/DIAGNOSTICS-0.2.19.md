# Focused chunk-loading diagnostics in 0.2.19

The [marked 0.2.18 Thor test](THOR-0.2.18-ANALYSIS.md) confirms startup recovery and smooth warm revisits, while locating a 6.75-second interior packet stall and two substantial outdoor Draw stalls inside synchronous `Chunk.Load`. This release adds attribution within that measured boundary. It makes no resource-caching or gameplay scheduling change.

Exact imported client IL shows that terrain stretching repeatedly reads neighboring heights. On map index 1, those height queries check three write-shared file lengths through `MapLoader.SanitizeMapIndex`. Up to 2,115 length queries can occur when constructing one fully textured chunk. The current export does not record the active map or those checks' wall time, so this is a candidate to measure, not a proven cause.

Managed diagnostics use revision 4. The native Vulkan observer remains revision 2. Existing resource, frame, packet, FNA, atlas, GC, CPU, music, health and Android presentation observations remain. Resource CPU queries remain disabled to avoid the 0.2.17 startup regression.

## Measurement requirements

`CHUNK_LOAD` records completed chunk scopes >=50 ms. Identity includes originating managed thread, frame/stage, `chunk_id`, `parent_chunk_id`, nesting depth, input/world map indices, chunk coordinates and radar-update flag. IDs are load-call tokens unique within that thread, not persistent world-object IDs. World-map index is observed from the local produced by the original getter; `-1` means unavailable. No getter is moved or repeated.

Each record includes `wall_ms`, non-overlapping root-part wall in `parts_root_ms`, `unassigned_ms`, observer overhead, frame offset and reporting delay. Part fields have `_calls`, inclusive `_ms`, `_self_ms` and `_max_ms` suffixes:

| Part | Original method |
| --- | --- |
| `sanitize_map_index` | `MapLoader.SanitizeMapIndex` |
| `file_length` | `FileReader.Length` |
| `get_tile_z` | `Map.GetTileZ` |
| `apply_stretch` | `Land.ApplyStretch` |
| `land_create` / `static_create` | Original land/static factories |
| `tile_insert` | `Chunk.AddGameObject` |
| `tile_marker` | `TileMarkerManager.IsTileMarked` |

Part self time excludes observed child parts; inclusive and nested timings overlap. They must not be added together or treated as CPU/GPU duration. `get_tile_z` includes subsequent generic map-block reads, while the initial generic `Chunk.Load` map-block read remains unassigned. Marker type initialization before `IsTileMarked`, static-buffer reads and other unobserved work also remain unassigned. Generic mapped reads use direct pointer access and can incur page faults. Existing ResourceTrace and ChunkTrace use separate hierarchies; their self/root fields are not an additive attribution.

Chunk summaries have their own eight-record limit per nominal five-second window/thread. Frequent child calls aggregate without consuming the existing resource slow-detail limit. `CHUNK_WINDOW` retains all completed call counts, inclusive chunk wall, chunk maximum, slow-call count and part aggregates, including suppressed details. `CHUNK_LIMITS` reports actual window duration, observer overhead, slow suppression and stack overflows. Fixed thread-local storage allows eight nested chunks and 32 nested parts; overflow is explicit. Output waits for the enclosing ResourceTrace root to finish its original cleanup, and windows can extend beyond five seconds or wait for later resource activity. Align windows using their actual duration rather than assuming periodic sampling.

`COLD_FRAME.chunk_trace_overhead_ms` reports frame-thread chunk observation/output cost. Scope, chunk-window and existing resource/frame overhead can overlap; do not add them or universally subtract them from original inclusive times. Chunk/resource CPU fields remain explicitly unavailable. No packet payloads, account credentials or file paths are collected in these focused records.

The instrumentation must forward every original call once, preserving arguments, results, short-circuit/fallback behavior and exceptions. It does not freeze file lengths: live file growth, map replacement and UltimaLive behavior remain unchanged. Older .17/.18 resource hashes remain recognized for verified restoration before .19 activation; unknown assemblies are preserved.

## Qualification and Thor test

Qualification covers exact patched methods and the previous startup-shaped readers/loaders in enabled and disabled modes, including map 0/map 1, null/empty/nonempty fallback files, live growth, exception propagation, nested/chunk-thread attribution, reporting caps and observer overhead. Existing atlas, graphics, runtime, signing, input, audio, Surface and upgrade gates remain required. Retained Wine/FEX and both PRoot modes execute the fixture separately from host checks.

Install over 0.2.18 and use the [marked test procedure](UO-Memento-Mobile-0.2.19-Instructions.txt). Keep optional SDL OFF and all working settings. Export the complete ZIP after cold outdoor/interior and warm retrace/re-entry phases, then disable cold timing for normal play. Device telemetry, not the existence of new diagnostic records, determines the next optimization.
