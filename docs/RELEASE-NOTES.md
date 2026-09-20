# UO Memento 0.1.1 — recovery preview

- Fix support ZIP export failing with “Unsafe archive path” on Android directory aliases.
- Include TazUO timestamped crash reports, including clients imported inside subfolders; keep settings, packet logs and chat files excluded.
- Make Android exit-history collection optional so it cannot block the support ZIP.
- Disable Wine's Mono installer. TazUO uses the prepared modern .NET runtime.
- Bundle the missing ARM64 XComposite library as an APK overlay; no client-runtime reinstall or download is needed.
- Repair old/interrupted Wine prefixes once, retaining the imported client and prefix contents.
- Use the device CPU count instead of the runtime's stock 64-CPU override.
- Capture .NET host startup traces, flush process logs promptly, and report immediate client exits.

## Installation: recovery app, not an in-place update

The original 0.1.0 CI workflow did not save its signing key. The key could not be recovered, so Android cannot accept an in-place update. This release uses the separate identity `io.github.russianranger.uomemento.recovery` and the launcher name **UO Memento Recovery**. Keep the old app installed and do not clear its data.

Read [the recovery guide](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/RECOVERY.md). The attached `recover-preview.py` can export old logs or back up/copy the complete installation to the recovery app with ADB. A computer-free path is to export the old world from Saves, prepare the recovery app, and restore that ZIP. Only run one app at a time because their localhost ports overlap.

The fixed exporter passed an Android-alias regression that reproduces the exact reported failure. APK build/lint, controller checks, Python tests and real Memento compilation passed. The ADB helper has host tests, but device migration and the .NET 10 game session still need retesting. The screenshots do not establish the final cause of the client exit.
