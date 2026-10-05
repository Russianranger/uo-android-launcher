# UO Memento Mobile 0.2.22: setup and complete session backups

0.2.22 makes runtime extraction work without Android hard-link creation, adds a choice of Realm server source and offline source compilation, and adds complete session backup and restore to Journal. It retains the accepted Wine/FEX archive and the map-loading fix validated on Thor in 0.2.20 and released in 0.2.21.

Release assets: [APK](https://github.com/Russianranger/uo-android-launcher/releases/download/v0.2.22/UO-Memento-Mobile-0.2.22.apk), [short instructions](https://github.com/Russianranger/uo-android-launcher/releases/download/v0.2.22/UO-Memento-Mobile-0.2.22-Instructions.txt), and [release/checksums](https://github.com/Russianranger/uo-android-launcher/releases/tag/v0.2.22). These URLs are populated when 0.2.22 is published.

## Update an existing installation

Save and close the session, then install the APK over the current app while keeping app data. Existing installations retain their world, client, settings and working runtimes. They do not need a runtime reinstall or client reimport. Changing the server source happens only when you explicitly pull and compile; installing the APK does not replace your current server with upstream.

Keep **Faster map loading** and **Smooth world loading** ON, **Cold-load timing (Thor test)** OFF for normal play, and optional SDL OFF on Thor. Keep your working graphics, Native Surface, audio, FPS, resolution and controller settings. The [physical comparison](THOR-0.2.20-ANALYSIS.md) and [cache lifetime](OPTIMIZATION-0.2.20.md) remain applicable; this update adds no new client-performance optimization.

## Realm source and offline compilation

Open **Realm → Realm setup & updates**. Step 1 installs or imports the Realm runtime; open it and prepare the Mono compiler before compiling a server.

Step 2, **Forge the server**, provides these choices:

| Source | Repository |
|---|---|
| Upstream, the default | `https://github.com/Jascen/ultima-memento.git` |
| My source | `https://github.com/Russianranger/ultima-memento.git` |
| Custom Git source | A public HTTPS Git repository entered by the user |

Enter a branch, tag or commit in the ref field and choose **Pull & compile**. Custom HTTPS repositories can use other Git hosts and subgroup paths, provided their source has the supported Memento layout. The URL must omit embedded credentials, query strings and fragments. The app validates the repository/ref and the expected local connection patches before deploying it.

The form choice is saved. The staged source provenance and compiled revision are reported separately, so choosing another source in the form does not imply it has already been installed. Source updates compile a candidate before replacing the active server and preserve its existing `Info`, `Saves`, `Backups` and `Data` content. Review retained settings if switching between materially different sources.

For offline server setup, expand **Offline server setup** under step 2:

1. Choose **Import server source ZIP**. Use a repository ZIP, a supported wrapped release ZIP, or a flat World ZIP with exactly one complete `World/Source/Tools/compile-world-linux.sh` layout. Import validates and stages source; it does not compile or activate a server.
2. Choose **Compile staged server source**. Mono builds the staged core and scripts before deploying the result. There is no Git download in this step. Prepare Mono and import the complete Memento client first; the client supplies the world map files.

Offline setup also supports importing both runtime archives from their existing setup sections. Have the Realm runtime, prepared Mono compiler, complete client, FEX runtime and any required portable .NET runtime available before disconnecting. Importing a source ZIP alone does not supply these dependencies.

## Journal complete session backup

Choose **Journal → Back up & export complete session**. The app closes the client, saves and stops the server, closes the runtimes, and creates a complete ZIP in app storage before opening Android's export picker. A failed world save acknowledgement stops the operation; the app does not take a live-server snapshot.

The backup includes installed components and their current contents:

- Realm runtime, prepared compiler, deployed server and staged server source.
- World `Info`, `Saves`, server `Backups`, `Data` and configuration.
- Imported client and game assets, client settings, FEX/Wine runtime, Wine prefix and prepared .NET.
- Controller mappings, launcher display/audio/performance preferences and Realm source/ref form values.

It excludes app-created export archives and their catalog records, incoming archives, support logs, transient process state, temporary/staging trees, package caches and Git download caches that can be fetched again. Server `Backups` is world content and remains included. Excluding app exports prevents backups from recursively containing earlier backup ZIPs. WebView's device-specific database is not copied; portable launcher preferences are stored separately.

**Your complete session backups** remains available in Journal with both runtimes closed. It shows creation time, size and completed-export status. If you cancel the destination picker, use that archive's **Export** button to retry without recreating it. Export a copy outside the app before uninstalling; an app-private copy is removed by uninstalling.

## Preview and restore

Use **Import & preview session ZIP**, or **Preview / restore** on a Journal archive. Preview is available with the runtimes closed and on a fresh setup. A save-data ZIP from Saves is a different format and cannot replace a complete session.

Preview reports the recorded components, creation time, file count and compressed/unpacked sizes. The archive's format, paths, links, declared sizes and file hashes are validated before closing the current session. Cancel leaves the installation unchanged and removes only the selected incoming copy; cancelling a catalog preview keeps the existing app archive.

Confirm **Save & replace complete session** only after reviewing the preview. Restore saves and closes the current session, then creates a mandatory local complete backup before replacing an existing installed Realm. If that backup cannot be created, restoration stops. A fresh setup has no installed Realm to snapshot. The automatic archive is listed in Journal for later export.

Restore replaces the installation's runtime and work trees, including their world, client, source and settings. Components absent from the selected backup are removed from the current installation. Existing app export ZIPs remain available and are not nested into the restored session. The app stages and verifies the replacement before activation; a durable transaction record restores coherent trees and launcher preferences after an interrupted activation.

Launcher choices and controller mappings are restored, and the server settings editor reloads imported values. Restored source selection does not start a download. Use **Play Memento** to reopen the restored session after completion.

Allow substantial extra storage: the current installation stays present while the imported ZIP, unpacked replacement and automatic complete backup are created. Their sizes are additional to the current installation; compression savings depend on the contents. The app enforces available-space checks and a 128 MiB reserve. Your external export destination also needs room for the complete ZIP.

## Runtime hard links and qualification

Both accepted runtime archives contain hard links: 45 in the client Wine/FEX archive and six in the Realm runtime. Extraction now materializes each as an independent file copy instead of calling Android `Os.link()`. Executable regular files and hard-link copies use mode `0755`; other regular files use `0644`. Linux guest symbolic links retain their link targets. Expanded hard-link bytes count toward storage and extraction limits.

The runtime archives remain unchanged. The APK extractor handles the compatibility change, including offline runtime imports, so an already working installation can keep its current runtime.

The exact client and Realm archives were exercised through the Java extractor with an Android adapter that rejects hard-link creation with `EACCES`, matching the reported Android 16 failure:

| Archive | Independent, byte-identical hard-link copies | Preserved guest symbolic links |
|---|---:|---:|
| Client Wine/FEX | 45 | 988 |
| Realm runtime | 6 | 1,345 |

Regular-file sizes/modes and hard-link copy modes were verified as well. This is host qualification under simulated Android denial; a physical Android 16 installation test remains pending.

## Focused device checks

On Thor, retain the established graphics/audio/controller settings and map-loading options. Test a fresh startup and world entry, a cold outdoor area, the first interior visit, and warm revisits in the same client process. Check inventory, targeting, audio and controls, then save/close and verify the character and world on the next launch. Enable cold timing only for a diagnostic comparison and export support logs before another launch if a problem occurs.

Also check source switching and ref persistence, custom HTTPS source input, offline ZIP import followed by separate compilation, a complete session export with a cancelled-picker retry, preview/cancel, and restore of a disposable session. Verify the restored world, client, controller mappings and launcher choices, and export the automatic pre-restore snapshot. Use a fresh Android 16 setup to qualify both online and offline runtime extraction on that device.

These device checks complement the automated extraction, source/import/build, session archive/transaction and mobile UI checks. Passing host checks or a build does not establish physical Android 16 compatibility or complete the Thor device pass.
