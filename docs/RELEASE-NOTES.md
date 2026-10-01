# UO Memento Recovery 0.2.10

This update adds backup management, a server settings editor and complete session controls, with a distinct UO-inspired pixel-art scene for Realm, Client, Saves and Journal.

## Backup management

- Existing `memento-world-*.zip` archives are listed independently of runtime jobs, including archives created by 0.2.9. The list works with the realm runtime closed.
- Each app copy shows its creation time, size, purpose when available, and whether an Android export completed. Export completion records that copy operation; the app cannot monitor whether an external file is later moved or deleted.
- **Save & export** closes the client, waits for the server's save/stop acknowledgement, creates a ZIP and opens the destination picker. Cancelling the picker retains the app backup for a later export.
- Preview an app archive or an imported ZIP before confirming restoration. Preview shows included folders, file count, compressed/unpacked sizes and legacy compatibility. Extraction validates data again, including ZIP checksums, before activation.
- Confirming a restore first saves/closes the active session. Current save data is backed up before replacement; restoring an app archive keeps that original archive too.
- Delete a selected app copy or explicitly retain the newest 3, 5 or 10. No automatic retention policy is enabled. Log archives and exported external copies are outside this deletion scope.
- New archives still contain **only Info, Saves and Backups**. Installed `Data`, source, binaries, runtimes and game assets are excluded. The previously supported plain, wrapped and legacy save archives remain supported.

## Server settings

- **Realm → Server settings** reads the installed `Info/Scripts/Settings.cs`. The pinned Memento revision exposes 142 settings in 12 categories, with the existing descriptions, search and category filtering.
- On/off controls, whole/decimal numbers, text and integer lists are supported. The editor validates types, documented limits, choice lists and paired minimum/maximum settings. Only changed values are written; unrelated settings/comments are retained.
- Changes require a stopped server and apply on its next start. The candidate file must compile before atomic replacement. A rejected edit leaves the original settings file intact.
- Discard draft changes or undo the last applied edit. Undo verifies the current revision and restores the previous file, including its original line endings and encoding marker.
- Address/port/autodetection are managed for the launcher's local connection. Custom expressions and values assigned in `Settings.override.cs` remain read-only, with an explanation; custom code is not evaluated or overwritten.

## Session controls and artwork

- **Save & close session** sits beside Play. It stops the client, waits for active realm tasks, then saves and closes the realm runtime. Failed save acknowledgements leave the realm running with an error to inspect.
- **Cancel launch & close** remains accessible while normal Play/server startup controls are busy. Cancellation requests a graceful close and waits for backend tasks; it does not force-kill an unfinished server.
- Launcher and notification shutdown use the same sequence. Duplicate shutdown requests are rejected, and elapsed time accompanies startup/task progress.
- Four original generated pixel-art backgrounds change with the active tab: castle realm, moongate journey, treasure vault and candlelit journal. Dark panel backgrounds keep text readable. See [artwork provenance and prompts](ARTWORK-0.2.10.md).

The existing FEX/Wine runtime, audio delivery, client acceleration, graphics defaults, client patches, controller mappings and viewport tuning are retained.

## Validation and device checks

Archive/settings tests cover failure preservation, unsafe input, unchanged server files, persistent catalogs, retention, stale revisions and exact Undo. Java host checks cover ordered startup/shutdown, failure gates, cancellation and duplicate shutdown. Chromium checks exercise phone/landscape layouts, backgrounds, settings edits, backup previews and session controls. CI also compiles edited settings with the real server/game scripts, builds/lints Android, checks packaged assets and verifies Recovery signing against the original certificate.

Use the [device test instructions](UO-Memento-0.2.10-Instructions.txt) after installing the APK. Device validation of these new controls is separate from the working 0.2.9 game session.
