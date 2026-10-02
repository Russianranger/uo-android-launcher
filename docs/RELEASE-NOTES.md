# UO Memento Mobile 0.2.13

This update adds focused diagnostics for the severe pauses when visiting new areas or entering interiors for the first time. It is a measurement build, not a claimed loading-performance fix. Install it over your working app after logging out and saving/stopping the session, keeping app data. The application identity and signing certificate are retained; no runtime reinstall or client reimport is required.

## What the latest device logs establish

The 0.2.12 logs show zero repeated Surface buffer configuration during steady gameplay, confirming the previous receiver fix. First-visit pauses remain: one network-processing call took 4,489 ms inside a 4,498 ms update. Other cold frame gaps of roughly 419–980 ms occurred outside the measured update work, compared with roughly 29–44 ms on warm sections. Startup scene loading and draw-list filling reached approximately 1,040 ms and 401 ms. These timings locate some work on the main thread but do not yet identify its specific cause.

## New load boundaries

The existing **Smooth world loading** helper now records registered packet-handler dispatch timing, the slowest packet ID and separate network/plugin summaries. It also times `GameController.Draw`, the inherited FNA `EndDraw` presentation boundary and `AudioManager.PlayMusic`. Together with the retained update/network/scene/load/fill/audio and GC-count summaries, these boundaries separate registered handler dispatch from other packet-processing work and from drawing, presentation or music switching. Packet logging, plugin receive filters and parser lock/copy work remain outside the handler boundary; a long network time with a short handler time points to that remaining work.

The helper keeps one summary per five seconds, retaining only packet IDs, counts and timings; it does not log packet contents or every handler call. It adds no background loader or graphics calls and preserves the existing 5 ms / 1,000-packet budget. That budget checks between packets and cannot interrupt a single slow handler. This build does not change asset preparation, textures, frame pacing or audio delivery.

The launcher recognizes the previous exact frame-budget and combined render-budget revisions, verifies their preserved original client backup and upgrades from that original. Original and render-only states remain reversible. Unrecognized client binaries are left unchanged. The additional summaries require **Smooth world loading** on and the exact supported TazUO 5.2.0 / FNA binaries.

## Device test

Keep the existing 60 FPS, resolution, graphics and audio settings. Leave **Smooth world loading** on and **Render trace** / **Managed diagnostics** off. Start a fresh client, enter the world, follow an unvisited route and enter an interior. Note the clock time and action at each jarring pause. Repeat the same route and interior two or three times without closing the client, then export support logs from Journal. No new setup or diagnostic toggle is needed.

Use the [device checklist](https://github.com/Russianranger/uo-android-launcher/releases/download/v0.2.13/UO-Memento-Mobile-0.2.13-Instructions.txt) and [diagnostic design](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/OPTIMIZATION-0.2.13.md). Release validation is documented with the source; device performance conclusions depend on the new cold/warm comparison.
