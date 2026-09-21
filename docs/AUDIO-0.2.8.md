# Audio delivery and the world-map pause

## Device evidence

The supplied 0.2.7 support archive covers roughly 35 minutes on 2026-09-21, 20:52–21:27 UTC. Audio write gaps above 40 ms fell from 38 in the first five minutes to 10 in the next five and one during the remaining roughly 25 minutes. All 208,957 reported writes were fully accepted, while Android still accumulated 459 underruns. Sampled queue depths were frequently 0–1,440 frames. This fits the user's observation that the session smoothed out; full write acceptance alone does not show that the queue stayed fed.

At about minute 33, the game update reached 9,189 ms and the audio-update gap reached 9,182 ms. The next timing window also observed the same long separation between updates. Network, scene and world-list stage maxima in the affected window were small. The user confirmed opening the world map and generating its image at this point. GC counters record collections, not their duration; neither they nor the stage timers isolate the entire pause.

## Change and comparison

`AudioPcmSession` now optionally wraps its socket stream in a 16 KiB `BufferedInputStream`. Previously, reading little-endian command integers through `DataInputStream` made separate underlying byte reads. Buffering can coalesce available bytes. It adds no playback watermark: an input read can return fewer than 16 KiB, and each command retains its immediate reply/flush. The stream still validates payload lengths, sends exactly the received PCM and reports actual accepted frames.

`AudioBridge` requests `THREAD_PRIORITY_AUDIO` on each bounded playback worker when **Smooth audio delivery** is enabled. It logs the resulting priority and continues if that request is denied. Listener, game and server priority are unchanged. Turning the switch off and relaunching restores both ordinary worker scheduling and unbuffered input; the extra interval diagnostics remain available in either mode.

This retains the device-tested 480-frame period, 1,920-frame ring and Android 12+ one-frame start threshold. The 0.2.1 experiment changed period, ring size, startup threshold and priority together and regressed. This release isolates delivery changes from the larger buffers and startup behavior. It does not establish whether priority or buffering individually helps; if the combined mode regresses, the switch provides a controlled fallback and the counters can guide a narrower follow-up.

`client-audio.log` adds `interval_underruns`, `socket_read_calls`, `socket_read_bytes`, `queue_samples`, `empty_queue_samples`, `below_10ms_samples`, `min_queued_frames` and `max_queued_frames`. Read counters measure calls to the underlying stream, including EOF, rather than Java wrapper reads. Queue samples are taken at existing playback-position requests while playing; they are observations, not distinct audible glitches. Empty/minimum samples cannot reconstruct the duration of starvation. Underrun baselines reset when an AudioTrack is recreated. The actual Android buffer size and start threshold appear in each interval. The audio log is capped at 512 KiB and retains the existing session rotation.

## Map investigation

The verified TazUO 5.2.0 assembly corresponds to source revision `0fc274bf83c6ba84f37ec69a6bec7570743c1777`. `WorldMapGump.ChangeMap` schedules `LoadMap` via `Task.Run`. `Map.GenerateMapPng` hashes the map/statics data and reuses `Data/Client/MapsCache/map{index}_{hash}.png` when present. Creating the PNG involves rasterization/encoding; loading its texture can still require decode/upload and graphics-thread work. Clearing the in-memory path lookup when changing maps does not delete the disk PNG cache.

No map code or cache key is changed. Removing content validation could reuse stale images after a map update. Moving the existing background task would not by itself remove memory pressure or texture upload work. Reopen the same unchanged map after its first successful generation, then repeat in a later client session with the cache retained. A recurring multi-second pause warrants timing map hashing, PNG decode and texture upload separately. The existing evidence supports a one-time generation explanation but does not prove all cached openings will be instant.

## Validation

`bash scripts/check-audio.sh` exercises protocol equivalence with fragments of 1, 3, 7 and 1,928 bytes, including zero/partial sink acceptance, short sounds, maximum payloads, stop/reset/restart and EOF. Invalid and incomplete bodies must not deliver PCM. Its loopback socket test waits for every response with a timeout while sending less than the input-buffer size, so an accidental fill requirement fails. Queue counters cover paused exclusion, negative-depth clamping, interval reset and recreated tracks. Existing startup-policy checks remain intact.

The synthetic coalesced fixture uses 122 underlying reads without buffering and six with buffering. Actual Android stream packetization and thread scheduling differ. Compare the same route and elapsed session age with the switch on/off; inspect interval underruns together with low-queue samples, delivery gaps and read calls. A larger ring should only be reconsidered if these observations establish that refill headroom is still the limiting factor.

Sources: [matched WorldMapGump](https://github.com/PlayTazUO/TazUO/blob/0fc274bf83c6ba84f37ec69a6bec7570743c1777/src/ClassicUO.Client/Game/UI/Gumps/WorldMapGump.cs), [matched Map](https://github.com/PlayTazUO/TazUO/blob/0fc274bf83c6ba84f37ec69a6bec7570743c1777/src/ClassicUO.Client/Game/Map/Map.cs), [Android Process audio priority](https://developer.android.com/reference/android/os/Process#THREAD_PRIORITY_AUDIO), [Android AudioTrack underruns](https://developer.android.com/reference/android/media/AudioTrack#getUnderrunCount()).
