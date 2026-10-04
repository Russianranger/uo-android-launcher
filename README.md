# UO Memento Mobile

## Updating to 0.2.18

This corrective diagnostic release addresses the black screen before login reported with 0.2.17. The client was progressing through startup assets extremely slowly: the new resource observer made two Wine CPU-time queries for each tiny primitive read. 0.2.18 removes those resource-scoped CPU queries while retaining wall/self/FNA/lock/allocation records, frame/EndDraw/native CPU measurements and bounded graphics correlation. Resource-window overhead is now visible even before the first game frame. See the [device evidence](docs/THOR-0.2.17-STARTUP-REGRESSION.md).

Install **UO-Memento-Mobile-0.2.18.apk** over the current app, keeping data/runtime/client. Leave **Use SDL 3.4.16 (optional) OFF**, use **Cold-load timing (Thor test) ON** for the launch check, and keep the working Turnip / Native Surface / changed regions / Smooth world loading / music / layout / input settings. First confirm login and world entry, then perform the marked traversal test and export the complete ZIP. See the [short procedure](docs/UO-Memento-Mobile-0.2.18-Instructions.txt) and [updated diagnostic guide](docs/DIAGNOSTICS-0.2.18.md). Thor validation is still required before claiming the startup regression is resolved.

## Updating to 0.2.17

This diagnostic pass follows the measured native fence/submission stalls and the remaining long Draw time. **Cold-load timing (Thor test)** adds resource/loading/lock observations and bounded Vulkan fence, submission and command/resource correlation. It retains the existing frame, packet, atlas, GC/CPU and Android presentation records. Enable it for a fresh marked outdoor/interior/retrace test, then export the complete Journal ZIP.

The diagnostic session uses **original SDL 3.2.27**, including restoration from the verified backup if the optional update preference was left on. Keep **Use SDL 3.4.16 (optional)** OFF on Thor. Install **UO-Memento-Mobile-0.2.17.apk** over the working app with data/runtime/client retained; keep current Turnip, Native Surface, changed regions, Smooth world loading, music caching, 60 FPS, layout, audio and controller choices. See the [short procedure](docs/UO-Memento-Mobile-0.2.17-Instructions.txt) and [record guide and limits](docs/DIAGNOSTICS-0.2.17.md). This pass adds diagnostics; the logs still determine the next performance change.

## Updating to 0.2.16

This diagnostic build investigates the remaining cold first-visit pauses measured on Thor. **Client → Client options → Cold-load timing (Thor test)** adds bounded individual long-frame records, FNA/native Vulkan timing and **Mark test phase** in the touch menu. It defaults off. Enable it for one fresh outdoor/interior/re-entry/retrace session, then export the complete Journal ZIP before selecting the next optimization.

Install **UO-Memento-Mobile-0.2.16.apk** over the working app, retaining data/runtime/client, the current 60 FPS and other settings. Keep Smooth world loading on and the older detailed/crash tracing off. See the [short Thor procedure](docs/UO-Memento-Mobile-0.2.16-Instructions.txt) and [record guide, reversibility and limits](docs/DIAGNOSTICS-0.2.16.md). This release makes no new performance optimization or claim that the stutters are fixed.

Keep **Use SDL 3.4.16 (optional)** OFF on Thor. The device comparison ended in an Android low-memory termination; the earlier recommendation to enable it is withdrawn. Turning it off and starting a fresh client restores the verified original library from its retained backup. See the [failure evidence and recovery procedure](docs/THOR-0.2.16-SDL-FAILURE.md).

## Updating to 0.2.15

The touch quick-menu return action now says **Back to Launcher Menu**; matching display-failure messages use the same destination. Install **UO-Memento-Mobile-0.2.15.apk** over your working app, retaining its data/runtime/client. This release contains the wording correction and [0.2.14 Thor telemetry analysis](docs/THOR-0.2.14-ANALYSIS.md); it introduces no new performance change. See the [short device check](docs/UO-Memento-Mobile-0.2.15-Instructions.txt).

## Updating to 0.2.14

The latest first-visit traces show repeated FNA presentation waits while Android copy/post stays inexpensive. This update coalesces adjacent new terrain/animation atlas uploads on the supported Turnip client, reducing separate GPU upload commands with unchanged sprite pixels and ordering. Staging is bounded to 4 MiB; drawing, readbacks, mutations and disposal flush it before proceeding. It retains the Surface geometry fix, packet budget, music cache and existing launcher features.

Install **UO-Memento-Mobile-0.2.14.apk** over your working app after logging out and saving/stopping the session. Keep app data and the installed runtime/client. Keep your current 60 FPS and other settings, **Smooth world loading** on, and **Render trace** / **Managed diagnostics** off. Compare the same fresh route/interior with two revisits, then export Journal logs. See the [device checklist](docs/UO-Memento-Mobile-0.2.14-Instructions.txt) and [implementation and limitations](docs/OPTIMIZATION-0.2.14.md). Actual improvement on Thor still requires this comparison.

## Updating to 0.2.13

This diagnostic update isolates first-visit area and interior stalls. The latest 0.2.12 Thor logs show that repeated Surface setup is fixed, while one network/update stall lasted about 4.5 seconds and other long frame gaps occurred outside the existing update timings. Warm routes were much smoother. Those measurements do not yet identify which asset, packet handler or graphics operation caused the pauses.

With **Smooth world loading** enabled, the existing five-second summaries now include registered packet-handler dispatch timing and packet IDs, separated by network/plugin origin, plus game drawing, presentation and music-switch timing. This adds evidence for the next loading change; it does not change asset loading, texture creation, graphics calls or the existing packet budget.

Install **UO-Memento-Mobile-0.2.13.apk** over your working app after logging out and saving/stopping the session. Keep app data and the installed runtime/client. The exact supported client is upgraded from its verified original backup on launch; no runtime reinstall or client reimport is needed. Keep your current 60 FPS, resolution, graphics and audio settings, **Smooth world loading** on, and **Render trace** / **Managed diagnostics** off. Start a fresh client, reproduce a cold route and first interior visit, then repeat them two or three times in the same process. Note the clock time and action at each large stutter, then export support logs from Journal. See the [short device checklist](docs/UO-Memento-Mobile-0.2.13-Instructions.txt) and [evidence and diagnostic scope](docs/OPTIMIZATION-0.2.13.md).

## Previous update: 0.2.12

Native Surface now retains its successful buffer configuration for the current Surface reader. A larger onscreen view no longer causes buffer setup and a forced full redraw on every changed frame. New readers and actual game-resolution changes still configure and redraw a complete baseline; Android's returned redraw bounds remain authoritative.

Install **UO-Memento-Mobile-0.2.12.apk** over your working app after logging out and saving/stopping the session. Keep app data and your installed runtime/client. Leave **Send changed regions** enabled and compare cursor/gump movement, walking and app resume using the [device checks](docs/UO-Memento-Mobile-0.2.12-Instructions.txt) and [fix details](docs/OPTIMIZATION-0.2.12.md).

## Previous update: 0.2.11

The app is now named **UO Memento Mobile**. It updates the existing Recovery installation with the same application identity and certificate; keep app data and your installed runtime/client.

Native Surface can deliver exact changed regions instead of a complete image on every changed frame. It redraws Android's returned Surface bounds from a complete retained image, including buffer-age expansion. Initial connections, resizing and broad changes still deliver full frames. Full X11 readback is retained.

**Client → Client options → Send changed regions** is enabled by default. Turn it off and restart the client for a full-frame comparison. Capture, transport, comparison, copy and Surface counters distinguish smaller transfers from actual device savings; display posts are not game FPS.

Install **UO-Memento-Mobile-0.2.11.apk** over Recovery after logging out and saving/stopping the session. See the [device checks](docs/UO-Memento-Mobile-0.2.11-Instructions.txt), [delivery design and measurement guide](docs/OPTIMIZATION-0.2.11.md) and [release notes](docs/RELEASE-NOTES.md).

## Previous update: Recovery 0.2.10

This pass adds a persistent backup browser, a touch-friendly server settings editor, complete session controls, and four generated UO-inspired backgrounds that follow the selected tab.

1. Log out, save and stop your existing session, then install **UO-Memento-0.2.10-Recovery.apk** over Recovery, keeping app data. Your working runtime, client, graphics and audio settings are retained.
2. Use **Save & close session** next to Play to close the client, save the world and close the realm runtime. During Play startup, **Cancel launch & close** requests the same graceful shutdown. The notification uses the same sequence.
3. In **Saves**, **Save & export** closes the client, saves/stops the server, creates a three-folder ZIP and opens Android's destination picker. The persistent list shows existing app backups, creation times, sizes and completed exports; it is available with the runtime off. You can preview, restore, export or delete an app copy, or explicitly remove older copies while keeping the newest 3, 5 or 10. Nothing is pruned automatically.
4. **Import & preview a ZIP** displays included folders and file counts before restoration. Confirming a restore saves/closes the current session first and automatically creates a pre-restore backup. Existing app archives remain in the list after restoration. Only `Info`, `Saves` and `Backups` are transferred.
5. In **Realm → Server settings**, load the installed settings, search or select a category, and edit values. Stop the server before applying. The app validates values and compiles the candidate settings before an atomic replacement. **Discard edits** resets the draft; **Undo last applied edit** restores the exact previous settings file. Local connection values are managed by the launcher; custom expressions and settings defined in a custom override file are preserved and shown read-only.

See [release notes](docs/RELEASE-NOTES.md), [device test instructions](docs/UO-Memento-0.2.10-Instructions.txt) and [artwork prompts](docs/ARTWORK-0.2.10.md).

## Previous update: Recovery 0.2.9

This update limits save-data transfers to **Info, Saves and Backups**, groups client settings in a collapsed **Client options** menu, and adds **Play Memento** to open the realm runtime, start the server, wait for it to be ready, and launch TazUO.

1. Stop the client and save/stop the realm, then install **UO-Memento-0.2.9-Recovery.apk** over Recovery, keeping app data. Existing installations do not need their runtimes or client imported again.
2. Tap **Play Memento** after setup is complete. **Start server** also opens the installed realm runtime automatically. First-time installation and repair controls are under setup sections.
3. Open **Client options** to change graphics, resolution, display mode, FPS, audio, performance or diagnostic settings. Your existing values are retained; restart the client to apply changes.
4. Use **Saves** to export or import save data. New ZIPs contain only `Info/`, `Saves/` and `Backups/`; installed `Data` and server files are not replaced by an import. Save and stop the server before transferring data.

See [release notes](docs/RELEASE-NOTES.md) for the supported archive formats and device checks.

## Previous audio update: 0.2.8

This update targets audio delivery overhead with buffered socket reads and playback-worker priority. It keeps the working 40 ms audio ring and immediate startup behavior, along with the existing Wine/FEX runtime, music cache, world-loading budget, graphics, controls and viewport.

1. Stop the client and save/stop the realm, then install the APK over **UO Memento Recovery**, keeping app data. No runtime reinstall or client reimport is needed.
2. Keep your existing settings. The tested baseline is **Client acceleration**, **WASAPI**, **Turnip / Native Surface**, **30 FPS**, and **1280×720 with the 1098×720 world view**.
3. Leave **Smooth audio delivery**, **Smooth world loading** and **Cache music folder during loading** enabled.
4. Test music, short sound effects and the same walking route for 10–15 minutes, including the first few minutes after launch. Log out and export support logs. If audio is worse, turn **Smooth audio delivery** off, stop and relaunch the client, and compare the same route. This restores ordinary worker priority and unbuffered reads.
5. Open the world map, close it and reopen it. Its first image generation is already cached by TazUO; compare the second opening without deleting the cache. Report if the long pause repeats on the same unchanged map.

Audio gains still need device testing. See [release notes](docs/RELEASE-NOTES.md) and [audio and map investigation](docs/AUDIO-0.2.8.md). The retained world-loading patch applies only to the checksum-matched TazUO 5.2.0 DLL; see [its verification details](docs/OPTIMIZATION-0.2.7.md).

## 0.1.1 recovery build

The original preview's signing key was not saved by CI, so 0.1.1 installs separately as **UO Memento Recovery**. Keep the original app installed; do not clear its data. The new APK fixes log export and the evidenced Wine startup issues.

Use the [recovery guide](docs/RECOVERY.md) to copy your complete installation with the supplied ADB tool, or export the world from the old Saves tab and set up the recovery app separately. The tool can also export the old logs without using the broken export button.

After migration, retry **Play Memento** and export a support ZIP from the Journal. World entry is now verified on the Thor; longer-session stability is still under investigation.


A standalone ARM64 Android launcher for **Ultima Memento + the imported Windows TazUO client**, with a gold UO shield and a retro fantasy interface.

## First test on the AYN Thor

1. Install the APK. Open **Realm → Realm setup & updates → Install realm runtime**, then **Open runtime → Prepare Mono compiler**. These first downloads require internet.
2. Use **Pull & compile** with `main` to fetch `Russianranger/ultima-memento`. You can also enter a tag or commit SHA. The source revision appears after compilation.
3. In **Client → Client setup & import**, import your **complete Windows Memento client folder or ZIP**, including `TazUO.exe` (or `ClassicUO.exe`), its DLL/runtimeconfig, and the Memento asset directory. ZIPs may contain an outer folder. Include exactly one client and one asset directory with `tiledata.mul`, `cliloc.enu`, and `map0.mul`. Your imported settings, client version, credentials and plugins are retained; the server address and asset path are prepared for this app.
4. Select **Install FEX runtime**, then **Prepare required .NET**. The app detects the required version and x64/x86 architecture and downloads Microsoft's matching portable runtime with SHA-512 verification. A self-contained client uses its included runtime.
5. Tap **Start server** at the top. Wait for **ONLINE**; first-start script compilation can take several minutes. If it fails, read `server.log` in Journal.
6. Tap **Play Memento** with **Turnip 26 · Vulkan**, **1280×720**, **Native Surface**, **30 FPS**, WASAPI audio and client acceleration enabled. Use **Client options → Test Wine desktop** if client startup fails. The gear menu provides keyboard, Esc, mappings and return to the launcher.
7. Log in, enter the world, move, open inventory, test targeting and audio. LT cycles the four initial layers and displays the active layer at the top. Map your TazUO macros to the chosen keys. Do not enable conflicting native controller bindings in TazUO.
8. Log out, use **Save & stop**, restart the server and confirm the character and items persist. Create and export a world backup. Use **Journal → Export support logs** to report any issue.

This is an initial device-test preview. Android compilation, automated input/import/backup checks and CI server compilation are distinct from a successful Thor game session. The previous Box64 runtime reached the world on the Thor but remained unstable. The new FEX runtime requires a fresh device session. VirGL/OpenGL and software rendering are comparison paths. The app does not invoke installed Winlator or Termux.

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

Save-data archives contain only `Info`, `Saves` and `Backups`, matching the [Memento upgrade procedure](https://github.com/Jascen/ultima-memento/releases/tag/2.4.1). They exclude `Data`, game assets, compiled server files and runtime downloads. Imports preserve the installed server and `Data`, stage the replacement save folders, and back up the current save data before activating it. Failed or unsafe client imports leave the existing client intact. Updates preserve existing configuration; changes to upstream settings may need review against your retained `Info` files.

## Build

.NET SDK 10, JDK 17, Gradle 8.11.1, Android SDK 35/build tools 35.0.0:

```sh
python3 -m unittest discover -s tests -v
bash scripts/check-input.sh
bash scripts/check-client-readiness.sh
python3 scripts/prepare-assets.py
bash scripts/build-diagnostics.sh
# On an ARM64 Docker build host, rebuild the two changed native endpoints:
bash scripts/build-audio.sh
bash scripts/build-presentation.sh
python3 scripts/package-bridges.py
gradle --no-daemon :app:assembleDebug :app:lintDebug
```

The APK bundles verified ARM64 PRoot, display, audio, VirGL and Turnip components plus DXVK 2.7.1 D3D11/DXGI for x64 and x86. The server runtime currently reuses TRASC's Debian compiler rootfs and installs Mono into this app's separate copy; the client runtime is built separately from pinned Wine ARM64EC and FEX sources in `client-runtime/Dockerfile`. It contains no Box64 or x86 Linux libraries. The APK retains the existing in-app display, controller and audio transports. Runtime downloads validate their manifests and checksums. Offline archive imports are available for both rootfs downloads.

The internal Java/JNI namespace is retained for compatibility with the reused native display library; the current Android application ID is **`io.github.russianranger.uomemento.recovery`**. Realm control binds `127.0.0.1:18785`, game service `127.0.0.1:2593`; client X11 uses `:8` with a random cookie and local Unix sockets. No RFB TCP listener is exposed.

See [component provenance](docs/COMPONENTS.md) and [release notes](docs/RELEASE-NOTES.md).
