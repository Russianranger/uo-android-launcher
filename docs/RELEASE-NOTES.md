# UO Memento Recovery 0.2.0

The client now uses **native ARM64 Wine with FEX ARM64EC**. This replaces Box64 and x64 Wine, following the architecture of the previously reported Bannerhub setup. It is a new runtime preview, not a claim that long-session Thor stability has been established.

## Update

1. Save/stop the realm and stop the client. Install this APK over **UO Memento Recovery**, keeping app data.
2. In **Client**, press **Install FEX runtime** once. The new runtime and Windows prefix are separate from the previous installation. Do not import the old TRASC client-runtime archive into this version.
3. Start the realm and launch TazUO with **Turnip 26 · Vulkan**, **Native Surface**, **1280×720**, and **1098×720 world + gump space**.
4. Start with SDL replacement, render tracing and detailed managed diagnostics **OFF**. Previous recognized patches are restored automatically from their backups.

Imported client files, .NET downloads, character profiles, server saves and controller mappings are preserved. No server rebuild or client reimport is required. The old runtime/prefix remain on disk, but are not used. Support logs now identify native Wine and both FEX modules by architecture and hash.

## Runtime and verification

The replacement is built on ARM64 from pinned Wine ARM64EC and FEX sources. Its installation is checked for native ARM64 Wine and ARM64/ARM64EC FEX modules. Windows x64 .NET 10.0.8, JIT/GC/thread/vector work, and the real TazUO 5.2 SDL/FNA3D Vulkan resource test are release gates, directly and under Linux PRoot. Existing application, controller, import/backup, layout, server compilation, APK packaging and signing checks remain required.

ARM64 CI uses software Vulkan and Linux PRoot. Android PRoot, Adreno/Turnip rendering, audio/controller interaction and a sustained Memento world session still require device testing. The exact GameHub Wine 10.6/FEX date and Turnip 25 combination has not been reproduced; see [the component comparison](RUNTIME-COMPARISON.md).

The release includes the separate client runtime and manifest, full Wine/FEX sources, native-bridge corresponding sources and the APK source archive.
