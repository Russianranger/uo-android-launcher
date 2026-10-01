# Changed-frame delivery

## Evidence and scope

The source baseline is 0.2.10 (`f68ea3c62964d3694a4e3cf740e6b4ae2fed5396`). The previous [0.2.5 support analysis](OPTIMIZATION-0.2.5.md) found roughly 0.97 ms readback and 44% duplicate captures. It did not establish a current copy/Surface bottleneck on Thor. This change targets unnecessary transport and conversion for localized changes; no device FPS, temperature or latency improvement is claimed before comparison testing.

Full X11 capture, exact unchanged-frame suppression, current cursor/window caches, MIT-SHM/XGetImage compatibility and 30/60 pacing remain. The existing Wine/FEX runtime, graphics drivers, client patches, game viewport and audio settings remain.

## Delivery and Surface correctness

- The capture helper compares exact pixels against its last delivered image, after compositing the cursor. A single bounding rectangle includes every difference and both old/new cursor positions.
- Region mode can stop comparison early and deliver a full frame when the bounding area reaches 60% of the image. Full mode keeps the original first-difference comparison path. Initial connections and resolution changes always establish a full baseline.
- Original request byte 1 retains the eight-word full-frame protocol. Byte 2 allows region packets (flag bit 2), with a four-word x/y/width/height extension and packed XRGB pixels. Byte 3 queries support without capturing. An old helper closes that probe; Android reconnects using request 1 and stays on Native Surface.
- One direct buffer per Surface reader retains the complete XRGB image, plus 16 bytes of baseline metadata. Scatter socket reads place packed rows directly into that image. No per-frame patch allocation, full RGBA staging buffer or patch-merge copy is introduced.
- Android receives a requested dirty rectangle but can expand it for buffer preservation. The renderer converts and writes the **returned** bounds from the complete retained image. It never assumes a reused Surface buffer already holds the previous frame. Geometry changes request a full redraw.
- Recreated Surfaces get a new socket and baseline. Dimensions, bounds, byte counts, flags and sequence are validated before presentation. Partial/truncated or invalid packets use the existing display failure fallback.

Android documents that the returned area may be expanded and must be redrawn: [ANativeWindow_lock](https://developer.android.com/ndk/reference/group/a-native-window#anativewindow_lock).

## Reading the counters

Compare equivalent sessions with **Client options → Send changed regions** on and off, restarting the client each time. Keep the resolution, graphics, FPS, scene and other options fixed. Allow initial loading to settle; compare stationary animation, cursor/gump interaction, and walking separately.

| Counter | Meaning |
| --- | --- |
| `region_frames` / `full_frames` | Changed packets delivered in each format; excludes unchanged responses. |
| `delivered_pixel_fraction` | Actual pixel bytes divided by full-frame bytes for the same delivered changed frames. 1 means no pixel-byte saving. |
| `surface_redraw_fraction` | Pixels actually converted/copied divided by full image pixels for the same Surface posts. Can exceed the delivered fraction because Android expanded the region. |
| `surface_expanded_frames` | Surface posts whose returned redraw area exceeded the received region. |
| `native_copy_ms_per_frame` | Actual color conversion and write into the returned Surface buffer. |
| `surface_lock_ms_per_frame` / `surface_post_ms_per_frame` | Surface wait/preservation and posting; region mode cannot guarantee these decrease. |
| `request_receive_ms_per_frame` | Request, bridge pacing, queries, capture, comparison and receive combined; not a pure network timer. |
| `capture_ms_per_frame` | Android: capture duration reported for delivered changed frames. Bridge: legacy name for average over all captures, including duplicate captures. |
| `diff_ms_per_capture` / `cache_ms_per_frame` | Helper comparison cost and previous-image update cost. Include these when assessing region overhead. |
| `receive_calls_per_frame` / `wire_bytes_per_second` | Incoming socket work, including headers, for delivered frames. |

`client-frame-bridge.log` records sender measurements. `client-presentation.log` contains the `native_surface` measurements and active mode. The in-game gear view also shows transferred/redrawn percentages with capture/copy/Surface timing. Percentages apply to changed frames in that measurement window, not to the whole gameplay interval. Display posts per second are not game FPS.

If localized changes materially reduce delivered and redraw fractions and copy cost without increasing comparison/Surface wait, keep region mode. If broad animation usually sends full images, or Surface preservation dominates, the switch permits the original transport. Capture remains full-frame, so lower transfer bytes alone do not establish lower capture cost.

## Verification

The native host probe runs the production JNI receiver with real fragmented Unix socket packets and a three-buffer Surface model. It checks localized conversion, color/stride/padding, an expanded redraw after disjoint updates, unchanged frames, resizing, fresh/legacy connections, unsupported flags, oversized bounds, sequence gaps, short payloads and cache capacity.

The real TigerVNC probe checks cursor motion/shape/clipping, small and disjoint UI changes, broad damage, resize, reconnect and unchanged-frame suppression with full/region delivery, MIT-SHM/XGetImage, and 30/60 request limits. Reports preserve sender byte and timing evidence. Android build/lint and packaging checks verify the native library, rebuilt helper and new app label together. Actual Thor performance and visual correctness still require the device checklist.
