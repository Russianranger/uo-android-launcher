# UO Memento Recovery 0.2.6

Completes the music-loading optimization and includes the audio/display efficiency changes from 0.2.5. The successful Wine/FEX runtime, WASAPI, acceleration, 40 ms audio buffer, 30 FPS default and 1098×720 world inside the 1280×720 canvas are retained.

## Install and use

Stop the client and save/stop the realm, then install **UO-Memento-0.2.6-Recovery.apk** over Recovery. Keep app data. You can update directly from 0.2.4; no client reimport, runtime reinstall or world migration is required.

Keep **Cache music folder during loading** enabled. After launch, its status says whether the cache is active. The original Assets DLL is backed up before replacement. Turn the switch off and relaunch to restore it. Other client builds are left as imported.

## Changes

- On the supported TazUO 5.2.0 Assets assembly, enumerate the music directory once per load. Preserve recursive search, original ordering, regex matching, ambiguity warnings and missing-track results. Reset the cache on Load and ClearResources.
- The patch has exact input/output SHA-256 guards and atomic replacement with an original backup. It adds one private array and one private helper; it has no new DLL dependency, worker, timer or graphics change. TazUO render tracing remains independent.
- Retain 0.2.5's single audio sample scan and interval delivery-gap/write counters, plus event-driven X11 window/cursor caches with per-request pointer tracking and a two-second refresh fallback.

## Verification and limits

The public Memento client package contains TazUO.dll and FNA.dll matching the user's uploaded binaries exactly. Its Assets DLL is the sole supported input; no assumption about other Assets builds is made.

Verification compares original and patched assembly metadata, constants, resources and method bodies: 439 original methods are unchanged, with only the three intended loader methods changed. Real-assembly probes under .NET and Windows Wine exercise configuration results, regex/case/duplicate matching, repeated lookup, new tracks, reload, changed asset roots, ClearResources and missing-directory errors. The shipped delta is regenerated and compared byte-for-byte, applied twice, and restored to the original bytes. Python checks cover unknown updates, invalid backups, corrupt deltas and interrupted replacement.

Android build/lint/deployment/signature checks, real ARM64 display/audio probes and retained Wine/FEX runtime gates remain required. These do not measure Thor speaker quality, thermals or a live world session. Further gains beyond the user's successful 0.2.4 session still need device testing.
