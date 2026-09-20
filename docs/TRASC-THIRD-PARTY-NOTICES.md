# Third-party components

The app release bundles PRoot and links talloc statically. Source is pinned and the complete build recipe is in `scripts/build-proot.sh`:

- [Termux PRoot](https://github.com/termux/proot/tree/7266fb3e8516535682f5a9c8f3a7e70f6506eddb), commit `7266fb3e8516535682f5a9c8f3a7e70f6506eddb`, GPL-2.0-or-later. The relevant source licenses are in that repository. Its Android modifications are reused without depending on the Termux app.
- [Samba talloc 2.4.3](https://www.samba.org/ftp/talloc/talloc-2.4.3.tar.gz), LGPL-3.0-or-later for the library (see its source `talloc.h` and license files). The source archive is SHA-256 pinned in the build script. The cross-build configuration follows the [Termux package recipe](https://github.com/termux/termux-packages/blob/master/packages/libtalloc/build.sh).
- Debian Bookworm packages: the runtime archive includes `/etc/trasc-packages.txt` with the exact package versions and `/usr/share/doc/<package>/copyright` with license notices. Source packages are available from [Debian](https://www.debian.org/distrib/packages). Runtime includes MariaDB, Python, Git, GCC, CMake, Ninja and dependencies listed in `runtime/Dockerfile`.

The runtime is built separately from imported server source. Server and quest licenses remain those supplied by the selected repository. No proprietary EverQuest client files, maps, Winlator binaries or modified `dinput8.dll` are included.

The APK release includes `launcher-sources.tar.gz` with the pinned PRoot/talloc source archives, build recipe and patches. The recipe recreates the generated loader helper. Retain these notices and corresponding component sources when redistributing binaries. Debian package notices and the exact package list remain inside the runtime archive.

## Optional embedded client runtime

`client-runtime/Dockerfile` builds a separate Debian ARM64 environment:

- [Box64 0.4.4](https://github.com/ptitSeb/box64/tree/2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a), commit `2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a`, MIT; its license is installed under `/usr/share/doc/box64/`.
- [Wine 10.0](https://dl.winehq.org/wine/source/10.0/), LGPL-2.1-or-later, vanilla WoW64 binary from [Kron4ek's 10.0 release](https://github.com/Kron4ek/Wine-Builds/releases/tag/10.0). The exact binary archive SHA-256 is pinned in the Dockerfile. Upstream Wine source and the Box64 source accompany the release as `client-runtime-sources.tar.gz`; Kron4ek's repository documents the compiler flags and Ubuntu build environment used for its binaries.
- Debian's TigerVNC/X server, Mesa llvmpipe, fonts and support libraries. `/etc/trasc-client-packages.txt` records exact package versions and `/usr/share/doc/*/copyright` retains the package license notices. Corresponding versioned source packages are available from Debian. TigerVNC is GPL-2.0-or-later; Mesa and X components retain their respective upstream licenses.

The Android RFB client is implemented in this repository from the public protocol specification. The Windows integration-test EXE/DLL are built from `tests/client_probe*.c`; they contain no proprietary client code. No EverQuest executables, modified client DLLs, copyrighted game assets or Winlator binaries are redistributed.

## DirectX model helper installer

The APK packages [cabextract 1.11](https://www.cabextract.org.uk/) with its bundled libmspack cabinet decoder. The exact source archive (SHA-256 `b5546db1155e4c718ff3d4b278573604f30dd64c3c5bfd4657cd089b823a3ac6`) and `scripts/build-cabextract.sh` accompany the APK in `launcher-sources.tar.gz`. See that archive's COPYING and source notices for the GPL/libmspack terms.

The optional installation action downloads the [Microsoft DirectX End-User Runtimes (June 2010)](https://www.microsoft.com/en-us/download/details.aspx?id=8109) directly from Microsoft, or reads the user's matching offline EXE. It verifies the entire package SHA-256 before extracting only x86 d3dx9_30.dll and d3dx9_35.dll. Microsoft libraries retain Microsoft's license terms; none are included in this repository, APK, Linux runtime archive or published test artifacts. CI obtains the same official package temporarily to verify installation and model APIs.

## Native graphics bridge

The APK builds VirGL renderer 1.3.0 (MIT) and statically links libepoxy 1.5.10
(MIT). It calls Android's public EGL/GLES libraries; no proprietary graphics
driver, ANGLE binary, Termux application or EverQuest asset is distributed.
Source archives, the build script, launcher, Android patches and license files
are included in the published launcher-sources archive.

Selected Android portability and EGL patches come from
[Termux packages](https://github.com/termux/termux-packages/tree/4f48a30edadeff906a3cad7adfaa17e5f8d10605/packages/virglrenderer-android).
The former gl4es DXT upload patch is replaced with the MIT-licensed TRASC
block decoder in native/trasc_dxt.h and a host-storage correction. The original
patch provenance remains in git history.

The APK also carries Wine 10.0's LGPL-2.1-or-later PE32 wined3d.dll with a small
legacy GLSL specular-output correction. Its checksum-pinned source archive,
patch and build recipe are included in wined3d-sources.tar.gz inside the
published launcher-sources.tar.gz. It is mounted over the app-private runtime
module at launch; no EverQuest binary is modified or distributed.

The APK also carries Wine 10.0's LGPL-2.1-or-later x86-64 wineserver, built in
Debian Bookworm with a bounded cleanup-grace correction for translated Unix
processes. Its original Wine source, patch and Docker build recipe are in the
same wined3d-sources.tar.gz bundle. The app selects this private helper through
Wine's WINESERVER setting; the installed runtime image remains intact.

TRASC additionally patches the vtest worker lifecycle to terminate workers when their owning renderer exits. The native launcher probes Android EGL in an isolated child before serving client connections. These project modifications are included with the corresponding sources.

## Turnip / DXVK Vulkan path

The APK includes selectable Mesa 24.3.4 and 26.0.0 ARM64 glibc Turnip drivers, built for Qualcomm KGSL from the unmodified official release source (24.3.4 SHA256 `e641ae27191d387599219694560d221b7feaa91c900bcec46bf444218ed66025`; 26.0.0 SHA256 `2a44e98e64d5c36cec64633de2d0ec7eff64703ee25b35364ba8fcaa84f33f72`). Mesa's source carries its component license notices, primarily MIT. No proprietary Qualcomm driver is included.

The x86 D3D9 DLL comes from upstream DXVK 2.5.3 (zlib license), release archive SHA256 `d8e6ef7d1168095165e1f8a98c7d5a4485b080467bb573d2a9ef3e3d79ea1eb8`. Its complete tagged source archive SHA256 is `e3d8c320f1cbd134ce176be81a0c156585a1a251fd004c78d78373adff37f1ce`. The Mesa and DXVK source archives, licenses, exact Dockerfiles/build script and the project's Vulkan preflight source accompany the APK in `vulkan-sources.tar.gz` inside `launcher-sources.tar.gz`. The existing client runtime supplies the Vulkan loader; the APK adds no EverQuest assets.

## Android playback bridge

The APK adds the original TRASC ALSA PCM endpoint (MIT; native/audio-LICENSE), dynamically using the client runtime's existing ALSA library. It calls Android AudioTrack through the launcher. Endpoint source, license, Bookworm Dockerfile and build-audio.sh accompany launcher-sources.tar.gz. No new libasound binary, proprietary game sound, or microphone recording is bundled.

Mesa 26.0.0 is built using Khronos glslang 15.1.0 (source archive SHA256 `4bdcd8cdb330313f0d4deed7be527b0ac1c115ff272e492853a6e98add61b4bc`), retained in the Vulkan source bundle with its upstream license notices. This build tool is not installed into the client runtime. The comparison driver is upstream Mesa, not Winlator’s custom R5 binary.

## Launcher fonts (0.4.10)

Cinzel and Crimson Pro from https://github.com/google/fonts, distributed under the SIL Open Font License 1.1. Font files and their complete OFL/copyright notices are included in app/src/main/assets/ui. The fantasy backdrop is original AI-generated artwork commissioned for this launcher.

Microsoft Visual C++ compiler tools and Windows SDK headers/libraries are user-supplied and are not distributed by this project. In-app compilation uses the existing Wine/Box64 runtime with an isolated compiler prefix.

The native presentation/input helper statically links the MIT/X11-licensed libXdamage and libXtst client libraries. Their complete distribution copyright/license notices are bundled in the APK as `presentation-notices.txt` and in the corresponding launcher source archive.
