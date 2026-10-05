# UO Memento Mobile 0.2.21 — Official release

Promotes the map-loading optimization physically validated in 0.2.20 to an official release. The October 5 Thor export confirms that completed map-1 chunks in emitted windows use three original file-length getters instead of 2,115. Cold-interior main-thread chunks peaked at 5.795 ms, compared with the prior 6,578.185 ms interior chunk. The marked outdoor and interior phases contained no frame gaps of 250 ms or longer, and the user reported a substantially smoother run.

**Faster map loading** retains the tested chunk-scoped cache: first accesses remain live, subsequent chunks refresh lengths, reader replacement is observed, disposed readers retain their original exceptions, and all references clear on normal and exceptional returns. Actual data reads and client behavior carry forward from 0.2.20. There is no additional performance experiment in this release.

Install over the existing app, keeping data, imported client, saves, caches and installed Wine/FEX runtime. Leave **Faster map loading** and **Smooth world loading** ON. Turn **Cold-load timing (Thor test)** OFF for normal play; keep optional SDL OFF and your working Native Surface, graphics, audio, controls and server settings. No repeat diagnostic baseline is needed.

A separate initial-world frame still lasts about 5.2 seconds before the first outdoor marker, including 4.65 seconds in packet-55/network handling. Its chunk work is small, so this release does not claim to eliminate every startup pause. The analysis records this remaining boundary without assigning an unmeasured cause. Marked warm revisits remain smooth, and the export records successful world entry and completed save/close.

The accepted Wine/FEX runtime, application/signing identity, startup fixes, native rendering, audio, controls, server and existing data are preserved. The exact eight delta variants, activation/restoration tests, host/Wine/FEX/both PRoot checks, packaged-APK verification and every existing release gate remain required. The 0.2.19 diagnostic path remains available by disabling Faster map loading and enabling Cold-load timing for a fresh client.

See the [normal-play instructions](https://github.com/Russianranger/uo-android-launcher/releases/download/v0.2.21/UO-Memento-Mobile-0.2.21-Instructions.txt), [physical comparison and limits](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/THOR-0.2.20-ANALYSIS.md) and [cache lifetime and qualification](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/OPTIMIZATION-0.2.20.md).
