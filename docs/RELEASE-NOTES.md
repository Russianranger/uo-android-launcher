# UO Memento Recovery 0.1.2 — managed client loader fix

The 0.1.1 support bundle showed TazUO loading its bundled .NET 10.0.8 and then failing with Wine's `mscoree.dll not found` error for `System.Runtime.dll`. The launcher disabled that DLL globally to suppress Wine's Mono installer. Wine's IL-only DLL loader still needs it when running modern .NET.

- Enable builtin `mscoree` for TazUO, .NET preflight, and the Wine desktop.
- Disable it only in the independent Wine setup environment, keeping the Mono installer suppressed.
- Add a real Wine 10 / self-contained Windows .NET 10.0.8 regression: reproduce the disabled-loader failure, then execute managed code with the fixed launch environment.
- Preserve the existing server, saves, imported client, .NET and graphics/controller settings.

## Update and test

1. In **UO Memento Recovery 0.1.1**, save and close the realm runtime and stop the client.
2. Install the 0.1.2 APK over Recovery. Do not uninstall or clear app data. CI verifies that it uses the same package ID and signing certificate as 0.1.1.
3. Open the realm runtime and start your existing server. No rebuild is needed.
4. Launch TazUO using Turnip, 1280×720, Native Surface and 60 FPS. No reimport or .NET preparation is needed for the reported self-contained client.
5. Export support logs after testing. Tell us whether it reaches login, character selection and the world.

The regression test runs Wine directly on an x86-64 CI host. It verifies the managed-loader fix; it does not prove ARM64 Box64, Adreno graphics or TazUO gameplay compatibility on the Thor.

If still using the original **0.1.0** app, its signing key is different; use the [recovery guide](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/RECOVERY.md) first. The included recovery helper remains available for that older migration.
