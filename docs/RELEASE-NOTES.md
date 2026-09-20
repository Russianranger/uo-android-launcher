# UO Memento 0.1.1 — diagnostics and startup fixes

- Fix support ZIP export failing with “Unsafe archive path” on Android directory aliases.
- Include TazUO timestamped crash reports, including clients imported inside subfolders; keep settings, packet logs and chat files excluded.
- Make Android exit-history collection optional so it cannot block the support ZIP.
- Disable Wine's Mono installer. TazUO uses the prepared modern .NET runtime.
- Bundle the missing ARM64 XComposite library as an APK overlay; no client-runtime reinstall or download is needed.
- Repair old/interrupted Wine prefixes once, retaining the imported client and prefix contents.
- Use the device CPU count instead of the runtime's stock 64-CPU override.
- Capture .NET host startup traces, flush process logs promptly, and report immediate client exits.

Save and stop the server before updating. Install this APK over 0.1.0; do not uninstall or clear app data. The release build verifies that both APKs use the same signing certificate. Existing realm files, saves, client imports and .NET installation remain in place.

After updating, export the existing logs from Journal, then retry Launch TazUO. If it exits again, export a fresh support ZIP. The reported export failure was reproduced and fixed in a host regression test. APK/lint, controller, Python and real server compilation checks run in CI. The .NET 10 game session still needs an on-device retest; these screenshots do not establish the final cause of the client exit.
