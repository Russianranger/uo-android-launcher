# Moving from the original preview to 0.1.1

The original 0.1.0 CI workflow tried to back up its signing key from a directory where the key was not created. Its job reported that no key was saved. The original key could not be recovered, and the new APK's certificate differs. Android cannot install it over 0.1.0.

**0.1.1 uses a separate app identity and is named UO Memento Recovery. It leaves the old app and all its data installed. Do not uninstall the original app or clear its data.**

The recovery app contains the log-export and client-startup fixes. Two ways to move your installation are available:

## Copy the complete installation with a computer

This retains the downloaded runtimes, imported client, .NET, server, world saves and logs. It needs a computer with Python 3, [Android platform-tools](https://developer.android.com/tools/releases/platform-tools), and enough free disk space for a compressed copy of the installation. Neither device nor computer needs root.

1. Install the recovery APK alongside the original. Open it once, then leave it unconfigured.
2. In the **original** app, use **Realm → Save & close realm runtime** and **Client → Stop client**. Wait for both to stop.
3. Enable USB debugging on the Android device, connect it to the computer, and accept the device's debugging prompt. `adb devices` should show the device as authorized.
4. Download `recover-preview.py` from the 0.1.1 release into a new folder on the computer.
5. Export the old logs, even though the old app's export button fails:

   ```sh
   python3 recover-preview.py logs
   ```

   This creates `uo-memento-old-logs.tar.gz`, which can be attached for diagnosis. On Windows, use `python` instead of `python3` if needed.

6. Copy the complete installation:

   ```sh
   python3 recover-preview.py migrate
   ```

   Type `SAVED` when asked, after completing step 2. The tool closes both apps, makes `uo-memento-installation-backup.tar.gz` on the computer, checks the compressed backup, then copies its contents into the fresh recovery app. It never uninstalls or clears the original app, and refuses to overwrite a configured recovery installation or an existing backup file. Keep this backup private: it contains your world, client settings and any saved credentials.

7. Open **UO Memento Recovery**, then **Realm → Open runtime**. Existing installation files should be available. Start the server and retry **Client → Launch TazUO**. The first launch repairs Wine setup once; later launches reuse it.
8. Use **Journal → Export support logs** after the attempt. Keep the original app and computer backup until the recovered world and client are verified.

If the copy fails, the original installation and any completed computer backup remain available. A partly copied recovery installation can be reset separately; never clear the original app. The script's transport and refusal paths have host tests, but actual ADB migration still needs a device test.

## Set up without a computer

In the original app, save and stop the world, then use **Saves → Back up world** and export that world ZIP. Install the recovery APK separately, prepare its runtimes, import your original client folder/ZIP, and pull/compile the server. Restore the world ZIP through the recovery app's Saves tab while its server is stopped. This requires downloading the runtimes and importing the client again.

Only run one app's runtime/server/client at a time: both use the same localhost ports. Closing the old app's screen alone does not stop its foreground server service.

## Future recovery updates

The recovery build uses an explicit keystore path. CI caches that file, can restore a repository owner's `MEMENTO_SIGNING_KEYSTORE_BASE64` secret, and verifies later APKs against the first recovery certificate. If the key becomes unavailable after this release, publication fails instead of silently changing the certificate again. No signing key is committed or attached to the public release.
