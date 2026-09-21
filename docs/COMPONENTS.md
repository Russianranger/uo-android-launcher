# Component provenance

- TRASC launcher reference: `Russianranger/trasc-server-android` commit `eabcb0f4075d52afc173ceee06c6ecee6d660ece`.
- Android PRoot, VirGL and native presentation binaries, ARM64 ALSA output module, X11 frame helper and Turnip 26: extracted unchanged from TRASC preview APK SHA-256 `c5d0d6e2680039dcc1e035b2adb93b4569a1da5d8d2f0ec3c4646b2e793673aa`. Applicable build scripts/native sources are retained. The release attaches the original corresponding-source archive, SHA-256 `492043660b1370e1910c8b8ca2b93be1f637f4929034f575591f14e67e015243`.
- DXVK 2.7.1 D3D11/DXGI x64 and x86: official `doitsujin/dxvk` release archive, SHA-256 `d85ce7c79f57ecd765aaa1b9e7007cb875e6fde9f6d331df799bce73d513ce87`. Source: https://github.com/doitsujin/dxvk/tree/v2.7.1 . DXVK uses the zlib license; see included DXVK-LICENSE.
- PRoot and bundled third-party licenses: [TRASC-THIRD-PARTY-NOTICES.md](TRASC-THIRD-PARTY-NOTICES.md), the native source headers, and the corresponding-source archive. Keep these notices and provide corresponding sources when redistributing binaries.
- Server source verified against `Russianranger/ultima-memento` commit `916d1ec666376ef44366c986befa3200deb93eb0`; not included in the APK. The user selects the fetched revision. Server game scripts/data keep their own licenses.
- TazUO .NET requirement verified in `PlayTazUO/TazUO` commit `3212623f63436be1c0f4e3b308b202b29597c026`, `src/Directory.Build.props`: `net10.0`. No game client/assets are distributed.
- .NET portable Windows runtime: downloaded directly from Microsoft's release metadata with its published SHA-512 hash. The imported client's runtimeconfig selects the major/minor and minimum patch version. Its license/notices remain inside the downloaded runtime.
- Icon: created with built-in Image Generation for this app. Prompt: “retro 16-bit fantasy pixel-art heraldic shield with large gold UO letters, burgundy face, gold beveled metal rim, dark background, no other text.” Full-resolution original: `artwork/uo-shield.png`.

The 0.2.0 client uses a separate native ARM64 Wine/FEX runtime; earlier releases used Wine/Box64. Logs distinguish startup failure from a successful client process; Android/host CI cannot validate Adreno acceleration or a Memento login on the Thor.

## 0.1.1 runtime overlay

- XComposite: Debian Bookworm `libxcomposite1` ARM64, version `1:0.4.5-1`, from `https://deb.debian.org/debian/pool/main/libx/libxcomposite/libxcomposite1_0.4.5-1_arm64.deb`. SHA-256: `cfe39326fdb822e9d060ed5eb3f95b14459dd6b73793c5290000f9b27f8bad37`.
- Only `libXcomposite.so.1.0.0` is copied into the APK as `libXcomposite.so.1`; its Debian copyright/license file is included as `libXcomposite-COPYRIGHT` in the APK assets. The library uses the MIT/X11 license. Source package: `https://deb.debian.org/debian/pool/main/libx/libxcomposite/`.
- The overlay is loaded from `/opt/uo-client` with `LD_LIBRARY_PATH`; the installed runtime archive and package database are unchanged.

## Managed-loader regression (0.1.2)

- Evidence: the user's 0.1.1 support bundle reaches bundled CoreCLR 10.0.8, then Wine reports `fixup_imports_ilonly mscoree.dll not found` for `System.Runtime.dll` and the process exits with code 82.
- Wine 10 implementation: [dlls/ntdll/loader.c, fixup_imports_ilonly](https://github.com/wine-mirror/wine/blob/wine-10.0/dlls/ntdll/loader.c). This loader imports `mscoree.dll` for IL-only modules independently of which CLR hosts the app.
- The CI probe uses the same checksum-pinned Wine 10.0 WoW64 archive as the client runtime and Microsoft's `Microsoft.NETCore.App.Runtime.win-x64` 10.0.8 runtime pack. Probe source is in `tests/managed-probe`; it contains no game files.

## Client configuration regression (0.1.3)

- The 0.1.2 support bundle and screenshot show TazUO's UO-directory error, followed by an empty client-version warning. The launcher had written an unknown `ultimaonline` property and only prepared the path during import.
- Schema and startup checks: [TazUO Settings.cs](https://github.com/PlayTazUO/TazUO/blob/3212623f63436be1c0f4e3b308b202b29597c026/src/ClassicUO.Client/Configuration/Settings.cs) and [Main.cs](https://github.com/PlayTazUO/TazUO/blob/3212623f63436be1c0f4e3b308b202b29597c026/src/ClassicUO.Client/Main.cs) use `ultimaonlinedirectory`, `clientversion`, `Directory.Exists` and `tiledata.mul`.
- The default for blank versions, **7.0.15.1**, is documented by [Memento desktop setup](https://uo-memento.com/setup/desktop-client/#server-information), verified September 20, 2026. This is the UO data/protocol version, independent of the modern TazUO/.NET build.
- The CI fixture uses the reported `Ultima-Memento/Client/TazUO-Launcher/TazUO` and `Ultima-Memento/Client/Data Files` layout. Its .NET probe verifies Windows access through Wine's D: drive after the production configuration repair; fixture data files contain no game assets.

## SDL Vulkan compatibility preview (0.1.10)

- SDL 3.4.16 Windows x64: official [release](https://github.com/libsdl-org/SDL/releases/tag/release-3.4.16), zlib license. Archive SHA-256 `4217944b4e51457af4a59c82d883f8443b3e65964b2acd8943484c492756c4b6`; DLL SHA-256 `1f98969319302a100931f4385e5918a0bd53ab07773040682d22e7edb54858c0`. `SDL3-LICENSE.txt` is bundled in APK assets. Source: [SDL release-3.4.16](https://github.com/libsdl-org/SDL/tree/release-3.4.16).
- The replacement allowlist is the x64 SDL3/FNA3D pair at [TazUO 5.2 commit 73768f6](https://github.com/PlayTazUO/TazUO/tree/73768f6653d39788b00f5bce5b2a063dc76452aa/external/x64). Original SDL SHA-256 `f53fbe656b784365dc1db0de61958a51a41b5923ab9623bf2f7af4eca9649c09`; FNA3D SHA-256 `93ca16fb415438830bd1591ac25fabb92a2b532cb629b215c8bd7d73ca806eb8`. These imported libraries are not distributed by the launcher.
- The Wine-only graphics fixture downloads that pinned FNA3D DLL and uses the FNA3D 25.11 header at `de4870e6cd215ea97ea6109cc72c25c0276f1bec`. SDL MinGW SDK archive SHA-256 `c7ef65bd72eabac6e5b535411dbd8d5824d0aab24fd62ff8812666b336f18a9c`. Test downloads are excluded from the APK/source archive.
- Relevant upstream fixes: [allocation refcounting during pending transfers](https://github.com/libsdl-org/SDL/pull/15127), [pending-transfer cleanup indexing](https://github.com/libsdl-org/SDL/commit/f8b7e22d7d1d143f085a1b355e674b05025ef114), and [texture barriers during defrag](https://github.com/libsdl-org/SDL/pull/15593). These candidate fixes are present in the bundled version. The exact Thor `vkDestroyImageView` fault has not been reproduced by host CI.

## Native Wine/FEX runtime (0.2.0)

- Wine ARM64EC: [bylaws/wine](https://github.com/bylaws/wine/tree/a6844d10622fc1a973ec1f22fc4f78a0fcd6cb29), Wine 10.13 base, LGPL-2.1-or-later. The full pinned source is attached as `wine-arm64ec-source.tar.gz`.
- FEX: [FEX-Emu/FEX](https://github.com/FEX-Emu/FEX/tree/320c5f18475b0c8a7e99c51a5fdc5b5e35b147ab), FEX-2510, MIT with bundled third-party notices. `fex-2510-source-with-submodules.tar.gz` includes the complete source and pinned submodules used to build both ARM64EC and WoW64 PE modules.
- ARM64EC compiler: bylaws LLVM-MinGW 20250920, ARM64 Linux archive SHA-256 `bce5cc755c613515fd44e1ee9523123d854103abae147571adb645450036274d`. Build-only dependency, not installed on Android.
- Native Debian 12 packages and their notices remain in the rootfs; exact installed versions are listed in `/etc/memento-client-packages.txt`. No amd64 Linux packages, Box64 or Bionic FEX Unix libraries are included.
- `client-runtime/Dockerfile`, `scripts/check-fex-runtime.sh` and `scripts/pack-fex-runtime.py` are the build, verification and packaging recipes. Bannerlator was a research reference; no Bannerlator application code is bundled. See [runtime comparison](RUNTIME-COMPARISON.md).
