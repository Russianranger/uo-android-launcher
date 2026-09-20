# UO Memento Recovery 0.1.5 — Native Surface startup fix

The 0.1.4 session selected Native Surface, but its Android display remained on RFB for the entire run. It also tried to connect relative input before the helper socket existed. In-world presentation updates had a median of about 12.2/s; these are screen-update counts, not measured game FPS. The client later crashed after about 13 minutes 50 seconds with `InvalidOperation_EnumFailedVersion` in TazUO 5.2.0's `DrawRenderList`.

- Fix readiness reporting: an Xvnc socket alone no longer opens the client activity. Wait for the supervisor to publish the completed presentation/input setup, then verify the corresponding sockets. Apply the same check to reopening the display.
- Preserve intentional Standard display and absolute-input fallbacks, while rejecting incomplete setup and stale sockets from stopped sessions.
- Avoid expensive first-chance stack construction for ordinary file, assembly and script-control exceptions. Retain bounded capture for relevant faults and add the render-list throwing stack/thread.
- Capture bounded FNA graphics messages and the client's own cached FPS, active/focus flag and scene every ten seconds for up to one hour. These allow comparison with Android's independent display measurements.
- Keep the 1098×720 world viewport, 1280×720 canvas, controller mappings and existing installation.

## Update and test

1. Save and close the realm runtime and stop the client. Install this APK over **UO Memento Recovery** without uninstalling or clearing data.
2. Start the existing server, then launch with **Turnip/Vulkan**, **1280×720**, **Native Surface**, **60 FPS**, and **1098×720 world + gump space** enabled. No rebuild or client reimport is needed.
3. Open the gear menu and check that it says **Native Surface**. Compare movement responsiveness with 0.1.4, then test for at least 15 minutes if stable.
4. Export support logs after the test, even if there is no crash. If Native Surface falls back, include the displayed reason.

The startup race is fixed and covered by regression tests. **The TazUO render-list crash remains unresolved; this release does not claim a crash fix or a measured device FPS improvement.** Its exception indicates a list version changed during enumeration, but the writer/reentrant call has not been identified. We investigated FNA's Win32 paint callback; TazUO installs its own event filter, so this build does not introduce that speculative workaround or change the imported client binary.

Validation includes Android build/lint, startup-readiness cases, controller/log/import/world tests, browser UI checks and Wine 10/.NET 10.0.8 tests for configuration, original exception stacks, graphics-log handler preservation and cached FPS sampling. The graphics tests use explicit API fixtures, not an Adreno renderer or a running TazUO world.

References: [TazUO 5.2 render loop](https://github.com/PlayTazUO/TazUO/blob/73768f6653d39788b00f5bce5b2a063dc76452aa/src/ClassicUO.Client/Game/Scenes/GameScene.cs), [game frame counter](https://github.com/PlayTazUO/TazUO/blob/73768f6653d39788b00f5bce5b2a063dc76452aa/src/ClassicUO.Client/GameController.cs), [FNA logging contract](https://github.com/FNA-XNA/FNA/blob/fb477d965e2e7c531a7dba3a10295ff1f8d1fb9f/src/FNALoggerEXT.cs).
