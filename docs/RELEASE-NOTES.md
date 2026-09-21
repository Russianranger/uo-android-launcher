# UO Memento Recovery 0.1.13

This update disables Box64's optimized direct returns for the game process. The bundled translator predates [upstream fix 4405](https://github.com/ptitSeb/box64/pull/4405), which addresses returns into recycled translated code. The workaround uses `BOX64_DYNAREC_CALLRET=0` and records it in support logs. It applies automatically.

The latest VirGL test entered the world but showed white object coloring and crashed with an access violation in DrawRenderList. That establishes that switching to OpenGL did not solve the instability. The Box64 workaround addresses a relevant known defect; **it is not yet a confirmed fix for the Thor crash**. Performance may differ.

## Update and test

1. Save and stop the realm, stop the client, then install this APK over **UO Memento Recovery**. Keep app data; no server rebuild, client reimport, runtime download or prefix repair is required.
2. Select **Turnip 26 · Vulkan**, **Native Surface**, **1280x720**, with **1098x720 world + gump space** enabled.
3. Keep **SDL Vulkan resource fixes ON**, **Render crash tracing ON**, **Detailed client diagnostics OFF**, and **Memory compatibility OFF**.
4. Enter the same character, check the ship's color and play beyond the earlier failure interval. After a crash or freeze, export **Journal -> Export support logs**. Logs should report `BOX64_DYNAREC_CALLRET=0`.

Server behavior, controller mappings, saved profiles and the 182-pixel gump area are preserved. Wine setup and .NET JIT/GC settings retain their prior behavior.

## Release gates

The release requires the existing Python, Java, UI, server compile, Wine/.NET, FNA/SDL, render-instrumentation, APK packaging and signature-continuity checks. A new real ARM64 job builds the pinned Box64 source and checks modified-code returns using an x86-64 generated-code fixture. It records stock mode separately; stock failure is not assumed. These tests do not reproduce a TazUO world session or establish device stability.

See [the VirGL investigation](CRASH-0.1.12-VIRGL.md) for exact evidence, the upstream defect and verification limits.
