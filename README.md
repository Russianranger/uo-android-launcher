# UO Memento for Android

## Updating Recovery to 0.1.3

Save and close the realm runtime, stop the client, then install the 0.1.3 APK over **UO Memento Recovery**. The package ID and signing certificate are unchanged. Keep app data; no server rebuild, client reimport, .NET download or migration is needed.

This update fixes TazUO's “could not find the UO directory” error. The launcher now writes `ultimaonlinedirectory`, the key TazUO actually reads, and repairs earlier imports on launch. Blank client versions use Memento's documented asset/protocol version **7.0.15.1**; existing versions, credentials, plugins and other settings are retained. The original settings backup is preserved. Missing required data files are reported before Wine starts.

Retry with **Turnip / 1280×720 / Native Surface / 60 FPS**. Export **Journal → Export support logs** afterward; `client-config.json` records the resolved data path and version without saved credentials. The Wine 10 / bundled .NET 10.0.8 CI probe verifies both the managed-loader fix from 0.1.2 and access to the reported nested data folder. Graphics, gameplay and Box64 compatibility still require device testing.

## 0.1.1 recovery build

The original preview's signing key was not saved by CI, so 0.1.1 installs separately as **UO Memento Recovery**. Keep the original app installed; do not clear its data. The new APK fixes log export and the evidenced Wine startup issues.

Use the [recovery guide](docs/RECOVERY.md) to copy your complete installation with the supplied ADB tool, or export the world from the old Saves tab and set up the recovery app separately. The tool can also export the old logs without using the broken export button.

After migration, retry **Client → Launch TazUO** and export a support ZIP from the Journal. On-device .NET 10 gameplay remains unverified.


A standalone ARM64 Android launcher for **Ultima Memento + the imported Windows TazUO client**, with a gold UO shield and a retro fantasy interface.

## First test on the AYN Thor

1. Install the APK. Open **Realm → Install realm runtime**, then **Open runtime → Prepare Mono compiler**. These first downloads require internet.
2. Use **Pull & compile** with `main` to fetch `Russianranger/ultima-memento`. You can also enter a tag or commit SHA. The source revision appears after compilation.
3. In **Client**, import your **complete Windows Memento client folder or ZIP**, including `TazUO.exe` (or `ClassicUO.exe`), its DLL/runtimeconfig, and the Memento asset directory. ZIPs may contain an outer folder. Include exactly one client and one asset directory with `tiledata.mul`, `cliloc.enu`, and `map0.mul`. Your imported settings, client version, credentials and plugins are retained; the server address and asset path are prepared for this app.
4. Select **Install client runtime**, then **Prepare required .NET**. The app detects the required version and x64/x86 architecture and downloads Microsoft's matching portable runtime with SHA-512 verification. A self-contained client uses its included runtime.
5. Return to **Realm → Start server**. Wait for **ONLINE**; first-start script compilation can take several minutes. If it fails, read `server.log` in Journal.
6. Launch TazUO with **Turnip 26 + DXVK**, **1280×720**, **Native Surface**, **60**, audio enabled. Start with **Test Wine desktop** if client startup fails. The gear menu provides keyboard, Esc, mappings and return to the launcher.
7. Log in, enter the world, move, open inventory, test targeting and audio. LT cycles the four initial layers and displays the active layer at the top. Map your TazUO macros to the chosen keys. Do not enable conflicting native controller bindings in TazUO.
8. Log out, use **Save & stop**, restart the server and confirm the character and items persist. Create and export a world backup. Use **Journal → Export support logs** to report any issue.

This is an initial device-test preview. Android compilation, automated input/import/backup checks and CI server compilation are distinct from a successful Thor game session. TazUO .NET 10 under Wine/Box64 still requires device verification; a working TRASC RoF2 session does not prove that newer CoreCLR and TazUO will work. VirGL/OpenGL and software rendering are comparison paths. The app does not invoke installed Winlator or Termux.

## Controller methodology

The input engine, relative mouse transport, editable profiles, up to six named layers, hold/cycle/switch actions, and on-screen layer notification are adapted from TRASC. Inputs release on focus loss, disconnect, layer changes and menus.

| Control | Initial action |
|---|---|
| Left stick | Arrow keys (TazUO movement) |
| Right stick | Mouse pointer |
| RB / LB | Left / right mouse button |
| LT / RT | Next layer / Tab |
| A / X / Y / B | F / 1 / 2 / 3 |
| D-pad up / right / down / left | 4 / 5 / 6 / 7 |
| Select / Start | Esc / I |
| L3 / R3 | Home / C |

## Storage and world updates

Everything is app-private, independent of TRASC. Uninstalling deletes it, so export backups first. Server state is saved through a Memento Timer on its main thread, followed by `World.WaitForWriteCompletion()`. A missing save acknowledgement leaves the server running and reports the failure. Source updates back up and preserve `Saves`, `Info`, `Data` and `Backups`, compile in staging, and retain the previous deployment. No changes are pushed to the Memento source repository.

World archives include accounts and characters but exclude game asset files and runtime downloads. Restores stage a complete deployment and back up the current world before activating it. Failed or unsafe client imports leave the existing client intact. Updates preserve existing configuration; changes to upstream settings may need review against your retained `Info` files.

## Build

JDK 17, Gradle 8.11.1, Android SDK 35/build tools 35.0.0:

```sh
python3 -m unittest discover -s tests -v
bash scripts/check-input.sh
python3 scripts/prepare-assets.py
gradle --no-daemon :app:assembleDebug :app:lintDebug
```

The APK bundles verified ARM64 PRoot, display, audio, VirGL and Turnip components plus DXVK 2.7.1 D3D11/DXGI for x64 and x86. The server runtime currently reuses TRASC's Debian compiler rootfs and installs Mono into this app's separate copy; the client runtime reuses its Wine 10 WoW64/Box64 0.4.4 rootfs. This preserves the known Android integration without requiring a separately published UO rootfs. Runtime downloads validate their manifests and checksums. Offline archive imports are available for both rootfs downloads.

The internal Java/JNI namespace is retained for compatibility with the reused native display library; the current Android application ID is **`io.github.russianranger.uomemento.recovery`**. Realm control binds `127.0.0.1:18785`, game service `127.0.0.1:2593`; client X11 uses `:8` with a random cookie and local Unix sockets. No RFB TCP listener is exposed.

See [component provenance](docs/COMPONENTS.md) and [release notes](docs/RELEASE-NOTES.md).
