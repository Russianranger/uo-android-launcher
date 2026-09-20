# UO Memento Recovery 0.1.3 — client data directory fix

The 0.1.2 test reached TazUO's own startup checks. It could not find the data directory because the launcher wrote `ultimaonline`, while TazUO reads `ultimaonlinedirectory`. The log also showed a blank client version.

- Write the correct Windows data path and repair existing imports automatically at launch.
- Fill blank versions with Memento's documented **7.0.15.1** asset/protocol version. Preserve existing versions, credentials, plugins and other settings, and retain the original settings backup.
- Check for `tiledata.mul`, `cliloc.enu` and `map0.mul` before opening Wine.
- Include the resolved configuration in `client-config.json` support diagnostics, excluding saved credentials.
- Extend the real Wine 10 / Windows .NET 10.0.8 test to reproduce the ignored-key failure and verify the repaired nested Memento data path.

## Update and test

1. In **UO Memento Recovery**, save and close the realm runtime and stop the client.
2. Install the 0.1.3 APK over Recovery. Do not uninstall or clear app data. CI verifies its package ID and signing certificate against the existing Recovery release.
3. Open the realm runtime and start your existing server. No rebuild is needed.
4. Launch TazUO using Turnip, 1280×720, Native Surface and 60 FPS. Settings repair happens automatically; no reimport or .NET preparation is needed.
5. Export support logs after testing. Report whether you reach login, character selection and the world.

The Wine/.NET regression runs on an x86-64 CI host and checks configuration and managed loading. ARM64 Box64, Adreno rendering and TazUO gameplay still need device validation.

Sources: [TazUO settings schema](https://github.com/PlayTazUO/TazUO/blob/3212623f63436be1c0f4e3b308b202b29597c026/src/ClassicUO.Client/Configuration/Settings.cs), [Memento client setup](https://uo-memento.com/setup/desktop-client/#server-information).

For the original **0.1.0** app, follow the [recovery guide](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/RECOVERY.md) first; its signing key differs. The included recovery helper remains available for that older migration.
