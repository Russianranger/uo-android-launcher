# UO Memento 0.1.9 Recovery — Fix client runtime deployment

Install over UO Memento Recovery without clearing app data. No realm rebuild, client reimport, .NET preparation or runtime download is required.

## Confirmed failure and fix

The 0.1.8 support bundle records `ModuleNotFoundError: No module named 'client_health'` while importing `/opt/uo-client/uo_client_runner.py`. The supervisor exited with code 1 before display setup, Wine or TazUO could start. Both experimental settings were off. This is a launcher deployment bug, separate from the earlier in-game freeze.

`client_health.py` was present in the APK but omitted from Android's hardcoded copy list. Add it to a shared `ClientRuntimeAssets` list used by Android startup and a new packaged-APK test. Every launch copies these assets, so upgrading repairs the existing installation automatically.

## Validation

Reproduced the exact 0.1.8 missing-module failure locally from its deployed Python file list. The new release gate extracts the production deployment list from the built APK and imports the supervisor with isolated Python (`-I -B`) outside the checkout. It verifies that every listed asset exists, deletes only the deployed `client_health.py` to reproduce the reported failure, then restores it and verifies that imports recover. Source-tree imports cannot mask a missing deployed dependency.

Android build/lint, existing Python/Java/UI/Wine checks, real server compilation and Recovery signing continuity remain release gates. The asset check verifies deployment and Python imports, not Android/ARM64 gameplay.

## Update and test

1. Save/stop the server and stop the client. Install the 0.1.9 APK over Recovery; keep app data.
2. Start the existing server. Keep Memory compatibility OFF and Detailed client diagnostics OFF for the diagnostic comparison. Retain Turnip/Vulkan, Native Surface, 60 FPS and 1280×720.
3. Launch TazUO. The 1098×720 world view with 182 pixels of gump space remains configured. If a later freeze occurs, wait about 20 seconds, return to the launcher and export support logs.

The proven missing-module startup failure is fixed. The earlier client freeze and long-session stability remain under investigation. This release does not change the Wine/Box64 stack or implement the Bannerhub FEX/ARM64X reference configuration.
