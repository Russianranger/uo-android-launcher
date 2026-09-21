# TazUO runtime comparison

The user supplied three Bannerhub settings screenshots on 2026-09-20 and stated that this was their configuration for running TazUO. The images identify selected settings, not the exact TazUO version, loaded renderer, duration or stability of that session.

| Setting | Bannerhub screenshot | UO Memento 0.1.8 |
| --- | --- | --- |
| CPU translator | Fex-20251025 | Box64 0.4.4 |
| Wine | wine10.6-arm64x-2 | Wine 10.0 amd64 WoW64 |
| GPU driver | turnip_v25.0.0_R1 | Turnip 26.0.0 |
| DXVK selection | dxvk-2.3.1-async | TazUO is configured for FNA Vulkan directly; DXVK selection does not establish the active renderer |
| VKD3D selection | vkd3d-2.12 | Not used by the configured FNA Vulkan path |
| Dinput | Prefer Native | Wine defaults; launcher input arrives through XTest |
| Audio driver | Pulse | Wine audio routed through the embedded Pulse transport |
| CPU core limit | Unlimited | Real CPU count (`BOX64_MAXCPU=0`) |
| VRAM limit | Unlimited | No launcher-imposed limit |
| Translation parameters | Game Presets (contents not shown) | Conservative explicit Box64 flags in the launch report |
| Skip audio/video decoding | Off | No corresponding override |
| Disable image quality enhancement plugin | Off | No corresponding plugin |

## 0.2.0 replacement

The selected architecture is **FEX Windows ARM64EC modules + native ARM64 Wine**, as used by Bannerlator's ARM64EC containers. This replaces the old Box64/x64 Wine execution path. The app still hosts the client, server and TRASC controls; no external Bannerlator installation is required.

| Component | 0.2.0 source build | Difference from the screenshot |
| --- | --- | --- |
| Wine | bylaws Wine ARM64EC fork, 10.13, `a6844d10622fc1a973ec1f22fc4f78a0fcd6cb29` | Open, reproducible glibc build; not GameHub's `wine10.6-arm64x-2` binary |
| FEX | FEX-2510, `320c5f18475b0c8a7e99c51a5fdc5b5e35b147ab` | October 2025 release; not claimed to be the exact `Fex-20251025` build |
| Host libraries | Native ARM64 Debian 12 inside the app's PRoot | Bannerlator uses Bionic/Android libraries; these are not binary interchangeable |
| Vulkan | Existing native ARM64 Turnip 26, FNA Vulkan directly | Screenshot selected Turnip 25 R1; driver not changed in this migration |
| Translation settings | Upstream FEX defaults | Screenshot's hidden Game Presets values are unknown |
| Display and controls | Existing Native Surface / X11 transport, TRASC mappings | Retains the app's existing controls and 1098×720 world in a 1280×720 display |

The upstream FEX instructions recommend the bylaws Wine fork and explain that its ARM64EC modules allow Wine and Vulkan Unix libraries to execute natively, without an x86 rootfs. Wine and FEX are built together on native ARM64 CI from the commits above. Both the runtime archive and corresponding Wine/FEX sources accompany the release.

The runtime installs into `client/runtime-fex-v1` and uses `client/prefix-fex-v1`. It never upgrades the old x64 Wine prefix. Previous Box64/JIT tuning is removed, and old tracing/SDL settings cannot carry over as a FEX opt-in. Binary architectures and hashes are recorded in `client-runtime.json` for each launch.

The CI gate runs Windows x64 .NET 10.0.8, repeated dynamic-method JIT/compacting GC/thread/vector work, and the actual TazUO 5.2 SDL/FNA3D Vulkan render-target probe on ARM64, both directly and under Linux PRoot. It does not verify Android PRoot, Adreno/Turnip, a Memento world login or long gameplay sessions.

## Research sources

- [Bannerlator](https://github.com/The412Banner/Bannerlator): open-source continuation of Winlator Star Bionic; ARM64EC containers and FEX component selection. Its native Unix FEX modules must match the PE modules; this build uses upstream DLL-only FEX instead.
- [Bannerlator guest launcher](https://github.com/The412Banner/Bannerlator/blob/eb5812d3b73cc827cd77a8e5aaf86d3969e58849/app/src/main/java/com/winlator/star/xenvironment/components/GuestProgramLauncherComponent.java): native Wine path for ARM64EC containers, separate Box64 path for x86_64 containers.
- [FEX ARM64EC build documentation](https://wiki.fex-emu.com/index.php/Development:ARM64EC): Wine fork, compiler and two Windows FEX modules.
- [Pinned Wine fork](https://github.com/bylaws/wine/tree/a6844d10622fc1a973ec1f22fc4f78a0fcd6cb29) and [FEX-2510](https://github.com/FEX-Emu/FEX/tree/320c5f18475b0c8a7e99c51a5fdc5b5e35b147ab).
- [Bannerhub component labels](https://github.com/The412Banner/Nightlies/blob/main/wine_containers.json) include the screenshot's Wine label, but do not identify a reproducible redistributable build recipe for that exact package.

The implementation follows the FEX/ARM64EC architecture. It is not an exact copy of the earlier GameHub runtime, and stability has not been inferred from the settings screenshots.
