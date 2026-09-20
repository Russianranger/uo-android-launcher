# UO Memento Recovery 0.1.4 — world viewport and Vulkan compatibility

- Add **1098×720 world + gump space**, enabled by default at 1280×720. The borderless full client canvas remains **1280×720**, leaving **182 pixels on the right** for movable gumps. The world view is fixed at the top left.
- Apply the layout to existing characters and the default profile for new characters. Preserve other settings and saved gumps, and keep a one-time `.json.before-memento-layout` backup. Turning the option off stops applying it; it does not restore previous dimensions automatically.
- Select Vulkan explicitly for Turnip. The imported TazUO **5.2.0** treats the previous auto value as OpenGL; the supplied log confirmed llvmpipe software rendering even though Turnip was selected.
- Add a bounded managed startup hook to capture pathfinding exception details before termination when supported, plus client package versions and asset sizes in support diagnostics.

## Update and test

1. Save and close the realm runtime and stop the client. Install this APK over **UO Memento Recovery** without uninstalling or clearing data. The package ID and certificate remain stable.
2. Start your existing server. No rebuild, reimport or .NET download is needed.
3. Select **Turnip 26 · Vulkan**, **1280×720**, **Native Surface**, **60 FPS**, with **1098×720 world + gump space** checked.
4. Enter the world, move a gump into the right-hand strip, then test walking. If it crashes, report whether it happened while idle or during the first movement, and export support logs.

The supplied crash trace ends in `Pathfinder.CreateItemList` / `CalculateNewZ`, without the exception type. **This release does not claim to fix that movement crash.** The separate scripting-download DNS error was handled by TazUO and is not established as the cause. CI verifies configuration, managed loading and exception capture under Wine 10 / .NET 10.0.8; it cannot verify ARM64 Box64 gameplay or Adreno graphics.

Sources: [TazUO 5.2 startup and renderer selection](https://github.com/PlayTazUO/TazUO/blob/73768f6653d39788b00f5bce5b2a063dc76452aa/src/ClassicUO.Client/Main.cs), [profile schema](https://github.com/PlayTazUO/TazUO/blob/73768f6653d39788b00f5bce5b2a063dc76452aa/src/ClassicUO.Client/Configuration/Profile.cs).

For the original 0.1.0 app, follow the [recovery guide](https://github.com/Russianranger/uo-android-launcher/blob/main/docs/RECOVERY.md) first; its signing key differs.
