# UO Memento 0.1.8 Recovery — Isolate the client freeze

Install over UO Memento Recovery without clearing app data. No client reimport, realm rebuild or runtime download is required.

## What the logs establish

The reported 0.1.7 attempt passed Wine setup, connected to the server and reached `GameScene` at 19:23:40 UTC. Managed samples then stopped, the game stopped producing audio, and its final Wine output was texture creation at 19:23:41. Android display/input stayed available until the user stopped the client at 19:27:43. There is no current crash exception. An older imported crash file is not evidence for this attempt. The last FPS sample is cached and cannot establish continued rendering.

## Changes

- Make the launcher's injected managed diagnostic hook opt-in and **off by default**. Normal launches no longer install its assembly/exception callbacks, FNA logger delegate or managed timer. This isolates a possible source of interference; it is not a claim that the hook caused the freeze.
- Retain Wine/Box64 native error output and support log export.
- Add a bounded external process/thread activity log. It samples every ten seconds, caps process/thread counts, rotates at 1 MiB, and uses the existing history limit. It records CPU ticks, resident pages, thread states and available wait channels without reading process memory, command lines or environments. Restricted `/proc` access does not stop the game. Activity is evidence for investigation, not proof of responsiveness.
- Preserve the working Native Surface readiness gate, relative controls, audio transport, existing runtime settings and the requested **1098×720 world inside 1280×720**.
- Record the user's Bannerhub reference: FEX-20251025, Wine 10.6 ARM64X, Turnip 25.0 R1 and selected DXVK 2.3.1 async. That stack is not bundled in this update.

## Test

1. Save and close the realm runtime and stop the client. Install the update over Recovery; keep its data.
2. Start the existing server. Keep Turnip/Vulkan, 1280×720, Native Surface, 60 FPS, and the world/gump layout. Leave **Memory compatibility OFF** and **Detailed client diagnostics OFF**.
3. Launch and attempt world entry. If it freezes, leave it open for about 20 seconds, return to the launcher and export support logs. If it works, continue normal play and export after the session.

## Validation and limits

Checks cover default/explicit diagnostic launch environments, removal of inherited hooks, setup/desktop isolation, UI persistence, a real stopped Linux process sampled externally, unavailable process data, bounded logging and PID reuse. The Windows .NET/Wine fixture executes with the hook absent, then explicitly enables the existing managed diagnostic tests. Android build/lint, signing continuity, server compilation and the existing regression gates remain required.

CI runs on x86-64 Linux and cannot establish ARM64 Box64 gameplay stability on the Thor. This is a diagnostic isolation release; the freeze and earlier long-session crashes remain unresolved until device evidence identifies the cause.
