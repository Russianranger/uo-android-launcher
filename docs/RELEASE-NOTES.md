# UO Memento Mobile 0.2.18

Corrects the diagnostic startup slowdown that left 0.2.17 black before login. On Thor, tiledata loading took about 132 seconds instead of the previous 5–6 seconds. The new resource observer made two Wine CPU-time queries around every tiny read; those queries sat outside its reported operation time. This release removes resource-scoped CPU queries and exposes resource-window observer overhead during startup.

Resource/decode/read/lock wall, self, nested FNA and allocation observations remain, along with the existing frame/EndDraw/native CPU, packet, atlas, GC, Vulkan correlation and Android presentation records. Managed cold diagnostics report revision 3; the unchanged native observer reports revision 2. This fixes diagnostic overhead and does not select another game-performance optimization.

Install over the current app and retain data, imported client and Wine/FEX runtime. Keep optional SDL OFF and original SDL active. First test login/world entry with Cold-load timing ON, then the marked cold/warm route and interior phases. Turning cold timing OFF still restores the existing verified client/atlas assemblies for normal play.

Native Surface, changed regions, Surface geometry caching, signing/upgrade compatibility, audio, server, controller/input, 1280×720 canvas / 1098×720 world, the existing packet budget, 0.2.13 summaries and 0.2.14 atlas batching remain. The touch quick-menu return label remains **Back to Launcher Menu**.

See the [test procedure](https://github.com/Russianranger/uo-android-launcher/releases/download/v0.2.18/UO-Memento-Mobile-0.2.18-Instructions.txt), [device evidence](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/THOR-0.2.17-STARTUP-REGRESSION.md) and [diagnostic guide](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/DIAGNOSTICS-0.2.18.md). Analyze the new Thor logs before selecting a performance change.
