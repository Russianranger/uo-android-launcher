# Thor 0.2.16 optional-SDL failure

## Outcome

Withdraw the recommendation to enable **Use SDL 3.4.16 (optional)** on Thor. The attempted comparison ended with two WebView renderer exits and an Android low-memory termination of the launcher. Keep the original SDL 3.2.27 configuration. The export does not establish an SDL memory leak, a native Vulkan crash, or which component caused device memory pressure.

Input: `logs-5661785330657922712.zip`, SHA-256 `df1c352f60be89c2971c7c2a5987449e005fd843ecd426df646ab34434aeb1f2`. App 0.2.16; failed launch begins 2026-10-03 12:42:31 UTC (07:42:31 America/Chicago). This follows the [successful original-library trace](THOR-0.2.16-ANALYSIS.md). The APK remains the published diagnostic build at `78b6d11498e6fa624b5e2024b6b9f16591194ea5`; these notes do not rebuild or change it.

## Confirmed configuration and timeline

`client-state.json` records `sdl_graphics.requested=true`, `action=updated_known_tazuo_5.2_pair`, and active SDL hash `1f98969319302a100931f4385e5918a0bd53ab07773040682d22e7edb54858c0` (3.4.16), replacing the known original hash `f53fbe656b784365dc1db0de61958a51a41b5923ab9623bf2f7af4eca9649c09`. Cold timing, the retained native observer, atlas batching, Smooth world loading, Turnip and Native Surface remain enabled. Client/FEX PID is 31842; Android launcher PID is 30788. They are different processes.

| UTC | Observation |
| --- | --- |
| 12:42:31 | Client launch begins with the optional library update. |
| 12:43:27.782612 | `app.log`: WebView renderer exits; MainActivity recreates its UI. |
| 12:43:28.508318 | A second WebView renderer exit is logged. |
| 12:43:28.553 | Android exit record: launcher PID 30788, reason 3, status 0. |
| 12:43:37.874 | Replacement launcher PID 2534 exits with reason 10. |

[Android ApplicationExitInfo](https://developer.android.com/reference/android/app/ApplicationExitInfo#REASON_LOW_MEMORY) defines reason 3 as a system low-memory kill, meaning the device was under memory pressure. Reason 10 is a user-requested termination, such as force-stop or removal from Recents. The later user-requested termination does not replace the earlier low-memory diagnosis.

The Wine log ends around the launcher termination, without a current unhandled exception/native fault stack or Vulkan device-lost result. The audio transport then reports a disconnected device. This supports loss of Android-side services; it does not independently identify the initiating component. Persisted `phase=client_running` is stale after abrupt termination, not proof that the client survived. No recovery launch is represented in this ZIP.

## Memory evidence and limits

| Observed process memory | Failed optional-SDL run | Successful original-SDL run |
| --- | ---: | ---: |
| Highest sampled client/FEX RSS | 834.43 MiB, final sample at 12:43:28 | 885.64 MiB |
| Original-library RSS at comparable startup elapsed 50–58 s | — | Approximately 856–868 MiB |

These are process RSS samples from `/proc`, not total device or GPU memory. The failed run does not show uniquely higher client RSS. Both runs reserve tens of GiB of virtual address space; virtual reservations must not be presented as physical RAM consumption. Health records report `children_unavailable=true` and do not account for the launcher, WebView, server, other Wine processes, driver/GPU allocations or other apps. The Android exit record's launcher PSS/RSS is the last system sample, not memory measured immediately before death.

`MainActivity.onRenderProcessGone` currently discards `RenderProcessGoneDetail.didCrash()` and `rendererPriorityAtExit()`. The two WebView exits therefore cannot be classified from this log as renderer crashes versus system kills. Immediate UI recreation is observed, but its causal contribution to the later launcher kill is unmeasured. Future termination diagnostics should record those details and device-wide memory availability/low-memory state before attributing pressure to a specific library.

This run contains login/first world loading, including long Update and Draw records, but no current traversal phase markers. Earlier markers in the archive belong to the successful 11:16 launch. Do not use this failed session to claim an SDL performance improvement or regression for the outdoor/interior route.

## Coverage and recovery

| Runtime fixture | Original SDL 3.2.27 | Updated SDL 3.4.16 |
| --- | --- | --- |
| Plain x64 Wine, FNA3D Vulkan | Executed | Executed |
| x64 Wine plus native Vulkan observer | Executed | Not executed |
| Retained ARM64 Wine/FEX, direct, observer off/on | Executed | Not executed |
| Retained ARM64 Wine/FEX, both PRoot modes, observer off/on | Executed | Not executed |

Sources: `scripts/check-graphics-wine.sh`, `scripts/check-fex-runtime.sh`, `tests/run-fex-proot.sh`. SDK headers/import libraries do not determine the executed SDL DLL. Host tests do not establish Android/Adreno/Turnip gameplay stability.

1. In **Client → Client options**, turn **Use SDL 3.4.16 (optional)** OFF.
2. Fully close the existing client and launch a fresh client process. Existing `backend/client_graphics.py` restores the original SDL from the checksum-verified `SDL3.dll.before-memento-3.4.16` backup before Wine starts. No normal rollback requires an APK reinstall, runtime reset, client reimport or app-data clearing.
3. Confirm the game runs again. A subsequent Journal export should record `sdl_graphics.action=restored_original` on the first restoring launch (or `unchanged_original` on later launches), `active_version=3.2.27 (TazUO 5.2)` and the original hash above.
4. If it still terminates, export the complete Journal ZIP before another launch. Then disable **Cold-load timing (Thor test)** for a baseline recovery attempt. That option separately restores the existing atlas FNA and removes the extra observers, retaining batching and the 0.2.13 summaries.

The normal update creates the verified original backup before replacing SDL. Unknown client libraries and altered/missing backups are not silently overwritten. If the original backup is missing, the current implementation reports `action=unchanged_no_original_backup` and leaves 3.4.16 active; turning the option off alone has not recovered that case. If this action or a changed-backup error appears, retain that evidence and restore the original SDL from the matching client package rather than deleting backups or resetting the runtime.

All five existing `test_client_graphics.py` tests pass, including update/repeat/restore/re-enable integrity, interrupted writes, unknown libraries and altered-backup protection. This verifies the implementation's rollback path, not recovery on this physical device. Device recovery remains to be confirmed.

Continue the measured graphics investigation on original SDL after recovery: the prior successful trace locates the dominant first-interior stall in native fence waiting and queue submissions. Do not change synchronization, stack another resource optimization or change runtime defaults based on this failed comparison.
