# 0.1.12 world-entry Vulkan crash

Status: native crash confirmed; origin of the invalid resource handle remains unresolved. The follow-up VirGL comparison also crashed; see [its investigation](CRASH-0.1.12-VIRGL.md) and the 0.1.13 workaround.

## Current attempt

Support bundle `logs-4860498521430267824.zip`, SHA-256 `f241de03e02a1c49cd4b5c8435b8838382bd7465a051a9ad89da83e7d7f4a824`.

The user reports selecting a character and crashing while entering the world.

- Launcher 0.1.12; attempt starts 2026-09-21 00:04:04 UTC, launcher PID 28761.
- Render tracing is requested and active. Installer action is `instrumented_known_client`, patched TazUO SHA-256 `0dd83f1af66262f51871ab5eecf4e8a1da5798e5de3c4a5eb4b87f4a4dd8e305`.
- Current Wine output confirms `RENDER_TRACE_ACTIVE revision=1 boundary_probes_only`. There is no `RENDER_ENUMERATOR_FAILURE` or `RENDER_WRITE_DURING_READ` marker before the native crash.
- Detailed managed diagnostics and memory compatibility are both off.
- SDL 3.4.16 is active, SHA-256 `1f98969319302a100931f4385e5918a0bd53ab07773040682d22e7edb54858c0`; FNA3D remains `93ca16fb415438830bd1591ac25fabb92a2b532cb629b215c8bd7d73ca806eb8`.
- Assets finish loading at 00:05:36, plugins at 00:05:39, audio initializes at 00:05:43, connection at 00:05:52.
- The process then faults in native Turnip and Wine asserts in `vkDestroyImageView`. Recorded client runtime is 100.03 seconds, exit code -9.
- Last external memory sample at 00:05:50 is approximately 749.8 MiB resident. Android exit history contains older app exits, not an OOM explanation for this attempt. The native fault precedes teardown; -9 alone does not establish OOM.
- Server remains running. Display EOF at 00:06:01 follows client teardown.
- The three exported TazUO crash reports are from the previous day. They are not new failures from this traced attempt.

This differs from the preceding stall bundle, where the old managed diagnostic hook was on and render tracing was off. The current user followed the requested settings correctly.

## Native evidence

Current Wine output records:

```text
SIGSEGV @0x7c24410100
bridge: /opt/uo-client/turnip-26.0.0.so+0x117210
accessing 0x78
RDI: 0x0000000038088de0
RSI: 0x0000000000000048
RDX: 0x0000000000000000
Assertion failed: !status && "vkDestroyImageView"
```

The exact bundled Turnip file was extracted from the checksum-pinned runtime bridge archive:

- Driver SHA-256 `51b968eed13c933d114cdc2956135758917e48451129f647ecb5ebbea5a527eb`.
- GNU build ID `648e21fce355e54333b11e504b27dbb49b62f451`.
- Archive SHA-256 `c5d0d6e2680039dcc1e035b2adb93b4569a1da5d8d2f0ec3c4646b2e793673aa`.

ARM64 disassembly at 0x117210 matches the image-view destroy entry: reject a null view, reorder device/allocator/view arguments, then branch to the object-free implementation at 0x1a8070. That implementation passes view+0x20 into sparse-array cleanup; its load at 0x2a0100 reads another 0x10 bytes onward.

The saved x64 argument RSI=0x48 and fault address 0x78 are consistent with an invalid non-null view handle (0x48 + 0x20 + 0x10). This is an inference supported by the registers, exact driver bytes, [Mesa's destroy implementation](https://github.com/chaotic-cx/mesa-mirror/blob/mesa-26.0.0/src/freedreno/vulkan/tu_image.cc), [object cleanup](https://github.com/chaotic-cx/mesa-mirror/blob/mesa-26.0.0/src/vulkan/runtime/vk_object.c), and [Box64's destroy wrapper](https://github.com/ptitSeb/box64/blob/2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a/src/wrapped/wrappedvulkan.c). The bundle does not provide ARM64 register state or a complete native backtrace.

Do not mistake the bridge's named entry offset for a symbolized fault instruction. Do not infer that Turnip created the invalid handle, that SDL double-freed it, or that the trace patch caused it. Resource lifetime, memory corruption and translated execution remain candidates. The native failure prevents this run from resolving the earlier managed-list exception.

## Next controlled device comparison

Use the existing 0.1.12 APK:

1. Stop the client.
2. Change Client -> Display & sound -> Graphics to **VirGL · OpenGL**.
3. Retain Native Surface, 1280x720, 1098x720 world + gump space, render tracing on, detailed diagnostics off, and memory compatibility off.
4. Enter the same character/world and export logs promptly after any failure. Note if graphics are incorrect or performance makes the comparison unusable.

Production code sets both TazUO `force_driver=1` and `FNA3D_FORCE_DRIVER=OpenGL` for VirGL, starts its Android graphics bridge, and omits the Turnip ICD selection. This bypasses SDL GPU's Vulkan image-view lifetime path. The existing SDL compatibility installer applies only to Turnip; on a renderer switch it restores the recognized original SDL if its verified backup exists. Keep the checkbox as it is and record the resulting SDL hash.

This is a diagnostic workaround, not an established stability or performance fix. A repeat of the managed-list exception under OpenGL would provide a useful independent trace. An OpenGL launch/texture failure should be reported as such rather than counted as a successful comparison.

The full 1280x720 canvas and 1098x720 world remain requested. No server reset, client reimport, prefix repair, cache clearing, or new APK is needed for the comparison. This historical comparison has now been completed; do not repeat it as the next recommended test.
