# UO Memento Recovery 0.1.6 — Native crash compatibility test

The 0.1.5 support bundle confirms the Native Surface startup fix worked: presentation stayed native throughout the session, with no fallback. The user reported better FPS. After initial loading, most ten-second game FPS samples were in the 28–37 range (these are sampled game FPS, not screen-update counts or a complete frame-time trace).

The client exited after 594 seconds with `Fatal error. 0xC0000005` from CoreCLR 10.0.8, exit code 2. No managed first-chance/unhandled exception was recorded. The render-list crash text included in the archive is from the previous session; it does not explain this native failure. The launcher and realm remained alive. The exact bad pointer/module and cause are not established.

## Changes

- Add **Memory compatibility (experimental)** in Client → Display & sound, enabled by default after upgrade. It sets Box64 `DYNAREC_STRONGMEM=3` and `DYNAREC_WEAKBARRIER=0` for the client. Compared with the previous limited memory barriers, this covers SIMD writes and uses regular barriers. Turning it off restores the prior memory-ordering values (`1` / `1`) on the next launch.
- This is an experimentally chosen mitigation for native instability under ARM64 translation, not proof that memory ordering caused the crash. It may reduce FPS. No client binaries or .NET JIT/GC options are changed.
- Enable Box64 signal details and Wine module-load addresses for the client process, which were absent from the fatal report. Do not enable continuous instruction traces, rolling call logs, or native backtrace walking on every signal. Handled faults can appear too; the terminal failure is what matters. Existing 8 MiB log rotation bounds output.
- Include an allowlisted compatibility report in the support ZIP. Add managed heap size and generation collection counts to the existing ten-second FPS samples, without forcing GC.
- Preserve Native Surface readiness, Turnip/Vulkan, controller mappings and the **1098×720 world viewport within the 1280×720 canvas**.

## Update and test

1. Save and close the realm runtime and stop the client. Install this APK over **UO Memento Recovery**, without uninstalling or clearing data. No server rebuild, client reimport or runtime download is needed.
2. Start the existing server. Use **Turnip/Vulkan**, **1280×720**, **Native Surface**, **60 FPS**, **1098×720 world + gump space**, and **Memory compatibility** on.
3. Repeat normal movement and interactions for **20 minutes**, if stable. Export support logs immediately afterward or after a crash. Note whether responsiveness changed noticeably.
4. If this mode is substantially slower, turn **Memory compatibility** off and restart only the client for a comparison. Export each session separately. Both modes retain the new native diagnostics.

## Validation and limits

Automated coverage includes memory-profile defaults/opt-out and persisted launch options, fatal output retention through log rotation, Android build/lint and signing continuity, readiness/controller/import/save regressions, and the real Memento server compile. Wine 10/.NET 10.0.8 tests cover managed diagnostics and a deliberate native access violation with module-load attribution. The native fixture verifies the reporting path; it does not reproduce the unknown TazUO defect. CI's x86-64 Wine tests do not establish ARM64 Box64 correctness or long-session Thor stability. Those require this device test.

Reference: [Box64 0.4.4 option definitions](https://github.com/ptitSeb/box64/blob/v0.4.4/docs/USAGE.md), [Box64 0.4.4 signal handling](https://github.com/ptitSeb/box64/blob/v0.4.4/src/libtools/signals.c).
