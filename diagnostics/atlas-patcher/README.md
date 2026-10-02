# Exact atlas upload patch

The patcher accepts only the checksum-pinned Memento client Renderer and FNA
assemblies. It adds one `Memento.AtlasUploads` assembly reference to each and
does not change the client dependency manifest, native FNA3D/SDL libraries,
public signatures, constants or resources. The separate verifier checks the
original and resulting managed assemblies.

`TextureAtlas.AddSprite` retains its original packing, atlas creation, source
span and return behavior. Its single existing `Texture2D.SetDataPointerEXT`
call becomes `AtlasUploads.Upload`, with the texture receiver and identical
arguments. The helper owns temporary pixel copies before the source pin ends.

FNA retains every existing native boundary signature. Each selected boundary
becomes a managed wrapper which calls `AtlasUploads.Flush()` and then exactly
one private extern clone. The clone preserves the original native library,
entry point, calling convention, return/parameter annotations and marshalling
metadata. The helper's flush guard prevents recursive flushing when committed
atlas writes enter the wrapped `SetTextureData2D` boundary.

There are 26 native wrappers:

- Three primitive drawing functions.
- Four texture upload functions and three texture readback functions.
- Backbuffer readback, resolve and reset.
- Four swap-buffer overloads and two render-target overloads.
- Texture disposal, device destruction and clear.
- Both vertex/index buffer upload and readback functions.

`Texture.Dispose(bool)` also flushes at entry, before its original
`Interlocked.Exchange` clears the native texture handle. Its original IL and
exception regions remain intact after this single call. Native texture
disposal stays guarded for direct callers. Other graphics state setters retain
their original behavior.

Run from the repository root after building the helper:

```bash
dotnet run --project diagnostics/atlas-patcher/AtlasPatcher.csproj -- \
  runtime-work/music-fixture/original/FNA.dll \
  runtime-work/atlas-uploads/Memento.AtlasUploads.dll \
  runtime-work/atlas-fixture/fna.dll
dotnet run --project diagnostics/atlas-verify/AtlasVerify.csproj -- \
  runtime-work/music-fixture/original/FNA.dll runtime-work/atlas-fixture/fna.dll
```

Use the same arguments with `ClassicUO.Renderer.dll` and `renderer.dll` for the
Renderer patch. Production APK assets contain verified binary deltas rather
than complete imported client libraries.
