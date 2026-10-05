# UO Memento Mobile 0.2.20

Reduces the repeated map metadata checks proven to dominate cold loading in the 0.2.19 Thor test. A cold interior chunk spent 6,558.669 of 6,578.185 ms inside 2,115 file-length getters; initial-area chunks show the same pattern. The new **Faster map loading** option defaults ON and reuses successful map-length results only within one synchronous chunk construction. Stable three-reader chunks can reduce those getter calls to three.

Each chunk and thread has its own bounded scope. The first getter still runs, exceptions are not cached, disposed streams bypass reuse, and replacing a reader obtains a fresh value. Every later chunk rereads lengths. Same-reader growth or truncation during construction becomes visible on the next chunk; no file lengths are frozen for the session. Actual file reads, lookup, terrain calculations, object ordering and texture uploads remain.

Install over the working app and retain data, client, caches and accepted Wine/FEX runtime. Keep optional SDL OFF. Leave Faster map loading ON, enable existing Cold-load timing for one marked cold outdoor/interior and warm-revisit comparison, and export the complete ZIP. The retained 0.2.19 export is the before baseline. Turn cold timing OFF afterward for normal play. Faster map loading OFF plus a fresh client restores the exact prior supported client and preserves the 0.2.19 diagnostic path.

All eight exact input variants are checksum gated, with validated backups and interrupted-launch restoration. The existing revision-4 managed and revision-2 native observers remain; resource CPU queries remain disabled. Native Surface/changed regions/geometry caching, original SDL/FNA, atlas batching, packet budget, audio, controls, server, saves, viewport and signing identity remain.

Publication requires the existing gates plus exact-client metadata regression checks under host .NET, Wine, ARM64 FEX, compatibility/accelerated PRoot and packaged APK deltas. Reduced getter counts are a qualification result; actual hitch reduction on Thor still requires the physical comparison.

See the [focused test](https://github.com/Russianranger/uo-android-launcher/releases/download/v0.2.20/UO-Memento-Mobile-0.2.20-Instructions.txt), [physical attribution](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/THOR-0.2.19-ANALYSIS.md) and [implementation/lifetime](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/OPTIMIZATION-0.2.20.md).
