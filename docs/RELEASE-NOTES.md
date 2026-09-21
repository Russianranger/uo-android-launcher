# UO Memento Recovery 0.2.8

Targets the remaining audio underruns after the 0.2.7 session settled down. It reduces playback socket-read overhead and requests audio priority for the playback worker. Device improvement remains to be measured.

## Install and test

1. Save and stop the realm and client. Install **UO-Memento-0.2.8-Recovery.apk** over Recovery, keeping app data. No runtime reinstall or client reimport is needed.
2. Leave **Smooth audio delivery** enabled. Keep WASAPI, client acceleration, Turnip / Native Surface, 30 FPS, music caching and smooth world loading at your existing settings.
3. Test music, short sound effects and the same walking route for 10–15 minutes. Compare the first few minutes with the settled session, then log out and export support logs.
4. If audio worsens, turn **Smooth audio delivery** off, stop and relaunch the client, and repeat the route. The setting takes effect at client launch and restores unbuffered reads and ordinary worker priority.
5. Open the world map, close it and reopen the same map without deleting its cache. Report a repeated long pause separately from first-time map image generation.

## Changes

- Read playback commands through a fixed 16 KiB input buffer to reduce underlying socket calls. Short reads are used immediately; the producer does not have to fill this buffer. Every protocol reply still flushes immediately, and PCM bytes, partial-write handling and the playback clock are preserved.
- Request Android audio priority only on the playback worker. If device policy declines it, playback continues at the available priority. The new switch controls this and buffered reads together.
- Add five-second diagnostics for interval underruns, sampled queue depth and actual input-stream read calls/bytes. Keep a bounded 512 KiB audio log so the added fields fit longer comparisons.
- Retain the tested 10 ms period / 40 ms audio ring and one-frame startup threshold on Android 12+. This does not repeat the 0.2.1 larger-buffer/startup-watermark experiment. Wine/FEX, native audio, graphics, controls and client patches are retained.

## World-map pause

The user identified the late pause in the 0.2.7 recording as opening the world map and generating its map image. The matched TazUO source already performs map-image loading/generation in a background task and reuses a PNG cache keyed by map data. First generation can still compete for CPU/memory, and texture loading may involve graphics-thread work. No map patch is included: a repeat opening will establish whether there is a recurring problem to fix. The trace does not prove that the full pause was GC or PNG generation alone.

## Verification and limits

Host tests compare buffered and unbuffered protocol replies, PCM bytes, partial acceptance, fragmented reads, invalid/truncated payloads, lifecycle handling and EOF cleanup. A real request/reply socket test sends short audio while waiting for every reply, checking that buffering does not introduce a fill requirement. A coalesced synthetic fixture reduces input calls from 122 to 6; this is not a Thor performance measurement.

CI also verifies UI defaults/persistence, Android build/lint and deployment, stable Recovery signing, native bridges, the real server, retained ARM64 runtime and managed/Wine client probes. Automated tests cannot establish audible improvement on the Thor. Exported logs distinguish queue starvation and transport timing but do not assign every delay to one component. See [investigation details](AUDIO-0.2.8.md).
