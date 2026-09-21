# World update scheduling and stall observations

The 0.2.6 device session (2026-09-21 17:06–17:10 UTC) used the music cache and loaded assets in 6,976 ms, versus 10,071 ms in the preceding session. It recorded 38 audio delivery gaps above 40 ms (22 above 80 ms), up to 904.649 ms. All 23,141 writes were accepted fully; the slowest write was 0.127 ms. A display sample around 17:07:56 was 2.35 seconds after the last changed frame. These observations suggest upstream delivery stalls but do not identify one root cause or label a particular interior transition.

## Scope and source

- Scheduling is adapted from [TazUO 0da7f149 / #960](https://github.com/PlayTazUO/TazUO/commit/0da7f1493d9f793175ba19affae22068ce2688db). Only the network time/packet budget is backported; entity update semantics and main-thread action-queue scheduling are retained.
- Buffer reset is adapted from [TazUO ce59683 / #892](https://github.com/PlayTazUO/TazUO/commit/ce59683cc6bb994701e69f74af53a3ab1df98930). Both parser buffers are cleared under their original locks after replacement of login/relay sockets. Retry policy is retained.
- The input assembly is the user's verified TazUO 5.2.0 build, SHA-256 `b04066be1b1b475ca00e6982a980e2dd11b93abede00c79c68bde566bdcf947e`, from source `0fc274bf83c6ba84f37ec69a6bec7570743c1777`.

The original outer limit counted 25 received messages, not individual packets. The private parser drained each message in full. The backport shares a 5 ms/1,000-packet budget across the outer loop and inner parser. It checks between complete packets, counts consumed packets even if a plugin filters them, and retains bytes in the same original CircularBuffer. Each update first parses retained data with an empty incoming span, which also services plugin data without a fresh network message. Decoder, handlers, packet ordering and original locks remain intact. A finally block ends the scheduling scope if a handler throws; original exceptions propagate. Nested scopes share the outer deadline.

`diagnostics/frame-patcher` generates both plain and render-trace-composed outputs offline. `client_frame_budget.py` installs only checksum-verified deltas and preloads `Memento.FrameBudget.dll` from app assets. It manages four known states directly, avoiding rewrites on an unchanged launch. It validates both original backups when both features are active. Unknown updated clients are never downgraded. Music caching operates on a separate Assets assembly.

## Observations

`FRAME_BUDGET` records in `client-wine.log` aggregate five-second windows on the game thread: packet count, budget yields, largest parser backlog, update/audio-update gaps, stage calls, total/max stage durations and GC collection-count deltas. The stages are the game update, network processing, GameScene Load/Update/FillGameObjectList and AudioManager.Update. GC counts are not pause durations. Nested stage totals overlap and must not be added as if mutually exclusive. Loading can happen outside an update; its duration is retained for the next summary. These hooks add no texture/graphics calls, background task or first-chance exception handler.

`client-audio.log` retains accepted-write gaps and adds maximum command wait, PCM-read time and reply time, plus command waits over 40 ms. Paused streams are excluded. Clock measurements include worker descheduling: a long read does not prove the producer alone was late. Compare timestamps and the managed audio-update gap before choosing any buffer or scheduling change.

## Verification

Run `bash scripts/check-frame-budget.sh --host-only` for the exact original/patched/combined managed probes, or omit the flag for the Windows/Wine gate. Full CI checks startup-hook loading with the helper absent beside the test executable, verifies the shipped deltas against regenerated outputs, exercises repeat application and restores the exact original. The probe replaces only network input, handlers and world setup; it executes the real client queue, packet parser, network loop, exception cleanup and buffer reset. No game server or display is started by this probe.

Structural comparison against each input preserves assembly identity, architecture, all prior dependencies, constants, fields and embedded resources. Exactly nine original methods change, with 19,779 preserved; one parser reset method and one helper assembly reference are added. Pure Python transition tests cover all four combinations, legacy traced imports, unknown upgrades, changed FNA, missing/corrupt backups, invalid deltas and interrupted replacement.

The stable Wine/FEX binaries, PRoot acceleration, controller engine, 30 FPS default, 40 ms audio buffer, 1098×720 world and 1280×720 canvas are unchanged. The backport cannot preempt one long handler, scene load, shader compilation or plugin callback. Gameplay testing is required to determine whether the observed hitches improve.
