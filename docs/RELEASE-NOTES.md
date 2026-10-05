# UO Memento Mobile 0.2.22 — Official release

0.2.22 fixes runtime extraction on devices that deny hard-link creation, adds upstream/fork/custom Realm source selection and offline server compilation, and adds complete session backup and restore in Journal. The accepted Wine/FEX archive, application/signing identity, startup fixes, native rendering, audio, controls and tested map-loading optimization are retained.

## Runtime extraction

The client archive's 45 hard links and the Realm archive's six hard links now extract as independent ordinary files. Executable files use `0755`, other regular files use `0644`, and guest symbolic links are preserved. Copies count toward expanded-size and free-space limits. Both online and offline extraction use this behavior; the archives are unchanged and existing working runtimes do not need reinstalling.

Both exact runtime archives passed Java host extraction with simulated Android `EACCES` denial: 45/six independent byte-identical copies, 988/1,345 preserved guest symbolic links, and verified file sizes and modes. A physical Android 16 setup test remains pending.

## Realm setup and updates

Step 2 defaults to **Upstream**, `Jascen/ultima-memento`. **My source**, `Russianranger/ultima-memento`, and a custom public HTTPS Git URL remain available with a branch/tag/commit field. Preferences persist, and staged provenance and the installed build revision are reported separately. Choosing a source or updating the APK does not replace the installed server; **Pull & compile** performs the explicit update.

**Offline server setup → Import server source ZIP** validates and stages supported Memento source. **Compile staged server source** is the separate deployment step, using prepared Mono and imported client map files without a Git download. Online and offline updates compile candidates before activation and preserve the existing world and settings. Have runtimes, compiler, client and required .NET prepared before disconnecting.

## Complete session backup and restore

Journal's **Back up & export complete session** saves/closes the session and archives the installed Realm runtime/compiler, staged source and server build, world `Info`/`Saves`/`Backups`/`Data` and settings, imported client/assets, FEX/Wine runtime, Wine prefix, .NET, controller mappings and launcher/source choices. App exports, logs, temporary/staging state and downloadable Git caches are excluded. A persistent catalog supports later export and preview/restore, including retry after cancelling the external picker.

Preview works with runtimes closed and on a fresh setup. Archive contents are validated before closing the current session. Confirming restore saves/closes it and must create a complete local snapshot before replacing an existing installed Realm. Restore replaces the complete backed installation; components absent from the backup are removed. A fresh setup has no installed Realm to snapshot. Existing app export ZIPs remain available, including the automatic snapshot for later export.

Restoration stages and verifies the replacement before activation, restores portable launcher/controller preferences, and reloads server settings. A durable transaction record supports recovery after interruption. Sufficient additional app storage is needed for the imported ZIP, unpacked replacement and automatic backup alongside the existing installation, with a 128 MiB reserve. **Saves** remains the separate `Info`/`Saves`/`Backups` transfer flow.

## Existing map fix and device checks

The October 5 Thor comparison for 0.2.20 recorded three original file-length getters instead of 2,115 for completed map-1 chunks in emitted windows, with a cold-interior main-thread chunk peak of 5.795 ms versus the prior 6,578.185 ms. Marked outdoor/interior phases had no frame gaps of 250 ms or longer. The chunk-scoped cache, live first accesses, per-chunk refresh, reader replacement/disposal behavior and retained diagnostic path carry forward unchanged.

A separate initial-world frame lasted about 5.2 seconds, including 4.65 seconds in packet-55/network handling. This setup/backup update does not add a new client-performance optimization or claim to remove that remaining startup pause.

Install **UO-Memento-Mobile-0.2.22.apk** over the current app while keeping app data. Leave **Faster map loading** and **Smooth world loading** ON, **Cold-load timing (Thor test)** OFF for normal play, optional SDL OFF on Thor, and retain working graphics/audio/controller choices. Check a fresh startup, cold outdoor area and first interior visit, then warm revisits, save/close and persistence on relaunch. Check source/ref switching, offline staging/compilation, session export retry, preview/cancel and restore of a disposable session.

The existing client delta, host/Wine/FEX/both PRoot and packaged-APK release gates remain required, alongside extraction, Realm source, session archive/transaction and mobile UI checks. The 0.2.22 physical device pass remains pending.

See the [0.2.22 instructions](https://github.com/Russianranger/uo-android-launcher/releases/download/v0.2.22/UO-Memento-Mobile-0.2.22-Instructions.txt), [setup/session guide](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/SETUP-AND-SESSION-0.2.22.md), [physical comparison](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/THOR-0.2.20-ANALYSIS.md), and [map-cache qualification](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/OPTIMIZATION-0.2.20.md). The [release and checksums](https://github.com/Russianranger/uo-android-launcher/releases/tag/v0.2.22) and download URLs are populated when 0.2.22 is published.
