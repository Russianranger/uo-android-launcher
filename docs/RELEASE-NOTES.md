# UO Memento Recovery 0.2.9

Save-data transfers now include only **Info, Saves and Backups**. A **Play Memento** button handles the normal runtime → server → client startup sequence, and client settings are grouped in a collapsed menu.

## Install and use

1. Stop the client and save/stop the realm. Install **UO-Memento-0.2.9-Recovery.apk** over UO Memento Recovery, keeping app data. Existing runtimes, imported client, controller mappings and launch settings are retained.
2. Tap **Play Memento**. The launcher opens the installed realm runtime, checks prerequisites, starts the server if needed, waits for it to accept connections, then launches TazUO and opens its display. Missing prerequisites are reported with the relevant setup section opened.
3. **Start server** opens the installed realm runtime automatically when you only want the server. Setup/download and maintenance controls remain available in their expandable sections.
4. Open **Client options** for graphics, resolution, display mode, FPS, audio, loading, controller and diagnostic settings. Restart the client after changing launch settings.
5. In **Saves**, save and stop the server before creating or importing save data. Export the resulting ZIP outside the app before updating server files or uninstalling.

## Save-data compatibility

- New ZIPs contain only the top-level `Info/`, `Saves/` and `Backups/` folders. Empty folders are retained. `Data`, source, compiled server binaries, game assets, runtimes and a separate manifest are excluded.
- Import accepts these ZIPs, plain save-folder ZIPs (also with one containing folder), and older launcher world archives. Older archives' `Data` contents are ignored.
- Restore keeps the installed server and `Data` files, including asset links. It backs up the current save data, stages the replacement, and only then activates it. Invalid archives leave the existing world intact.
- The scope follows the [upstream Memento upgrade procedure](https://github.com/Jascen/ultima-memento/releases/tag/2.4.1), which lists `Info`, `Saves` and optional `Backups`.

## Startup behavior

- Normal startup is serialized so repeated taps and conflicting setup/import actions cannot start overlapping launch sequences.
- Progress distinguishes runtime preparation, server startup and client startup. Client launch waits for server readiness, rather than just the existence of a server process.
- A failed startup reports the failed step; it does not force-kill a world that may need saving. Return to a running client remains available.
- The existing FEX/Wine runtime, graphics and audio defaults, client patches and viewport behavior are retained. This update does not change their performance tuning.

## Device checks

After installation, test **Play Memento** with the realm runtime closed, then with the server already online. Confirm it reaches TazUO without manually opening the runtime. Expand **Client options**, change an option, and reopen the app to check persistence. Restore an exported save-data ZIP with the server stopped and verify your character and settings after restarting. Inspect the exported ZIP to confirm that only `Info`, `Saves` and `Backups` are present.

Automated archive, launcher sequence and browser checks exercise failure handling and settings persistence. Android build/lint, stable Recovery signing, server compilation and the retained runtime/client checks run in CI. A live Thor session is still required to verify the complete device flow.
