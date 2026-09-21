# 0.2.3 session evidence and 0.2.4 changes

Source: user-supplied `logs-8740143909323385298.zip`, attempt 2026-09-21 12:36:25 UTC. Current-attempt records were separated from older appended presentation records.

- The new registry recovery regenerated a zero-filled system.reg and retained valid user hives. Wine/FEX hashes match 0.2.0. Client process launch was about 98 seconds after the request; this attempt included one-time registry repair, so 98 seconds is not a normal-launch baseline.
- TazUO reported game startup at 12:38:48, asset loading from 12:38:58 to 12:39:18 (19,855 ms), audio creation at 12:39:21 and player creation at 12:40:19. The world render target appeared at 12:40:56. These timestamps distinguish setup, client initialization and world entry; user login interaction is included between stages.
- Native Surface minute-average delivery was 12.5–15.8 new frames/s during 12:41–12:45, with individual windows near 7 FPS. At 12:47 it averaged 26.7 FPS, before logout at 12:48:31. Scene/activity differences prevent treating these as a controlled benchmark. Capture cost was usually 7–8 ms/frame in the slower interval, and many captures were duplicates.
- The one audio stream used a 1,920-frame/40 ms ring at 48 kHz, start threshold 1. Underruns climbed from 3 to 21 around world drawing at 12:40:57–12:41:02, remained at 24 for several minutes, then rose to 45 around 12:46. Persistent reported distortion between counter increases means Android underruns alone do not explain it.
- FAudio, DSOUND.DLL, mmdevapi and winealsa loaded. The supervisor forced `SDL_AUDIODRIVER=directsound` for every renderer. SDL 3 recognizes this legacy variable as an alias, so its old spelling did not make it inert.
- The client explicitly set `PROOT_NO_SECCOMP=1`, disabling PRoot's syscall filtering optimization. Thread samples repeatedly showed ptrace stops. This establishes that full syscall tracing was active, not the amount of speed or thermal improvement acceleration will deliver.
- User-reported temperature was about 64°C. Android's thermal-status field stayed 0; it is not a temperature measurement. No target temperature is inferred from it.

The implementation addresses the forced full-trace path, forced legacy audio backend and repeated healthy-prefix setup. It preserves the runtime binaries, graphics libraries, renderer, viewport, controllers and existing audio buffer policy. Compatibility switches allow comparison without reinstalling anything. Startup phase timings and the native acceleration-observed marker distinguish a requested optimization from actual activation.

Primary source checks:

- [Pinned PRoot event loop](https://github.com/termux/proot/blob/7266fb3e8516535682f5a9c8f3a7e70f6506eddb/src/tracee/event.c): filter activation unless explicitly disabled, kernel support handling and fallback.
- [SDL 3 audio-driver hint](https://wiki.libsdl.org/SDL3/SDL_HINT_AUDIO_DRIVER) and [SDL 2 hint](https://wiki.libsdl.org/SDL2/SDL_HINT_AUDIODRIVER).
- [SDL 3 legacy hint alias](https://github.com/libsdl-org/SDL/blob/release-3.2.26/src/SDL_hints.c).
- [FAudio SDL 3 platform backend](https://github.com/FNA-XNA/FAudio/blob/master/src/FAudio_platform_sdl3.c): selection honors an explicit driver; DirectSound preference exists for older Windows detection. This source explains the selection logic, not the exact imported FAudio revision or the user's audible failure.

Validation uses synthetic data: same retained runtime, patched PRoot in both modes, real imported TazUO SDL/FNA3D binaries, .NET 10 JIT/GC and a Windows WASAPI float-stereo probe through the actual ALSA plugin. The sink checks 440/660 Hz tones, level, duration and channels without recording device audio or reading game assets. A Thor gameplay comparison is still required.
