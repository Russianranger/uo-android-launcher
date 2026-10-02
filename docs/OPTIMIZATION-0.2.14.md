# First-use atlas upload batching

## Evidence and target

The 0.2.13 Thor session started at 2026-10-02 18:49:32 UTC with 60 FPS, Turnip, Native Surface and revision 2 load timings. Repeat visits were reported smooth. Of 23 gameplay measurement windows, 16 had update gaps above 100 ms and 16 had FNA EndDraw maxima above 100 ms; only two had Update maxima above 100 ms. Typical exploration windows reached 104–288 ms in EndDraw while Update stayed at 4–37 ms. Warm sections were approximately 8–17 ms in EndDraw. A larger window included a 541 ms EndDraw maximum and a 167 ms F3 handler; the 1,676 ms update gap is not fully explained by these individual maxima. F3 reached 811 ms in an earlier first-use item update.

Android presentation remains inexpensive: 6,354 posts, one initial buffer configuration and no ongoing configuration; weighted copy/post were 0.416/0.338 ms. These five-second maxima identify substantial client/graphics work but do not establish that atlas uploads are its only cause.

The exact client TextureAtlas.AddSprite sends one SetDataPointerEXT per new sprite. Native FNA3D 25.11 submits its upload command buffer before rendering, and SDL's Vulkan upload path transitions a texture subresource around each partial copy. Combining adjacent new sprite writes reduces upload commands and transitions without changing asset decoding or frame pacing. Shader compilation and other driver waits remain possible contributors.

## Pixel and ordering guarantees

The helper stages uploads only in the existing timed GameController.Draw scope when enabled for the exact supported Turnip path. The pinned packer reserves a one-pixel border around each new sprite. Staging copies the sprite pixels unchanged and initializes only that newly reserved border to transparent. Those owned padded rectangles can merge across a complete shared edge with matching width or height; a merged upload has no holes and cannot overwrite another sprite or its reserved border. UVs and packing are unchanged. The Utility DLL is checksum-gated as well, so a different packer cannot activate this path. There is no historical full-atlas shadow to become stale after cave-border filtering or custom art mutation.

Pending pixel payloads, including reserved margins, are bounded to 4 MiB and 256 entries. ArrayPool may retain larger buckets, and merging can briefly use a second buffer; this limit is not a cap on total process memory. Oversized or unsupported writes retain the immediate path, committing earlier queued writes first. Pooled buffers are returned after flushes/failures; warm frames add no pixel allocation. Native upload failures propagate. Draw-scope cleanup performs bookkeeping and protected optional reporting only, and issues no GPU calls while the original Draw exception unwinds. Empty native flushes return without reading the clock.

EndDraw-only flushing would be incorrect: first-use PNG processing, minimap creation and atlas export can read pixels and submit rendering earlier. The FNA patch flushes before native drawing, readback, texture and buffer mutation, render-target resolve/reset, presentation and lifetime boundaries. An additional managed Texture.Dispose entry flush precedes clearing the texture handle. Disposed textures/devices are discarded rather than uploaded. Original native functions execute once with unchanged arguments, entry points and calling conventions. Partial updates retain original cycling behavior.

## Deployment and recovery

The APK contains a helper and two bounded BSDIFF deltas for original FNA and ClassicUO.Renderer libraries, preserving assembly identities and unrelated code/resources/constants. Complete client DLLs are not shipped. Before changing either library, the launcher validates original backups, verifies helpers and computes/checks both outputs. Each replacement is atomic. A failed later write leaves verified originals available for next-launch or disable recovery.

The TazUO packet-budget patch/checksum remains unchanged. The timing helper gains optional Draw callbacks without a graphics dependency; a separate startup hook registers after it. Activation requires the supported TazUO/FNA/Renderer/Utility/FNA3D/SDL set, Turnip and Smooth world loading. Disabling that option, changing renderer or encountering an unsupported component restores only recognized patched libraries and preserves unknown files.

## Verification and comparison

Helper tests compare resulting pixels with immediate uploads for adjacent rows, holes, overlaps, varied sizes, buffer reuse and mixed textures. They cover limits, exceptions, ordering, thread isolation and warm allocations. The actual imported Renderer.AddSprite and Utility packer reduce twelve 8x8 sprite uploads to one 60x20 upload. All 768 sprite pixels and UV rectangles remain unchanged; fresh reserved margins become transparent, and a historical texel outside them survives. This is an upload-count test using a native C shim, not a GPU timing benchmark. Exact assembly verification checks allowed changes and native ABI metadata. Real FNA/Renderer probes execute wrapped boundaries and reentrant flushing under .NET and Wine. Production checks regenerate/apply shipped deltas and restore both libraries. APK gates verify deployed assets, app identity, signature and certificate continuity.

Automated upload reduction is separate from a measured improvement on Thor. Follow the [device checklist](UO-Memento-Mobile-0.2.14-Instructions.txt) at unchanged settings and export Journal logs. New upload summaries retain the previous packet, Draw and EndDraw measurements so remaining CPU or driver stalls remain visible.
