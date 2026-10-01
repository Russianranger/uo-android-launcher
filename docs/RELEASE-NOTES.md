# UO Memento Mobile 0.2.11

The app is now **UO Memento Mobile**, with changed-region delivery for Native Surface. It keeps the existing Recovery application identity and signing certificate, so install this APK over your working app while keeping its data. Log out and save/stop first; no runtime reinstall or client reimport is required.

## Changed-frame delivery

- Exact changed bounds include the composited cursor and its old/new positions. Small updates can transfer a region; broad changes, first frames and resizes use full images.
- The receiver retains the complete image. Packed region rows arrive directly into that image, without a separate patch allocation or merge copy.
- Color conversion and writes cover Android's returned Surface dirty bounds, including any expansion needed for reused buffers. Surface recreation establishes a fresh full baseline.
- Existing unchanged-frame skipping, full X11 readback, capture compatibility and 30/60 pacing remain. The existing Wine/FEX runtime, graphics, audio, controller and game viewport settings remain.
- **Client → Client options → Send changed regions** defaults on. Turn it off and restart the client to compare original full-frame delivery. Older helpers negotiate the original full protocol; the standard display remains available for delivery errors.

## Measurement and checks

Capture/copy/Surface timings are retained. Sender logs add comparison/cache timing and delivered-byte accounting. Android logs add delivered/redrawn fractions, full/region frame counts, expanded redraws and incoming socket work. The gear view displays transferred/redrawn percentages.

Host checks exercise the actual JNI receiver against fragmented packets and buffer-age expansion. Real X11 checks cover both capture modes, both delivery modes, cursor changes, UI damage, broad updates, resize, reconnect and unchanged frames. CI builds/lints Android, checks the new app label/assets, retains the runtime regressions and verifies Recovery certificate continuity before publishing.

Device performance is still to be measured. Smaller transfers alone do not establish higher game FPS; full capture and Android buffer preservation can remain the main cost. Use the [device comparison checklist](https://github.com/Russianranger/uo-android-launcher/releases/download/v0.2.11/UO-Memento-Mobile-0.2.11-Instructions.txt) and [counter guide](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/OPTIMIZATION-0.2.11.md). Existing backup management, server settings, session controls and per-tab artwork are retained.
