# Chunk-scoped map metadata snapshots

The first physical 0.2.19 export attributes the dominant synchronous chunk
stall to repeated `FileReader.Length` calls underneath `SanitizeMapIndex`.
This patch forwards only the three exact sanitizer call sites through a
successful-result snapshot scoped to one synchronous `Chunk.Load` call.

`Memento.ChunkMetadata` keeps separate thread-local and nested-chunk snapshots,
keyed by original reader identity. A replacement reader cannot reuse another
reader's value. Every new or nested chunk starts fresh; exceptions and early
returns clear reader/stream references in an injected outer `finally`.
Snapshots intentionally retain the first successful length for an existing
reader for the remainder of that one chunk. Growth/truncation is visible on
the next chunk, and outside that chunk every original sanitizer call is live.
Within-chunk disposal is checked using the captured backing `FileStream`'s
in-memory `CanRead`: a disposed stream bypasses the snapshot and preserves the
original `Length` exception. The exact private readonly stream field is read
once on admission; unknown reader shapes are not cached. Failed getter calls
are never cached.

The cache is bounded to eight nested chunks and sixteen reader identities per
chunk. Unexpected deeper chunks or extra readers safely use the original getter
until the scope unwinds. Warm cache hits allocate no managed objects, strings,
arrays, or delegates. The helper has no diagnostic-mode or environment-variable
dependency; the launcher's independent reversible binary selection controls it.

Eight exact base hashes cover accepted frame/frame+render clients, original /
music-cache Assets, and the matching unchanged 0.2.19 resource diagnostic
outputs. No IO, lookup, decode, terrain, object, tile, FNA, GPU or native code is
modified. Existing 0.2.19 instrumentation stays in place and measures only the
remaining actual length getter misses. `MapMetadataVerify` checks every
unrelated body, constant, resource, ABI and original exception region, the
three forwarding sites, the successful-only store order, and the new finally.

ABI in existing `Memento.FrameBudget, Version=1.0.0.0`:

- `long ChunkMetadata.Begin()`
- `void ChunkMetadata.End(long token)`
- `bool ChunkMetadata.TryGet(object reader, out long length)`
- `void ChunkMetadata.Store(object reader, long length)`

Run the preceding resource qualification gate, then
`scripts/check-map-metadata.sh` for the exact eight-output/delta structural
checks, real vendor MUL/static fixtures, host and Wine behavior. The dedicated
probe also qualifies nested snapshots, refresh, replacements, disposed readers,
failed getters, overflow, thread isolation, allocation-free hits and exception
cleanup. `--host-only` omits Wine. `generate-map-metadata-deltas.py` is the
explicit developer generation command after the patcher outputs have passed
structural verification; ordinary gates verify committed bytes without mutation.
