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

FEX with ARM64X Wine is a different execution stack, not a Box64 option. The screenshots support investigating that runtime difference but do not prove which component causes the current freeze. Importing an ARM64X Wine binary into the existing x64 Wine prefix is not a supported migration. A future FEX path requires verified redistributable binaries and sources, an isolated prefix, its own launch/cleanup path, and validation of .NET 10, graphics, input and audio on the device.

For the 0.1.8 comparison, retain current runtime/display settings and disable only the injected managed diagnostics. Avoid changing translators, driver, GC/JIT policy and renderer together before there is evidence to attribute the result.
