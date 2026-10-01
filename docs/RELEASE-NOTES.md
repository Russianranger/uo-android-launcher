# UO Memento Mobile 0.2.12

This update fixes repeated Native Surface buffer setup. Install it over your working app after logging out and saving/stopping the session, keeping app data. The existing application identity and signing certificate are retained; no runtime reinstall or client reimport is required.

## Surface configuration

The 0.2.11 Thor session recorded 4,068 Surface posts and 4,068 geometry setup calls. Region delivery saved 34.4% of pixel traffic, but every post still converted/redrew the full image. The receiver compared window query dimensions against game-buffer dimensions; the displayed view and configured image buffers can have different sizes.

The receiver now uses the existing per-Surface reader cache to remember successful buffer configuration. Setup runs for a fresh reader or an actual game-resolution change. Routine region updates and broad full frames at the same resolution retain their configuration. The retained image is still used to redraw Android's actual returned bounds, including buffer-age expansion, and actual locked-buffer dimensions/format are still validated.

This pass changes Surface geometry tracking only. Frame pacing, asset preparation, managed client patches, full X11 capture, graphics, audio, controller, backup/settings/session features and tab artwork retain their existing behavior.

## Verification and device comparison

The native receiver regression now models different view and buffer sizes. It fails on the 0.2.11 receiver and passes with this fix. It checks one initial setup, localized conversion, onscreen view changes, broad frames, actual resolution changes, fresh readers and buffer-age expansion alongside the existing socket and invalid-packet checks. CI rebuilds both native presentation endpoints, packages the current Android receiver, and checks Android build/lint and signing continuity before release.

Leave **Send changed regions** enabled. In support logs, `buffer_reconfigurations` should be zero in steady-state measurement windows after initial setup, with a setup again after a new Surface reader or game-resolution change. Small cursor/gump changes can lower the redrawn fraction; Android may still expand bounds. Walking/broad animation can still redraw the full image. Device stutter/FPS improvements require testing.

Use the [device checklist](https://github.com/Russianranger/uo-android-launcher/releases/download/v0.2.12/UO-Memento-Mobile-0.2.12-Instructions.txt) and [fix/counter details](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/OPTIMIZATION-0.2.12.md).
