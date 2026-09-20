# UO Memento 0.1.12 Recovery — Targeted render crash diagnostics

**Diagnostic update; the recurring client crash is not yet fixed.** Install over Recovery without clearing data. No runtime download, server rebuild or client reimport is required.

## What the supplied binaries establish

The supplied TazUO.dll and portable PDB match commit `0fc274bf83c6ba84f37ec69a6bec7570743c1777`, version 5.2.0. The supplied FNA.dll is assembly version 25.11.0.0 at submodule commit `fb477d965e2e7c531a7dba3a10295ff1f8d1fb9f`. Both symbol identities match; source checksums confirm the exact drawing/filter code.

The changed TazUO commit does not change the failing render loop. Its own SDL filter replaces FNA's paint filter. The corrected regression verifies that distinction: the earlier standalone FNA reproduction did not establish the Thor crash's cause. The latest device failure remains `InvalidOperation_EnumFailedVersion` in `DrawRenderList`, after 594.82 seconds of process runtime, with the server still running.

## New tracing option

**Render crash tracing (diagnostic)** is off by default. Enabling it before launch applies a reversible delta only to the exact uploaded TazUO/FNA hash pair. The launcher retains `TazUO.dll.before-memento-render-trace`, checks the resulting DLL hash, and preloads a small helper. Turn the option off and relaunch to restore the original. A different FNA also triggers restoration; unknown client DLLs are not modified.

The helper observes list-building entry and surrounds the original render enumerator with a diagnostic catch/finally. It records the captured/current list versions, index/count, reader/writer threads and fill sequence. A fill overlapping an active reader records its calling stack. It does not suppress an exception or replace iteration with an unchecked loop. There are no sampling timers, first-chance handlers, worker threads or graphics calls in this helper. The existing detailed diagnostics setting remains separate. Tracing can still affect execution timing; this is not a zero-overhead probe.

The trace appears in `client-wine.log`, included by the normal Journal exporter. `client-config.json` records the patch state and assembly hashes. Original PDB files are retained; the instrumented DLL omits obsolete source-offset references.

## Verification and limits

On the exact supplied DLL, the patch verifier found only two changed method bodies, 19,786 unchanged bodies, 3,096 preserved constants and unchanged embedded resources. Applying the shipped delta, reapplying it, and restoring the original were checked with the supplied TazUO and FNA binaries.

The executable instrumentation probe covers same-thread and cross-thread list writes, an untracked write, unchanged versions, a different exception, integer-version wraparound, the next draw after a failure, and disabled tracing. Required Wine CI runs it with .NET 10.0.8 and the existing Wine 10 build. Existing Android/lint, packaged-asset, Python, Java/input/log, UI, Memento compilation and native graphics gates remain required.

These checks verify patch preservation, deployment and diagnostics. They do not reproduce the Thor's intermittent failure or establish long-session stability under Box64/Turnip. No renderer, CPU/JIT/GC preset, server behavior or viewport setting is changed by this release.

## Next diagnostic run

1. Save/stop the realm and stop the client, then install 0.1.12 over Recovery. Keep app data.
2. In Client, enable **Render crash tracing (diagnostic)**. Keep **Detailed client diagnostics OFF**, **Memory compatibility OFF**, and **SDL Vulkan resource fixes ON**.
3. Keep Turnip, Native Surface and **1280×720 with the 1098×720 world option**. Launch the existing client; after a failure export **Journal → Export support logs**.
4. To remove instrumentation, turn Render crash tracing off and relaunch. The original DLL is restored automatically.
