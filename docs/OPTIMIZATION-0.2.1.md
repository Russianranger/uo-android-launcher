# 0.2.1 evidence and scope

The 2026-09-21 10:21–10:40 UTC support session used 0.2.0, FEX ARM64EC, native Wine 10.13, original TazUO 5.2/SDL graphics libraries, Turnip and Native Surface. The client saved its profile on exit. No crash fix or translator change is part of this update.

The playback stream negotiated 1920 frames at 48 kHz (40 ms), started with 480 queued frames and a one-frame start threshold, and recorded 42 AudioTrack underruns. Most were early in the session. The log cannot establish whether remaining distortion comes from translated mixing or upstream data; the bridge tests verify sample fidelity separately.

For frame-bridge windows 70 through the penultimate two, 18,169 frames were delivered and 35,623 captured in 781.64 seconds: about 23.24 delivered versus 45.57 captures per second, with 17,454 duplicate captures. Capture averaged 4.60 ms per operation. TigerVNC reported 42.35 Gpixels compared despite zero RFB framebuffer updates; the RFB connection served input while Native Surface displayed frames. These transport counters are not game FPS.

Targeted changes: match game/capture targets; default 30 with explicit 60 preserved; disable redundant VNC comparison for native mode; enlarge negotiated audio buffers and prime within producer capacity; prioritize Android audio worker. Runtime hashes, .NET policies, PRoot seccomp behavior, graphics drivers and render DLLs are unchanged. The new minimum ring trades some audio latency for scheduling tolerance. No PCM, account data or full settings are added to support logs.

References:
- [Android AudioTrack priming, start threshold and underrun API](https://developer.android.com/reference/android/media/AudioTrack)
- [Wine 10.13 ALSA stream sizing: four periods](https://github.com/bylaws/wine/blob/a6844d10622fc1a973ec1f22fc4f78a0fcd6cb29/dlls/winealsa.drv/alsa.c)
- [TigerVNC 1.12 CompareFB behavior](https://github.com/TigerVNC/tigervnc/blob/v1.12.0/common/rfb/VNCServerST.cxx)
- [TazUO game FPS setting](https://github.com/PlayTazUO/TazUO/blob/73768f6653d39788b00f5bce5b2a063dc76452aa/src/ClassicUO.Client/Configuration/Settings.cs)
