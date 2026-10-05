# Scoped map metadata reuse in 0.2.20

The [physical 0.2.19 export](THOR-0.2.19-ANALYSIS.md) identifies the first optimization: one cold interior `Chunk.Load` spent 6,558.669 of 6,578.185 ms inside 2,115 file-length getters. Initial-area chunks show the same pattern. Those calls occur in `MapLoader.SanitizeMapIndex`, repeatedly reached through neighboring terrain heights and stretching. Their nested inclusive timings are not additional terrain costs. This release reduces that repetition without changing the renderer, packet budget or actual asset reads.

## Lifetime and invalidation

For the exact supported client, each synchronous `Chunk.Load` starts an independent metadata scope on its originating thread. Only the three original `FileReader.Length` call sites inside `MapLoader.SanitizeMapIndex` use it. A successful getter result may be reused for that original reader during the current chunk. The general getter remains unchanged: startup, ordinary file reads, other length users and calls outside a chunk remain live.

The first access still calls the original getter. Exceptions are not cached. A disposed backing stream bypasses reuse and reaches the original getter's exception behavior. Replacing a reader uses its new identity and obtains a new length. The scope ends in `finally`, including early returns and exceptions, and releases its reader references. Nested chunks have independent scopes; background and frame threads never share snapshots. Capacity overflow falls back to live getters.

This is a per-chunk snapshot, not a session-wide file-length cache. File growth or truncation on the same open reader during construction becomes visible on its next chunk scope; a new reader is visible immediately. This bounded snapshot is deliberate: a chunk is constructed from one consistent map-availability decision. It does not prevent UltimaLive writes or persist across chunks, area changes, client restarts or imports. Concurrent destruction/replacement of mapped data remains subject to the original client's data-access lifetime rules.

The exact-client host qualification reduces a map-1 chunk's 2,115 original length calls to three across all 12 ordinary/render/diagnostic cases, with identical terrain, static-object and tile fingerprints. This is a measured call-count reduction, not a claim that every cold hitch disappears. The export contains smaller graphics tails and an initial frame with work outside the observed chunks.

## Activation and comparison

**Client options → Faster map loading** defaults ON. It requires the existing supported Smooth world loading client. Turning it OFF and restarting the client restores the exact previous client and Assets assemblies, independently of the cold-timing switch. Existing revision-4 managed / revision-2 native diagnostics remain available on either path. No resource-scoped CPU queries are added.

Eight checksum-qualified deltas support the ordinary and render-traced frame-budget clients, the original and music-cached Assets libraries, and their unchanged 0.2.19 diagnostic variants. Only the chunk lifetime and the sanitizer's length call sites change. Imported unknown assemblies are preserved. All selected inputs, outputs and existing backups are validated before activation writes. Every verified input is backed up before either assembly is replaced. An interrupted activation or restoration is repaired on the next launch.

At launch the metadata layer is restored first, followed by the existing diagnostic restoration and ordinary client/music/atlas selection. Cold diagnostics are configured as before; metadata reuse is then selected last. This preserves all prior diagnostic hashes and deltas without replacing the accepted Wine/FEX runtime, original SDL, FNA/Turnip configuration, Surface delivery/cache, audio, controls, server, world saves or signing identity.

## Qualification and physical check

The new gate exercises exact client and Assets methods, live lengths outside scopes, map-0/map-1 fallback and short-circuit behavior, three-versus-2,115 getter counts, growth/truncation on subsequent chunks, replacement/disposal, exceptions, nested scopes, thread isolation, capacity overflow, terrain/object/tile equivalence and restoration. It runs under host .NET, retained Wine, ARM64 Wine/FEX and both PRoot modes. The packaged APK gate reconstructs supported inputs and applies the shipped deltas. Existing startup, resource, atlas, graphics, Surface, audio, input, server, Android build/lint and certificate-continuity gates remain required before publication.

Use the [focused Thor procedure](UO-Memento-Mobile-0.2.20-Instructions.txt). Physical improvement remains to be measured. The existing 0.2.19 export supplies the before baseline; a second new baseline run is unnecessary unless the optimized result needs investigation.
