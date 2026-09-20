# UO Memento 0.1.11 Recovery — Serialize client repaint events

Install over Recovery without clearing data. No runtime download, server rebuild or client reimport is required.

## Evidence from this attempt

The 0.1.10 support bundle confirms the SDL 3.4.16 update was active. TazUO entered the world, then terminated at 21:52:19 with `System.InvalidOperationException: InvalidOperation_EnumFailedVersion` in `GameScene.DrawRenderList` (line 1328), through `DrawWorld` and `Game.Tick`. The supervisor recorded exit 82 after 911 seconds of client process runtime. The server remained running.

This attempt does not show the previous `vkDestroyImageView` assertion or native access violation. The native frame-delivery error appears during teardown after the managed crash. Exit 82 alone is not a diagnosis; the managed exception and stack identify this failure.

## Targeted mitigation

TazUO fills and then enumerates shared render lists during drawing. Its pinned FNA Windows event filter can synchronously invoke `RedrawWindow` on a window-exposure event, including while another draw is in progress. That nested draw can clear/repopulate a list whose outer enumerator is still active, producing the observed exception type and draw path.

The client launch now sets FNA's supported `FNA_WIN32_IGNORE_WM_PAINT=1` hint. This skips the immediate Windows paint filter. Exposed-window events still receive redraws through FNA's ordinary game-loop polling. The setting applies to the game process and is recorded in `client-compatibility.json`; Wine setup and the desktop retain their existing environment.

Source references: [TazUO 5.2 render-list iteration](https://github.com/PlayTazUO/TazUO/blob/73768f6653d39788b00f5bce5b2a063dc76452aa/src/ClassicUO.Client/Game/Scenes/GameScene.cs), [its pinned FNA SDL3 filter and event loop](https://github.com/FNA-XNA/FNA/blob/fb477d965e2e7c531a7dba3a10295ff1f8d1fb9f/src/FNAPlatform/SDL3_FNAPlatform.cs), and [FNA RedrawWindow](https://github.com/FNA-XNA/FNA/blob/fb477d965e2e7c531a7dba3a10295ff1f8d1fb9f/src/Game.cs).

The launcher also labels failures after the client process has started as **Client stopped unexpectedly**, and suppresses display-fallback reconnection/toasts when the supervisor has already reported a client failure or stopped.

## Verification and limits

The new required Wine regression builds the exact FNA submodule used by TazUO 5.2 and runs it with .NET 10.0.8, Wine 10, the actual TazUO FNA3D/FAudio libraries, SDL 3.4.16 and Mesa Vulkan. It injects an SDL window-exposure event during render-list enumeration. The old policy must reproduce an `InvalidOperationException` after a nested draw. The production policy must process 64 exposures and at least 160 draws with no nested draw or exception. The test does not replace FNA with a mock or swallow an exception in the production client.

This verifies the reentrancy mechanism and its mitigation on x86-64 CI. The device log does not record the original exposure event, so it does not conclusively prove that this mechanism caused the Thor crash. It also does not establish long-session stability under ARM64/Box64/Turnip. Existing native Vulkan, managed loader, client configuration, server compile, Android build/lint, packaged-APK import, input/log and signing-continuity checks remain required.

## Install and compare

1. Save/stop the realm and stop the client. Install 0.1.11 over Recovery; keep app data.
2. Retain **SDL Vulkan resource fixes ON**, **Memory compatibility OFF**, **Detailed client diagnostics OFF**, Turnip and Native Surface. The repaint mitigation is automatic.
3. Keep 1280×720 with the 1098×720 world option for the 182-pixel gump area. Launch the existing client. If it fails again, export support logs; they now identify the active repaint policy as well as the DLLs.

No client executable patch, client reimport, new CPU preset or renderer switch is needed for this update.
