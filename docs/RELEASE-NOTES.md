# UO Memento Recovery 0.1.7 — Restore Wine startup settings

The 0.1.6 support bundle records `wineboot -i` ending with SIGKILL (code -9), approximately 22 seconds after the display started. TazUO was never launched. `client-wine.log` and `client-managed.log` still contained the previous 0.1.5 gameplay session, so their native crash was not this startup failure. The source of SIGKILL is not identified in the bundle; it does not establish an out-of-memory kill or a Box64 crash.

The new experiment was incorrectly applied to the supervisor's shared environment, so Wine setup, its services, preflight and teardown inherited `STRONGMEM=3` / `WEAKBARRIER=0`. That scope was broader than intended. This release corrects it and restores the earlier settings for the next device test.

## Changes

- Restore `STRONGMEM=1` / `WEAKBARRIER=1` for Wine setup, preflight, desktop, helpers started during setup, and teardown, regardless of the game compatibility selection.
- Default **Memory compatibility** off. Ignore the old 0.1.6 saved opt-in using a new client-specific option key; preserve the other launch preferences. A new explicit opt-in persists normally.
- Apply the stricter experimental profile only to the game launch's copied environment, never to the shared setup environment. Leave it off for this recovery test. No change to imported TazUO binaries or .NET JIT/GC policy.
- Preserve previous game/managed/host logs and compatibility reports in the existing bounded history before a new attempt. A setup-only failure no longer leaves an earlier gameplay crash in the current log slots.
- Record the attempt start time, whether the game was launched, and setup exit code/log/duration. Label SIGKILL distinctly instead of presenting it as a TazUO crash.
- Preserve Native Surface readiness, Turnip/Vulkan, controller mappings, native fault diagnostics and the **1098×720 world viewport inside 1280×720**.

## Update and test

1. Save and close the realm runtime and stop the client. Install this APK over **UO Memento Recovery**; keep app data. No rebuild, reimport or runtime download is needed.
2. Start the existing server. Keep **Turnip/Vulkan**, **1280×720**, **Native Surface**, **60 FPS**, and **1098×720 world + gump space**. Confirm **Memory compatibility is OFF**.
3. Launch TazUO and first check login/world entry. If it starts, continue normal play for up to 20 minutes. Export support logs after the test or immediately after a failure.

The known environment-scoping bug is corrected. The cause of the device's SIGKILL and the earlier roughly ten-minute native gameplay crash are not established, so neither is claimed resolved without a device test.

## Validation

Regression coverage exercises default and explicit opt-in paths, actual Wine setup call environments after constructing the experimental game environment, desktop isolation, a simulated setup SIGKILL before client spawn, preserved old crash history, and migration of the old saved UI option without resetting unrelated settings. Existing Android build/lint, signing continuity, native/managed Wine diagnostics, controller/readiness/log/import/save checks and real server compilation remain release gates. CI does not reproduce Android process management or ARM64 gameplay.
