# UO Memento Recovery 0.2.2

Repair startup after interrupted TazUO configuration writes and revert the audio changes that sounded worse in 0.2.1. The Wine/FEX runtime, Turnip driver, original client graphics DLLs, controller mappings and 30 FPS pacing are retained.

## Update

1. Save/stop the realm and stop the client, then install this APK over **UO Memento Recovery**, keeping app data.
2. Launch normally. The app checks existing settings backups and restores the newest valid JSON object if `settings.json` is damaged or missing. **No runtime reinstall is needed.** With a valid backup, no client reimport is needed either.
3. Use **Turnip / Native Surface**, **30 FPS · cooler**, audio enabled, tracing/SDL replacement off, and **1280×720 / 1098×720 world + gump space**.
4. Settings changed since the recovered backup may need to be set again. If every backup is invalid or absent, the launcher keeps the damaged file and explains that a client settings backup is needed; it does not silently reset preferences.

## Changes

- Recover settings from the newest valid `.memento-last-good`, `.before-memento-pacing`, or `.before-memento` backup. Skip empty, truncated, zero-filled and non-object backups. Keep exact damaged bytes in a unique local `.interrupted-*` file.
- Save validated settings checkpoints before launch and after a clean client exit. A failed client write cannot replace the checkpoint. The viewport preparer also recovers damaged character profiles from their existing layout backup or last-good checkpoint, preserving other profile options and separate gump files.
- Write launcher JSON through unique temporary files; sync file contents and the containing directory after atomic replacement. Recovery paths stay inside the imported client. Support reports contain recovery reason/suffix and counts, never backup contents or credentials.
- Revert the 0.2.1 audio experiment: restore the native ALSA negotiation that gives Wine its requested 10 ms periods / 40 ms ring, Android's one-frame start threshold on Android 12+, and ordinary playback-worker scheduling. Keep real playback-head timing and queue-depth diagnostics. A versioned, checksum-verified audio bundle is deployed from this APK.

## Evidence and limits

The supplied 0.2.1 retries fail in `local_client_settings` while reading imported `settings.json`, before Wine starts. Pre-reset audio logging confirms the 80 ms ring and 20 ms start threshold, but only its first few seconds survive; several logs have zero-filled tails. This supports repairing interrupted configuration and rolling back the reported audio regression, but does not establish the mechanism of the sound distortion or device-wide input freeze during recording.

Verification covers interrupted/zero-filled/truncated settings, invalid backups, preference and damaged-byte preservation, profile recovery, path confinement, failed atomic replacement, actual ARM64 ALSA S16/float conversion with short writes, a 37-frame sound draining, APK deployment/signature continuity, and the unchanged .NET 10/FEX runtime directly and under PRoot. Android host/CI checks do not establish Thor audio quality, sustained performance, temperature, or recording stability. Please first compare ordinary gameplay without recording, then export support logs after stopping normally.
