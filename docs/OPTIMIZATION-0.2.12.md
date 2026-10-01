# Surface configuration tracking

## Device evidence and scope

The 0.2.11 Thor support session began at 2026-10-01T22:24:30Z. Its 36 Native Surface windows recorded 4,068 posted frames and 4,068 `buffer_reconfigurations`, with `surface_redraw_fraction` equal to 1 in every window. The game image was 1280x720 while the onscreen view was 1920x1080. Region packets reduced total delivered pixel bytes to 0.655955 of equivalent full frames, a 34.4% transport saving. Capture averaged 0.747 ms and conversion averaged 0.490 ms per posted frame; neither average measures isolated stutters.

The receiver's geometry check used `ANativeWindow_getWidth/Height/Format` on every changed frame. A mismatch repeated `ANativeWindow_setBuffersGeometry` and explicitly requested a full redraw, independently of the smaller received region. Android [distinguishes buffer dimensions from physical window dimensions](https://developer.android.com/ndk/reference/group/a-native-window#anativewindow_setbuffersgeometry).

Only geometry tracking is changed. The other proposed frame-pacing and asset/allocation optimization passes are deferred.

## Configuration lifetime and correctness

- Each Java Surface reader already allocates its own direct image buffer and starts a fresh socket/baseline on Surface creation. Readers do not overlap. This existing lifetime also owns configuration state.
- The existing cache's valid flag and image dimensions are committed only after successful configure, lock, conversion and post. They therefore record the last successful buffer configuration for that reader; no additional allocation, native handle or JNI parameter is needed.
- An invalid cache or different incoming full-frame dimensions requires geometry setup and a full redraw. Valid region packets cannot change baseline dimensions. Broad full packets at the current dimensions do not repeat setup.
- Onscreen view scaling does not invalidate game-buffer configuration. A new reader starts with a fresh cache even when its first image has the same resolution as the previous reader.
- Every locked buffer is still checked for width, height, stride, format and valid returned bounds. Conversion always uses Android's actual returned redraw bounds, including a larger area needed for buffer preservation. Failed delivery retains the existing display fallback.
- Unchanged responses still skip locking/posting. Full X11 capture, delivery protocol, region comparison, game/capture pacing and pixel conversion remain otherwise unchanged.

## Regression evidence

The production JNI host probe now keeps onscreen query dimensions independent of configured buffer dimensions. Its view is 1920x1080 while the small fixture image is 16x12. The 0.2.11 receiver fails with `view/buffer size mismatch never repeats geometry setup`; the fixed receiver configures the baseline once and converts only 8 of 192 pixels for a 4x2 region.

Checks cover a changed view size, broad full frames at the same resolution, a true game-resolution change and later frames at that resolution, and a fresh reader/legacy full baseline at an unchanged resolution. The existing three-buffer preservation/expansion, color/stride/padding, fragmented reads, unchanged responses, maximum-height scatter and invalid-packet checks remain.

This establishes receiver behavior in the host model, not a device FPS or stutter reduction. Android can legitimately return larger redraw bounds.

## Device counters

Use the [0.2.12 device checklist](UO-Memento-Mobile-0.2.12-Instructions.txt) with the same resolution, scene and FPS settings as 0.2.11. `buffer_reconfigurations` should be zero in steady-state five-second windows; an initial/recreated reader or changed resolution needs setup again. It counts successful posts for which setup was requested, not allocations inside Android.

Compare `surface_redraw_fraction`, `native_copy_ms_per_frame`, `surface_lock_ms_per_frame` and `surface_post_ms_per_frame` for stationary cursor/gump movement and walking separately. Full redraws remain valid for broad changes or Android expansion. Do not use post count as game FPS, or assume a lower byte fraction proves fewer stalls. Export support logs after the route and lifecycle checks so the same-scene behavior and counters can be compared.
