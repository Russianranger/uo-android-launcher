# UO Memento Recovery 0.2.4

Targets long loading times, uneven FPS and garbled audio while retaining the device-tested native Wine/FEX runtime.

## Install and compare

Install **UO-Memento-0.2.4-Recovery.apk** over the existing Recovery app after stopping the client and saving/stopping the realm. Keep app data. No runtime reinstall, client reimport or world migration is required.

Use **Client acceleration** on, **WASAPI · recommended**, **Turnip / Native Surface**, **30 FPS · cooler**, and **1280×720 / 1098×720 world + gump space**. The two new options default to acceleration on and WASAPI. Existing display, layout, controller and tracing preferences persist.

## Changes

- Allow PRoot's supported-kernel syscall acceleration for the client. Previously every client launch forced it off. PRoot retains its built-in fallback when unavailable; the new Client acceleration switch restores the previous full-trace mode for comparison. The realm's execution policy is unchanged.
- Use WASAPI instead of forcing DirectSound. Set both SDL 2 and SDL 3 driver hints so imported audio libraries use the same selection. DirectSound remains selectable. The ALSA/AudioTrack bridge, 48 kHz stereo format and 0.2.2 buffering policy are retained.
- Reuse a healthy Wine prefix after validating its ready revision, all three registry hives and kernel32. Skip repeated wineboot/command/shutdown cycles. Corrupt or incomplete prefixes still take the preservation and repair path introduced in 0.2.3.
- Record startup phase elapsed times, requested audio backend and acceleration selection. The PRoot log records when acceleration is actually observed.

## Verification and limits

Release gates cover prefix reuse and interrupted-file recovery, option defaults/persistence, Android build/signature continuity, and the exact retained ARM64 Wine/FEX runtime in both compatibility and accelerated PRoot modes. Runtime probes exercise .NET 10 JIT/GC, Vulkan texture lifetime and Windows WASAPI through the real ALSA bridge. Synthetic 440/660 Hz stereo tones check playback rate, channel separation, level and duration against a clocked protocol sink.

The probes do not reproduce Android speaker output, a live Memento world, recording or Thor thermals. Improvements must be measured on the device; this is not a claim that audio distortion is eliminated or that the old setup's low-50°C range has been reached. See [session evidence](OPTIMIZATION-0.2.4.md).
