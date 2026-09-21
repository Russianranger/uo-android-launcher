# 0.2.5 scope and evidence

The 0.2.4 support session starting 2026-09-21 13:58:38 UTC ran approximately 24 minutes and ended in a normal logout. Older Sep 20 crash files in the archive do not describe this session. The user reported low-50°C temperatures, better sound and faster loading.

Observed: PRoot acceleration was active; the healthy prefix reused in about 1.12 seconds; TazUO asset loading took 10,071 ms versus 19,855 ms in the preceding session. The audio bridge remained one 48 kHz stereo WASAPI stream with a 1,920-frame producer buffer. Its final 630 underruns are event counts, not audible dropout duration. RSS was broadly stable around 760–815 MiB.

The display averaged about 29.4 captures per second, of which 44% were exact duplicates; changed-frame counts are not game FPS. Readback averaged about 0.97 ms, much faster than the preceding session. This justifies removing redundant synchronous metadata queries before considering a different pixel transport.

## Implemented

Audio scans accepted PCM once, retaining both progress and lifetime counts. Monotonic timestamps measure accepted-delivery gaps during playback and AudioTrack write duration. Five-second reports reset interval counters but retain the last delivery timestamp; stop/start/reset exclude idle and first priming time. No buffering, scheduling priority, native ALSA plugin or playback policy changes.

X11 retains XQueryPointer per request. Root ConfigureNotify invalidates window attributes, and XFixesCursorNotify invalidates shape/pixels. A two-second periodic refresh bounds missed-notification effects. Cursor compositing uses current pointer coordinates, not the coordinates stored in the cached image. Each socket connection owns and frees its cache. Existing pixel comparison, MIT-SHM/XGetImage paths and 30/60 limits remain intact.

The CI build must overlay the rebuilt presentation artifact after restoring retained assets. The release bridge archive verifies both audio and presentation manifests against the actual packaged bytes.

## Prepared, not deployed

`patches/tazuo-music-cache.patch` targets PlayTazUO/TazUO source revision `0fc274bf83c6ba84f37ec69a6bec7570743c1777`. Its per-loader array is reset at Load and ClearResources. It caches the original Directory.GetFiles result and leaves Regex/Array.FindAll and result selection unchanged.

The supplied TazUO.dll (`b04066be…947e`) does not contain SoundsLoader; that class is in the separate ClassicUO.Assets.dll, which has not been supplied. A production patch requires that exact DLL (and preferably its PDB), an original/output checksum pair, unchanged-method/resource verification and an execution probe. The current public AutoBuild is a different client revision and is not a substitute. No music cache is enabled or claimed by this APK.
