# Thor recovery with original SDL and cold timing

## Accepted device result

The user reports stable operation after disabling the optional SDL update while keeping **Cold-load timing (Thor test)** enabled. The export confirms original SDL 3.2.27 and the diagnostic observers are active in the final session, followed by orderly shutdown. Accept this recovery result; continue development on original SDL. The failed updated-library comparison remains withdrawn.

Input: `logs-5085551896468634550.zip`, SHA-256 `13db776b74e7b21fa75b6448daf69af27e6ba7180f160fe63f7f40464cdc7d41`. App 0.2.16, current launch 2026-10-03 13:09:12 UTC (08:09:12 America/Chicago), approximately 81.5 seconds to recorded stop. This is a recovery check, not a new marked outdoor/interior performance comparison.

`client-state.json` records:

- SDL option OFF, `action=unchanged_original`, active version `3.2.27 (TazUO 5.2)`, SHA-256 `f53fbe656b784365dc1db0de61958a51a41b5923ab9623bf2f7af4eca9649c09`.
- Cold timing ON, diagnostic FNA `18c88d506dbe15dcb4bb56f98e4b1756d9f8074ba8ab485ad36e10c087f168b1`, native observer `083c113887a43a912dc42f05e2d919fcafa816d5864f0d1512affc37eb5240b5`. Current Wine output contains both activation records.
- Retained Wine 10.13 ARM64EC/FEX-2510, Turnip, Native Surface, changed-region delivery, 60 FPS, 1280x720 canvas, atlas batching and Smooth world loading (5 ms / 1000 packets).
- `phase=stopped`, rather than the stale running phase in the [failed comparison](THOR-0.2.16-SDL-FAILURE.md).

Original SDL was already present at the start of this successful launch. The exact restoring launch is not retained: there is no literal `restored_original` action in this ZIP. The user notes an initial attempt with SDL accidentally enabled; do not merge that attempt with the final original-library session. A 13:08:42 HTTP end-of-stream launch error predates the successful launch and does not establish the restoration time.

The display server shuts down at 13:10:34; audio logs stream release/close and bridge close at 13:10:34.57–34.93. A UI polling connection reset at 13:10:37 follows shutdown. Android exit history contains no new low-memory/native-crash entry after the earlier 12:43:28 termination. These observations support the reported recovery for this session, not unlimited future stability.

## Additional performance evidence

There are no current test-phase markers. The only retained markers belong to the earlier 11:16:38 launch. Do not assign these new frames to outdoor cold/warm traversal or interior entry/re-entry. The [earlier marked trace](THOR-0.2.16-ANALYSIS.md) remains the evidence for that distinction and the dominant first-interior fence wait.

| Current-launch observation | Measured duration |
| --- | --- |
| First world loading, frame 3573 at 13:10:01.439 | Gap 3,747.224 ms; Update 3,688.429 ms; worst packet 0x55 3,228.631 ms; GameScene.Load 957.645 ms. |
| Initial drawing, frame 3574 at 13:10:04.683 | Gap 3,243.155 ms; Draw 3,158.562 ms; Fill 687.523 ms; EndDraw 25.780 ms. |
| Later unmarked frame 3965 at 13:10:11.354 | Gap 1,331.442 ms; Draw 1,119.866 ms; Update 176.665 ms; packet 0x20 169.805 ms; EndDraw 13.716 ms. |
| Later frame 4343 at 13:10:16.900 | Gap 197.599 ms; EndDraw 182.787 ms; largest FNA swap 49.212 ms; no atlas uploads. |
| Later frame 4757 at 13:10:20.415 | Gap 196.451 ms; EndDraw 179.649 ms; FNA swap 76.178 ms; native fence wait 56.207 ms wall / 0.073 ms CPU; no atlas uploads. |

Stage/packet boundaries are inclusive and must not be added together. Startup/loading frames are separated from the unmarked later observations.

Frame 3965 adds a concrete resource-creation boundary. Immediately after `TextureAtlas.CreateNewTexture2D` logs a **2048x2048 Color** texture, `FNA3D_CreateTexture2D` takes **220.796 ms**, completing at 13:10:10.663862. The native render-thread `vkQueueSubmit` completes at 13:10:10.663, taking **220.583 ms wall / 1.426 ms CPU**, with success. Almost the entire slow texture-creation call is accounted for by that submission. Its blocked interval does not identify GPU execution versus driver/kernel/PRoot behavior. Total observed FNA native time across the frame is 234.922 ms, so most of the 1,119.866 ms Draw remains unseparated. Atlas staging/flush in that frame is 1.181/0.228 ms, GC pause 6.952 ms, and managed current-thread allocation 541,512 bytes.

Background thread 15 also records `FNA3D_Image_Load` 319.730 ms, then `FNA3D_SetTextureData2D` 64.037 ms. That upload and a main-thread `FNA3D_SetVertexBufferData` 61.414 ms finish nearly together at 13:10:06.58756. This is a possible shared-resource serialization clue, not identification of a particular lock or proof that image decoding blocked the main thread.

Nine complete cold windows contain 48 Update-start gaps >=50 ms, 35 >=100 ms and five >=1000 ms. Forty individual long records are emitted and eight are suppressed; window histograms retain those suppressed gaps. There are no suppressed FNA/native slow details or Vulkan slow records. Entire-session shader-module and graphics-pipeline maxima are 0.023 and 4.043 ms respectively. These unmarked all-session counts cannot be compared directly with the earlier marked traversal counts.

## Presentation, memory and next diagnostic scope

Current Android presentation records show 1,061 posts, 701 region frames, 360 full frames, one buffer reconfiguration, no fallback and no Surface-work event >=50 ms. Lock/copy/post maxima are 6.134/3.885/1.539 ms. Two receive events exceed 50 ms, with maximum 205.340 ms; capture maximum is 27.415 ms. Retain Native Surface, changed-region delivery and geometry caching.

Client/FEX RSS peaks at 910.96 MiB, greater than the failed optional-SDL session's sampled 834.43 MiB peak. That reinforces the limit of the earlier diagnosis: client RSS alone does not identify the source of whole-device memory pressure. It does not account for other processes or GPU allocations.

The next focused diagnostic scope is original-library resource creation and graphics synchronization: correlate waited fences with submission identity/age and the resource/upload work preceding them, while exposing resource-loading/serialization boundaries within the untimed part of Draw. The original marked trace shows a large fence/submission stall; this recovery trace shows a submission stall inside atlas texture creation. Both are measured targets. Do not remove synchronization, switch SDL again or select another performance change until these boundaries identify the dominant fix. Android renderer-exit/device-memory observations remain a diagnostic gap if termination recurs.

The recovery check is accepted. The published APK and implementation are unchanged by these notes; no branch, PR, rebuild or release is needed to record this result.
