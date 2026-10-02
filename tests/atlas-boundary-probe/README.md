This probe loads the checksum-pinned imported FNA and ClassicUO.Renderer DLLs,
including their production patches. It does not replace either managed assembly
with a fixture implementation. Its native FNA3D library is a small C shim that
records every argument and copies uploaded texels into a test image.

`AtlasBoundaryProbe fixture-folder native-shim enabled|disabled|failure` runs in
an isolated process. The root `scripts/check-atlas-uploads.sh` prepares and checks
the production deltas, then runs the host probes and the Windows .NET/Wine probe.
`tests/verify_atlas_wine.py` repeats original/disabled, patched/enabled,
patched/disabled and patched/native-failure cases.

The probe executes all 26 intercepted FNA native overloads. It checks scalar and
pointer arguments, native by-reference writeback, upload-before-observer order,
exactly one original native invocation, reentrant flushing, and native entry-point
failure propagation. It executes the imported Texture2D.Dispose body with pending
pixels to verify that uploads occur before its native texture handle is cleared.
A disposed-device state checks that the helper discards unobservable pending
pixels instead of submitting them through an invalid device.

It also executes the imported TextureAtlas.AddSprite with its actual original
StbRectPackSharp.Packer. Twelve 8x8 sprites fill two rows of six in a 64x64 atlas.
Their twelve reserved 10x10 footprints form one 60x20 rectangle. The enabled
production helper must reduce twelve native uploads to one, retain every sprite
pixel and returned UV rectangle, initialize only fresh reserved margins to
transparent, and preserve a historical texel beyond those reservations. This
catches ineffective batching that ignores the packer's one-pixel margin.

The fake native graphics device and texture handles avoid creating a window or
requiring game assets. These checks validate managed batching and native ABI
preservation; they do not measure real Vulkan driver timing or device gameplay.
