# UO Memento Recovery 0.2.5

A narrow efficiency update on the successful 0.2.4 baseline. The Thor user reported substantially improved loading and sound, with temperatures in the low 50°C range on 0.2.4; further device gains from this update are not yet measured.

## Install

Stop the client, save/stop the realm, then install **UO-Memento-0.2.5-Recovery.apk** over Recovery. Keep app data. No runtime reinstall, client reimport or world migration is required.

Keep **Client acceleration**, **WASAPI**, **Turnip / Native Surface**, **30 FPS** and **1280×720 / 1098×720 world + gump space**. Wine/FEX, drivers, controls, audio format, the 40 ms producer buffer and Android start threshold are unchanged.

## Changes

- Remove the second scan of every accepted audio sample. Preserve progress and whole-session signal counters.
- Add interval audio delivery-gap, write-duration and partial/zero-write counters to support logs. Pauses and initial priming are excluded from gap measurements. No extra timers or per-write log output.
- Cache X11 window attributes and cursor images. Refresh on resize/cursor notifications and every two seconds as a fallback. Continue checking pointer position on every display request, with the existing full-pixel capture, exact duplicate comparison and frame limits.
- Build and package the updated ARM64 display bridge, with checksum verification and real X11 tests for shared-memory and fallback capture, cursor movement/shape, clipping, resize and reconnect.

## Music optimization pending one file

The source change in `patches/tazuo-music-cache.patch` performs one recursive music-directory enumeration per load, preserving existing filename matching, ordering, ambiguity warnings and missing-track behavior. It is **not applied by this APK**. The loader belongs to `ClassicUO.Assets.dll`, not the earlier uploaded `TazUO.dll`. The exact imported Assets DLL is needed to generate and verify its reversible binary patch; substituting a different upstream build would change more of the working client.

## Verification limits

Automated gates cover the audio protocol, delivery counters, X11 capture, Android build/lint/signing continuity, existing recovery paths and the retained ARM64 Wine/FEX runtime in both PRoot modes. They do not measure Thor thermals or Android speaker quality. Compare a normal session and export support logs after stopping.
