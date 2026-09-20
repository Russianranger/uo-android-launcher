# Render-list crash after the 0.1.11 repaint mitigation

Status: unresolved device crash. This investigation changes test coverage, not the shipped client or runtime. Do not publish a new APK as a crash fix based on this test alone.

## New device evidence

Support bundle: `logs-1188835873808204630.zip`, SHA-256 `0bde37323ab677364b965edc44ad5972abfc9b449c99c61df846a2ad63ca7624`.

- AYN Thor, launcher 0.1.11. Launch attempt starts at 2026-09-20 22:28:15 UTC; client process runtime is 594.82 seconds.
- `client-compatibility.json` records `FNA_WIN32_IGNORE_WM_PAINT=1` and `window_repaint_policy=game_loop_only` in the generated launch environment. It does not inspect the native filter ultimately installed inside TazUO.
- SDL 3.4.16 is active with verified hash `1f98969319302a100931f4385e5918a0bd53ab07773040682d22e7edb54858c0`; FNA3D hash remains `93ca16fb415438830bd1591ac25fabb92a2b532cb629b215c8bd7d73ca806eb8`.
- At 22:38:25 the client reports the same `InvalidOperationException: InvalidOperation_EnumFailedVersion` in `GameScene.DrawRenderList`, line 1328, on `TUO_MAIN_THREAD`. The stack continues through DrawWorld, GameController.Draw and FNA Game.Tick. Exit code 82 follows.
- Memory compatibility and managed diagnostics are off. Current Wine output contains no native access violation, Box64 SIGSEGV or Vulkan assertion. The server remains running and records a successful save. Display EOF follows client teardown.

Conclusion: 0.1.11 did not resolve this device failure. Do not attribute it to another GPU fault or to out-of-memory termination from this bundle.

## Gap in the previous reproduction

The prior test constructed a bare FNA Game. Its Windows paint filter can reenter Draw and invalidate an active list enumerator. The supported hint prevents that behavior in the bare FNA fixture.

However, the [TazUO 5.2 reference GameController](https://github.com/PlayTazUO/TazUO/blob/73768f6653d39788b00f5bce5b2a063dc76452aa/src/ClassicUO.Client/GameController.cs) installs its own `HandleSdlEvent` using `SDL_SetEventFilter` during Initialize, before base.Initialize. It replaces the FNA filter rather than forwarding to it. That handler has no window-exposure case and returns true for those events. The FNA-only negative control therefore did not reproduce the client's actual filter configuration.

The expanded Wine gate preserves the old FNA negative/positive controls and adds this replacement-filter behavior with the hint both off and on. Both replacement-filter cases must receive all 64 injected exposure events and finish at least 160 draws with no nested draw. This verifies the missing distinction, not a new device-crash fix; the fixture does not implement TazUO's unrelated input handlers or world logic.

## Needed next evidence

Obtain the exact `TazUO.dll` and `FNA.dll` from the imported client's `Ultima-Memento/Client/TazUO-Launcher/TazUO` directory. Include matching `TazUO.pdb` and `FNA.pdb` if available. Program files from the original imported folder/ZIP are sufficient if they have not since been updated. No new gameplay run is needed.

The bundle reports package/version names but includes neither these assemblies nor their hashes. A 5.2 version label alone cannot establish an exact source build. Inspect assembly identity, method IL, source checksums and filter/draw implementation before generating a binary-specific patch or substituting an entire client build. The source audit locates render-list writes in FillGameObjectList and its sorting helpers; the crash stack identifies the failed reader, not which operation changed its version.

Avoid replacing foreach with an unchecked live-list loop or swallowing the exception: either could conceal an unresolved mutation or execution fault. Do not change more Box64, GC, JIT or renderer settings without a discriminating test.

Keep this investigation branch separate from release publication. Before a future merge that publishes an APK, update the release version/notes; the existing main workflow targets v0.1.11 and must not overwrite that release with an unrelated investigation build.
