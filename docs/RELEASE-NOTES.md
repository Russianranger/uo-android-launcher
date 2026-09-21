# UO Memento Recovery 0.2.7

Targets the remaining stutters while receiving world data, using the successful 0.2.6 runtime and settings.

## Install and test

Save and stop the realm and client, then install **UO-Memento-0.2.7-Recovery.apk** over Recovery without clearing app data. No client import or runtime reinstall is required.

Leave **Smooth world loading** enabled. Keep your existing FPS, renderer, WASAPI audio and viewport settings. Walk into the same interiors and back outside, check music/effects and controller response, then log out and export support logs. The status below the switch confirms activation for the supported DLL. Turn it off and relaunch to restore original packet handling for comparison; the music cache is independent.

## Changes

- Backport TazUO's packet-processing budget: up to 5 ms or 1,000 complete network packets per update, retaining unfinished bytes for later frames. Large network messages no longer bypass the budget. Packets stay ordered; partial packets and plugin handling are preserved. Plugins are also serviced without fresh socket messages.
- Include the associated connection-buffer reset when login/relay sockets are replaced, so deferred data does not cross connection boundaries.
- Record compact five-second summaries for network processing, scene load/update, world-list preparation, game updates, audio updates and GC collection counts. No background diagnostic worker, stack sampling or per-packet log is added.
- Audio diagnostics now separate command-read waits, PCM-read waits and reply times from AudioTrack write times. The 40 ms buffer, WASAPI selection, start threshold and PCM data are unchanged.
- Exact input/output hashes, original backups and atomic replacement protect the supported client patch. Unknown client versions stay untouched. Original, scheduling-only, tracing-only and combined modes are reversible.

## Verification and limits

The production patch is generated from the exact TazUO 5.2.0 assembly and compared byte-for-byte with the shipped binary deltas. Structural verification preserves 19,779 original methods, all 3,096 constants and embedded resources; nine original methods change and one buffer-reset method is added. The extra timing helper is preloaded through the client-only .NET startup hook.

The real client parser and network loop are exercised with 14,000 ordered packets, split headers/bodies, a slow handler, leftover bytes without new socket data, plugin-only traffic, handler exceptions and connection reset. The original processes the burst in one update; the backport yields across updates. Tests run under .NET and Windows .NET 10.0.8 through Wine, including helper loading and composition with render tracing. Python, audio protocol, UI, APK deployment/signature and ARM64 runtime gates remain required.

The 5 ms budget is cooperative: one expensive handler can exceed it, and plugin handling is not time-sliced. It aims to improve responsiveness; it does not guarantee faster total loading or eliminate audio distortion. Timings locate delays but do not prove whether a socket wait originated in Wine, the client or Android scheduling. Device performance and longer gameplay stability still need a Thor session.
