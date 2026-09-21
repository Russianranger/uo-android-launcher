# UO Memento Recovery 0.1.14

**Diagnostic update; the world-entry freeze is not yet fixed.** The latest 0.1.13 run entered the world with boat coloring restored, then its main thread stopped advancing while the display bridge remained responsive. The Box64 return workaround was active.

Render crash tracing now records the last render-list boundary in a small shared record that the launcher can read while TazUO is stalled. Those samples appear in the existing support ZIP. Failure records no longer depend on walking or formatting an exception stack. The original client exception still propagates.

## Update and test

1. Save and stop the realm, stop the client, then install this APK over **UO Memento Recovery**. Keep app data. No server rebuild, client reimport or runtime download is needed.
2. Keep **Turnip 26 · Vulkan**, **Native Surface**, **1280x720**, and **1098x720 world + gump space** enabled.
3. Keep **SDL Vulkan resource fixes ON**, **Render crash tracing ON**, **Detailed client diagnostics OFF**, and **Memory compatibility OFF**.
4. If the world freezes, wait about **30 seconds**, return to the launcher and choose **Journal → Export support logs before stopping or relaunching the client**. There is no need to wait another ten minutes.

Controller mappings, saves, imported client data, the 182-pixel gump area and runtime settings are preserved. The client DLL uses the same reversible patch as 0.1.12/0.1.13; only its diagnostic helper changes. Turning tracing off and relaunching restores the original DLL.

## Verification limits

The release requires Python, Java, UI, real server compilation, Wine/.NET, FNA/SDL, render instrumentation, pinned Box64 ARM64, APK packaging and signing-continuity checks. New tests cover an independently observed blocked drawing loop, retained failure evidence, separate render threads, exception identity and tracing without stack formatting. Wine tests use the existing Wine 10 and Windows .NET 10.0.8 fixture.

These tests verify diagnostic behavior and packaging. They do not reproduce the Thor freeze or establish gameplay stability. See [the freeze investigation](FREEZE-0.1.13.md).
