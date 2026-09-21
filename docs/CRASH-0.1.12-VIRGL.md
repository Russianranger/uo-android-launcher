# VirGL comparison and translated-return workaround

## Device result

Bundle `logs-1236885992030745596.zip`, SHA-256 `b8f96f895eac441b1ac1effa2cc5b25b4e7e4e542994254f2309a3e474f35ee8`.

Launcher 0.1.12, attempt 2026-09-21 00:24:29 UTC, PID 10553. Settings and live output agree: FNA3D OpenGL, virgl on Adreno 740, OpenGL 2.1 Mesa 22.3.6. The separate graphics bridge reports Qualcomm OpenGL ES 3.2. The original SDL 3.2.27 is active as designed for this renderer. Render tracing is active; memory compatibility and detailed managed diagnostics are off.

The user entered the world, observed white coloring on objects including the normally brown ship, and reported a crash after about three minutes. The screenshot shows the ship's plank detail still present, with a white/grayscale hull and colored sail; surrounding scenery retains color. The screenshot confirms a coloring defect, not a missing-file diagnosis. No GL shader/compiler error in the exported logs establishes its exact cause. The requested 1280x720 canvas and 1098x720 world are applied.

World.CreatePlayer is logged at 00:27:14 and the 1280x720 target at 00:27:27. Process runtime including loading is 422.48 seconds. The final health sample is at 00:31:48. These timestamps are separate from the user's approximate play duration. RSS levels off around 991-999 MiB, without evidence that an OOM kill ended this attempt. Server remains running.

## Actual failure

The current log contains no `RENDER_ENUMERATOR_FAILURE` or `RENDER_WRITE_DURING_READ` despite `RENDER_TRACE_ACTIVE`. It ends with native SIGSEGV followed by fatal `System.AccessViolationException` in GameScene.DrawRenderList and process exit code 2. The render trace catches InvalidOperationException, not fatal access violations; its silence is not evidence that the list state was healthy.

Relevant fault values:

```text
x64 PC: 0x7fa0d5938b
x64 instruction: 48 89 45 b0   (mov [rbp-0x50], rax)
native instruction: f81b01ea
RBP in signal context: 0x7ffe9d8170
faulting write address: 0x7ffe9d8120
RSP: 0x8016c060
protection: 5 (read/execute)
coreclr.dll loaded base: 0x7ffe850000
```

The recorded frame-pointer-relative write targets the CoreCLR module's address range instead of the current stack. The Box64 signal header also prints an older emulated frame-pointer value; use the explicitly reported signal-context registers for the faulting translated instruction. This is consistent with corrupted execution state, but neither the instruction that first corrupted it nor a complete managed/native memory dump is available. Do not claim a specific .NET, Box64, TazUO or trace-patcher defect has been proven.

The former Vulkan image-view destruction fault does not occur in this OpenGL run. A different low-level failure remains in the rendering call chain. VirGL therefore is not an acceptable stability/color workaround on the evidence so far. The previous day's three client crash files are historical, not new managed-list exceptions from this attempt.

## Concrete upstream defect and mitigation

The bundled Box64 is based on commit `2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a`. Its [documented default CALLRET mode is 2](https://github.com/ptitSeb/box64/blob/2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a/docs/USAGE.md#box64_dynarec_callret). The launcher did not override it.

[Upstream PR 4405](https://github.com/ptitSeb/box64/pull/4405), merged September 17, 2026 as `92527ded34d51cdfd9d9f785a7157df51e8c14d8`, fixes pending direct returns into translated blocks that have already been invalidated and recycled. That fix is absent from the bundled commit. Such a defect is relevant to a client which generates and revises executable code. The current bundle does not prove that the defect was triggered in TazUO.

Version 0.1.13 sets `BOX64_DYNAREC_CALLRET=0` for the game process, directing returns through Box64's jump table rather than the affected optimization. This is a narrowly scoped workaround for a known upstream issue, not a backport or a new translator binary. The compatibility report includes its value and policy name. Wine setup, preflight, desktop, services, server, .NET JIT/GC options and existing memory-order settings retain their prior behavior. No additional user toggle is required.

## Verification and limits

- Startup tests check all three renderers, effective game environment, compatibility report and isolation from setup/preflight.
- The x86-64 generated-code fixture modifies its caller while a callback is active, churns 32,768 generated callees, and checks 64 resumed returns for the updated result. Direct x86-64 execution provides its reference result.
- An ARM64 CI job builds the exact bundled Box64 source and runs that x86-64 fixture through it. CALLRET=0 must complete with correct results. Stock mode 2 is also recorded; a stock success means the fixture did not reproduce the invalidation/reuse race, not that the upstream defect is absent.
- This new gate exercises actual ARM64 translation, but is a Linux native-code fixture, not TazUO, Wine or .NET on the Thor. Existing Wine/.NET/FNA/SDL gates still run on x86-64 and do not acquire broader coverage from this job.
- APK packaging, signing continuity and existing server/input/log tests remain release requirements. Physical-device long-session stability remains unverified.

For the next device run use Turnip, Native Surface, 1280x720 with 1098x720 world, SDL Vulkan fixes on, render tracing on, and both detailed diagnostics and memory compatibility off. Keep the installed client and runtime. The game-only return workaround is automatic. Export support logs after a crash or freeze; check `BOX64_DYNAREC_CALLRET=0` in both the compatibility report and Box64 output. Color correctness after returning to Turnip also needs confirmation.
