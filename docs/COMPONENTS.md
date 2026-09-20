# Component provenance

- TRASC launcher reference: `Russianranger/trasc-server-android` commit `eabcb0f4075d52afc173ceee06c6ecee6d660ece`.
- Android PRoot, VirGL and native presentation binaries, ARM64 ALSA output module, X11 frame helper and Turnip 26: extracted unchanged from TRASC preview APK SHA-256 `c5d0d6e2680039dcc1e035b2adb93b4569a1da5d8d2f0ec3c4646b2e793673aa`. Applicable build scripts/native sources are retained. The release attaches the original corresponding-source archive, SHA-256 `492043660b1370e1910c8b8ca2b93be1f637f4929034f575591f14e67e015243`.
- DXVK 2.7.1 D3D11/DXGI x64 and x86: official `doitsujin/dxvk` release archive, SHA-256 `d85ce7c79f57ecd765aaa1b9e7007cb875e6fde9f6d331df799bce73d513ce87`. Source: https://github.com/doitsujin/dxvk/tree/v2.7.1 . DXVK uses the zlib license; see included DXVK-LICENSE.
- PRoot and bundled third-party licenses: [TRASC-THIRD-PARTY-NOTICES.md](TRASC-THIRD-PARTY-NOTICES.md), the native source headers, and the corresponding-source archive. Keep these notices and provide corresponding sources when redistributing binaries.
- Server source verified against `Russianranger/ultima-memento` commit `916d1ec666376ef44366c986befa3200deb93eb0`; not included in the APK. The user selects the fetched revision. Server game scripts/data keep their own licenses.
- TazUO .NET requirement verified in `PlayTazUO/TazUO` commit `3212623f63436be1c0f4e3b308b202b29597c026`, `src/Directory.Build.props`: `net10.0`. No game client/assets are distributed.
- .NET portable Windows runtime: downloaded directly from Microsoft's release metadata with its published SHA-512 hash. The imported client's runtimeconfig selects the major/minor and minimum patch version. Its license/notices remain inside the downloaded runtime.
- Icon: created with built-in Image Generation for this app. Prompt: “retro 16-bit fantasy pixel-art heraldic shield with large gold UO letters, burgundy face, gold beveled metal rim, dark background, no other text.” Full-resolution original: `artwork/uo-shield.png`.

The first release is a compatibility preview. The inherited Wine/Box64 execution path has not been replaced with Winlator's FEX/ARM64EC runtime. Logs distinguish startup failure from a successful client process; Android/host CI cannot validate Adreno acceleration or a Memento login on the Thor.

## 0.1.1 runtime overlay

- XComposite: Debian Bookworm `libxcomposite1` ARM64, version `1:0.4.5-1`, from `https://deb.debian.org/debian/pool/main/libx/libxcomposite/libxcomposite1_0.4.5-1_arm64.deb`. SHA-256: `cfe39326fdb822e9d060ed5eb3f95b14459dd6b73793c5290000f9b27f8bad37`.
- Only `libXcomposite.so.1.0.0` is copied into the APK as `libXcomposite.so.1`; its Debian copyright/license file is included as `libXcomposite-COPYRIGHT` in the APK assets. The library uses the MIT/X11 license. Source package: `https://deb.debian.org/debian/pool/main/libx/libxcomposite/`.
- The overlay is loaded from `/opt/uo-client` with `LD_LIBRARY_PATH`; the installed runtime archive and package database are unchanged.

## Managed-loader regression (0.1.2)

- Evidence: the user's 0.1.1 support bundle reaches bundled CoreCLR 10.0.8, then Wine reports `fixup_imports_ilonly mscoree.dll not found` for `System.Runtime.dll` and the process exits with code 82.
- Wine 10 implementation: [dlls/ntdll/loader.c, fixup_imports_ilonly](https://github.com/wine-mirror/wine/blob/wine-10.0/dlls/ntdll/loader.c). This loader imports `mscoree.dll` for IL-only modules independently of which CLR hosts the app.
- The CI probe uses the same checksum-pinned Wine 10.0 WoW64 archive as the client runtime and Microsoft's `Microsoft.NETCore.App.Runtime.win-x64` 10.0.8 runtime pack. Probe source is in `tests/managed-probe`; it contains no game files.
