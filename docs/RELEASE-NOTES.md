# UO Memento Recovery 0.2.1

Audio buffering and cooler frame pacing for the Wine/FEX runtime that now reaches the world reliably on Thor. The Wine/FEX binaries, original graphics DLLs and Turnip driver are retained exactly from 0.2.0.

## Update

1. Save/stop the realm and stop the client, then install this APK over **UO Memento Recovery**, keeping app data.
2. **Do not reinstall the FEX runtime.** The updated audio bridge is included in the APK. Existing imports, saves and controller mappings remain in place.
3. Launch with **Turnip / Native Surface**, **30 FPS · cooler**, audio enabled, and tracing/SDL replacement off. Keep **1280×720 / 1098×720 world + gump space**.
4. Compare audio, responsiveness and temperature over a similar 15–20 minute session. **60 FPS · smoother** remains selectable and its choice persists after restart.

## Changes

- The frame target now applies to TazUO's own `fps` setting and display capture together. Upgrades start at 30 FPS once; an explicit later 60 FPS selection is respected. The original settings file is backed up before pacing changes.
- Native Surface disables TigerVNC's redundant framebuffer comparison. The separate RFB input connection and display fallback remain available; the native bridge still compares exact pixels.
- The native ALSA bridge negotiates a minimum 20 ms period and 80 ms buffer. Android primes up to 20 ms before playback, bounded by the producer ring, and the playback worker uses audio thread priority. Sample rate, channels and playback clock remain unchanged.
- Audio logs include queue depth for the next comparison.

The supplied 0.2.0 session stopped cleanly. Its audio log recorded 42 underruns; a later active display interval averaged about 23 new frames/s versus 46 captures/s. These are transport counts, not measured game FPS. Underruns support a buffering problem, but do not prove that every audible distortion has the same cause.

## Verification and limits

Release checks cover actual ARM64 ALSA S16/float conversion, exact stereo sample order with short writes and backpressure, natural drain, bounded Android priming, settings migration, UI, APK packaging/signature continuity, and the retained .NET 10/FEX runtime directly and under PRoot.

Audio clarity, sustained responsiveness and temperature improvement need another Thor session. No specific FPS gain or return to low-50°C temperatures is claimed. APK and native-bridge sources are included; the runtime and its corresponding Wine/FEX sources are the checksum-verified 0.2.0 assets.
