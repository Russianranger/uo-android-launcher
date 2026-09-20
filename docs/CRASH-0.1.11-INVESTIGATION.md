# Render-list crash after the 0.1.11 repaint mitigation

Status: unresolved device crash. Version 0.1.12 adds opt-in exact-build diagnostics, not a confirmed crash fix.

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

## Exact binaries supplied and inspected

| File | SHA-256 |
|---|---|
| TazUO.dll | `b04066be1b1b475ca00e6982a980e2dd11b93abede00c79c68bde566bdcf947e` |
| TazUO.pdb | `b5608ce330fd38d4b04a6007d168ab0914794f4773d777bea1b23c652084a6d3` |
| FNA.dll | `399c91458ccbd08bcd8094bde39a1091f5edd545fd77a9b4579016e7ac5498c6` |
| FNA.pdb | `b38bc5cf961af2332751ad1768e300469adcd21930af0377a91299c5d564d9ad` |

PE CodeView identities match the supplied portable PDBs. SourceLink identifies TazUO commit `0fc274bf83c6ba84f37ec69a6bec7570743c1777`, not the initially inspected May 29 reference; FNA is the same `fb477d965e2e7c531a7dba3a10295ff1f8d1fb9f` submodule. FNA's assembly version is 25.11.0.0 and it was compiled targeting net8.0. TazUO targets net10.0. This does not imply a runtime mismatch: the supplied self-contained process runs .NET 10.0.8.

The PDB SHA-256 source checksums match the exact-commit files:

- GameController.cs: `d922ea388081868f90c1bef8ea8d69b3543b576295bc29094310084de64aa67c`
- GameScene.cs: `c95096eb44ce8ab6efc728703befb7c15fedf5ca36a6fd2583a1c005fd7339ae`
- GameSceneDrawingSorting.cs: `a5e31c9ed4a854e09be5a3fba48ff08686399dcecd04b3ba49d8b5e3f5612403`

These files do not differ from the earlier reference. The actual IL confirms the replacement SDL filter, the original foreach in DrawRenderList (method token `0x06001a70`), and FillGameObjectList (`0x06001a68`). Render-list fields are private and their direct writes occur in FillGameObjectList and its sorting helpers. The existing crash proves a failing enumerator, but not which operation changed its version or whether runtime execution is responsible.

## Narrow instrumentation for the next observation

Version 0.1.12 offers a separate, opt-in render trace. It modifies only FillGameObjectList entry and adds a catch/finally around the original DrawRenderList. The catch reports scope and boxed-enumerator fields, then rethrows. The finally always removes the active reader. Fill records a stack only if it overlaps an active reader. It adds no per-object callback, first-chance handler, timer or graphics call.

The exact binary's patched SHA-256 is `0dd83f1af66262f51871ab5eecf4e8a1da5798e5de3c4a5eb4b87f4a4dd8e305`. Semantic verification preserves 19,786 other method bodies, 3,096 constants and all embedded resources. The installer applies the delta only to the original hash and matching FNA hash, verifies the output, preserves the original DLL, and supports atomic restoration. Instrumented source offsets are omitted because the original PDB offsets no longer apply.

The next trace can distinguish recorded list mutation from an exception with matching versions and can show overlapping fill calls and their threads. It cannot by itself prove a Box64 bug, capture every possible unsafe memory overwrite, or guarantee that timing is unchanged. Do not interpret the diagnostic release as a stability fix.

Keep existing renderer, memory and JIT/GC choices unchanged while collecting this observation. The 1280×720 display and 1098×720 world option remain intact.
