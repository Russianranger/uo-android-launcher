# Music cache: verified binary and deployment

The initial 0.2.5 source fix could not be enabled using only the earlier TazUO/FNA upload: SoundsLoader is in a separate Assets assembly. The public client linked by [Memento 2.4.1](https://github.com/Jascen/ultima-memento/releases/tag/2.4.1) supplied the missing counterpart. Both its TazUO.dll and FNA.dll match the uploaded files exactly.

| Component | SHA-256 |
|---|---|
| Original TazUO.dll | `b04066be1b1b475ca00e6982a980e2dd11b93abede00c79c68bde566bdcf947e` |
| Original FNA.dll | `399c91458ccbd08bcd8094bde39a1091f5edd545fd77a9b4579016e7ac5498c6` |
| Original ClassicUO.Assets.dll | `1dd53cf0eea718aefeda33fba105c9797b138188be22562b47548c310524100d` |
| Cached ClassicUO.Assets.dll | `84340a487aeae33c0f17ae1b20a0c8d1b54122d1e23801e5a582452c7db905c9` |

The patch caches Directory.GetFiles' returned array per SoundsLoader instance. Array.FindAll, original Regex semantics, result order and warnings are untouched. Load and ClearResources clear the cache. Only those two methods and GetTrueFileName change; 439 other methods, 365 constants and all embedded resources remain unchanged. Assembly identity, architecture, module attributes and dependency references are checked too. The private helper adds no external dependency.

`diagnostics/music-patcher` generates the delta input offline. `backend/client_music_cache.py` uses the existing bounded BSDIFF decoder and atomic checksum-checked writer. It preserves `ClassicUO.Assets.dll.before-memento-music-cache`, supports idempotent launches and restores the original when disabled. It never overwrites an unrecognized DLL, including an upstream client update. The APK contains only the delta and installer, not the full client assembly or Cecil.

`tests/music-probe` runs the actual original and patched assemblies against synthetic sound/index/music files, using separate assembly contexts. It verifies Load/config results, case/ambiguous/regex matches, an unchanged cache across 200 lookups, refresh after adding tracks, ClearResources, reload with another base directory and missing-directory errors. CI repeats this under Windows .NET 10.0.8 through Wine. A production test regenerates the assembly, compares the shipped delta output byte-for-byte, reapplies it and restores the original bytes.

`scripts/fetch-music-fixture.py` reads only pinned DLL members using HTTP ranges from the public ZIP. Every output is checksum verified; an upstream change fails the fixture gate. Game files and complete client assemblies are not committed or bundled with the APK. The corresponding source-level change remains in `patches/tazuo-music-cache.patch`.

The audio/display changes and the 0.2.4 session measurements are documented in [0.2.5 scope](OPTIMIZATION-0.2.5.md). Music caching was pending in 0.2.5 and is enabled for the checksum-matched assembly in 0.2.6. Performance on the Thor remains a device measurement, not an inference from the probe.
