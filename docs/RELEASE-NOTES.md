# UO Memento Recovery 0.2.3

Repair Wine registry corruption after a hard reset. The supplied 0.2.2 logs confirm that settings recovery succeeded (`.before-memento-pacing`), but Wine then rejected `system.reg` before starting the client.

## Update

1. Save/stop the realm and stop the client, then install this APK over **UO Memento Recovery**, keeping app data.
2. Launch normally. Registry recovery runs automatically. **No runtime reinstall or client reimport is needed.** The first repair can take longer than an ordinary launch.
3. Keep **Turnip / Native Surface**, **30 FPS · cooler**, audio enabled, tracing/SDL replacement off, and **1280×720 / 1098×720 world + gump space**.

## Changes

- Inspect all three Wine registry hives before trusting the ready marker. Detect empty files, zero-filled bytes, invalid headers, incompatible architecture markers and incomplete tails. These checks detect structural damage; they are not a complete registry grammar validator.
- Stop and wait for this prefix's wineserver before changing hives. Preserve exact damaged files in a unique local recovery directory. Restore valid last-good checkpoints where available; otherwise remove only damaged hives from the active set and let `wineboot -u` regenerate them.
- Retain healthy registry hives and all `drive_c` files. The imported TazUO client, profiles, settings, controller mappings and realm saves are not replaced. Registry customizations present only in a damaged hive may need reapplying if no valid checkpoint exists.
- After Wine setup and a successful command check, stop/wait for wineserver to finish saving, validate the hives, and durably checkpoint them before marking the prefix ready. A failed validation preserves earlier checkpoints and reports the failure.
- Add `client-prefix-health.json` with fixed hive names, sizes, hashes, structural status and recovery actions. Registry contents and values are not exported.

The Wine/FEX binaries, Turnip/graphics DLLs, 0.2.2 audio policy, frame cap and controller behavior are unchanged.

## Cause and validation

In the exact Wine source used by this runtime, failure to load `system.reg` can leave prefix architecture unknown; the registry loader then selects its legacy 32-bit fallback. The subsequent native client reports a 32-bit wineserver. The uploaded runtime identity still identifies the same native ARM64 Wine binary and hashes. See [Wine registry initialization](https://github.com/bylaws/wine/blob/a6844d10622fc1a973ec1f22fc4f78a0fcd6cb29/server/registry.c) and [client architecture check](https://github.com/bylaws/wine/blob/a6844d10622fc1a973ec1f22fc4f78a0fcd6cb29/dlls/ntdll/unix/server.c).

Release checks include damaged/missing hive recovery, invalid checkpoint rejection, exact damaged-byte preservation, path confinement and interrupted-restore retries. The retained ARM64/FEX runtime test under the app's patched PRoot now deliberately damages `system.reg`, requires the reported architecture error, runs the real supervisor repair, verifies a retained user registry value plus prefix/client sentinel files, exercises checkpoint recovery, and then runs .NET 10 JIT/GC and Vulkan probes from the repaired prefix. APK deployment and Recovery signing continuity are also checked.

These checks establish the reproduced startup repair, not Thor gameplay/audio quality or the cause of the device-wide recording freeze. First compare ordinary gameplay without recording and export logs after a normal stop.
