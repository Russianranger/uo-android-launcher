# UO Memento 0.1.10 Recovery — SDL Vulkan resource recovery

Install over Recovery without clearing data. This is a targeted graphics compatibility preview; it does not establish that the Thor crashes are solved.

## What the current logs establish

The 0.1.9 attempt starts Wine and TazUO, loads UO data and connects. Box64 then records a native access violation in `turnip-26.0.0.so` (access to `0x78`), followed by Wine's `!status && "vkDestroyImageView"` assertion. The client exits after approximately 156 seconds with final code -9. That code does not identify who sent the kill signal. Managed diagnostics and the experimental memory profile were both off. Sampled process RSS reaches about 750 MB; these samples do not establish Android-wide memory pressure or an out-of-memory kill.

This identifies the failing Vulkan resource-destruction path, not which component originally supplied the invalid state. The launcher, Wine/Box64, driver, SDL and client still form an unverified Android graphics stack.

## Narrow, reversible change

The exact TazUO 5.2 source distribution bundles SDL 3.2.27. SDL subsequently fixed Vulkan allocation defragmentation while transfers remain pending, including multi-threaded use ([upstream fix](https://github.com/libsdl-org/SDL/pull/15127)), and subsequent cleanup/barrier crashes. The bundled official SDL 3.4.16 includes these fixes. They are relevant candidate fixes; the current device fault has not been reproduced or proven to be that upstream bug.

- Before a Turnip client launch, upgrade **only** the recognized x64 SDL/FNA3D pair from TazUO 5.2. Both original DLL checksums must match. Custom, newer, missing and x86 libraries are left untouched.
- Preserve the original SDL beside the executable as `SDL3.dll.before-memento-3.4.16`. Verify checksums and replace atomically. The imported client executable, FNA3D, game files and .NET remain unchanged.
- **SDL Vulkan resource fixes (preview)** is enabled by default. Turn it off and relaunch to restore the original SDL from its verified backup. Switching to OpenGL also restores that backup. An already imported SDL 3.4.16 with no launcher backup is left as imported.
- Record active SDL version and SDL/FNA3D checksums in `client-config.json` and `client-state.json`, so a skipped or applied update is visible in support logs. No credentials are recorded in this report.

Wine, Box64, Turnip, audio, controller mappings and the 1098×720 world inside the 1280×720 canvas remain configured as before. There is no runtime download or server rebuild for this update.

## Verification and limits

Release gates exercise the **actual TazUO 5.2 FNA3D.dll**, first with its original SDL and then with the packaged updated SDL, under the pinned Wine 10 build and a Vulkan software driver. The native fixture creates/disposes 1,920 render targets, resizes the backbuffer six times, and verifies 120 pixel readbacks. This checks binary compatibility and resource-lifetime operations on x86-64 Linux, not ARM64/Box64/Turnip or long gameplay sessions.

Additional gates cover reversible upgrades, rejection of changed backups, interrupted writes, preservation of unknown client versions, persisted UI options, isolated imports and the SDL checksum from the built APK. Existing server compilation, Android build/lint, signing continuity, managed Wine probes and input/log checks remain required.

## Install and compare

1. Save/stop the server and stop the client. Install 0.1.10 over Recovery; keep app data.
2. Leave **SDL Vulkan resource fixes ON**, **Memory compatibility OFF** and **Detailed client diagnostics OFF**. Retain Turnip, Native Surface and 1280×720.
3. Launch your existing realm/client. If it crashes, export support logs; the active-library report will distinguish this attempt from earlier ones. You can return to the original graphics library by disabling the new option and relaunching.
