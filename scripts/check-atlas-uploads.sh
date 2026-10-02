#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
work="$PWD/runtime-work/atlas-fixture"
mkdir -p "$work/logs" "$work/original" "$work/patched" "$work/assets"
python3 scripts/fetch-music-fixture.py runtime-work/music-fixture/original
python3 scripts/fetch-atlas-fixture.py runtime-work/music-fixture/original
cp runtime-work/music-fixture/original/*.dll "$work/original/"
dotnet build diagnostics/frame-budget/Memento.FrameBudget.csproj -c Release -o runtime-work/frame-budget --nologo
dotnet build diagnostics/atlas-uploads/Memento.AtlasUploads.csproj -c Release -o runtime-work/atlas-uploads --nologo
cp runtime-work/frame-budget/Memento.FrameBudget.dll "$work/assets/"
cp runtime-work/atlas-uploads/Memento.AtlasUploads.dll "$work/assets/"
cp backend/*.b64 "$work/assets/"
dotnet run --project diagnostics/atlas-patcher/AtlasPatcher.csproj -- "$work/original/FNA.dll" "$work/assets/Memento.AtlasUploads.dll" "$work/fna.dll"
dotnet run --project diagnostics/atlas-patcher/AtlasPatcher.csproj -- "$work/original/ClassicUO.Renderer.dll" "$work/assets/Memento.AtlasUploads.dll" "$work/renderer.dll"
dotnet run --project diagnostics/atlas-verify/AtlasVerify.csproj -- "$work/original/FNA.dll" "$work/fna.dll"
dotnet run --project diagnostics/atlas-verify/AtlasVerify.csproj -- "$work/original/ClassicUO.Renderer.dll" "$work/renderer.dll"
python3 - <<'PY'
from pathlib import Path
import base64,shutil,sys
sys.path.insert(0,'backend')
import client_atlas_uploads as atlas
import client_frame_budget as frame
import client_render_trace as trace
work=Path('runtime-work/atlas-fixture').resolve()
root=work/'patched';assets=work/'assets';metadata={'executable':'TazUO.exe'}
for p in root.iterdir():
    if p.is_file():p.unlink()
for p in (work/'original').glob('*.dll'):shutil.copy2(p,root/p.name)
for original,name,patch,expected in [('FNA.dll','fna.dll',atlas.FNA_PATCH,atlas.FNA_PATCHED),('ClassicUO.Renderer.dll','renderer.dll',atlas.RENDERER_PATCH,atlas.RENDERER_PATCHED)]:
    output=trace.apply_delta((root/original).read_bytes(),base64.b64decode((assets/patch).read_bytes(),validate=False))
    assert output==(work/name).read_bytes() and atlas.digest(work/name)==expected
assert atlas.prepare(root,metadata,assets,True)['action']=='batched_known_client'
assert (root/'FNA.dll').read_bytes()==(work/'fna.dll').read_bytes()
assert (root/'ClassicUO.Renderer.dll').read_bytes()==(work/'renderer.dll').read_bytes()
assert atlas.prepare(root,metadata,assets,True)['action']=='already_batched'
assert frame.prepare(root,metadata,assets,True,False)['frame_budget']['active']
assert atlas.prepare(root,metadata,assets,True)['active']
assert frame.prepare(root,metadata,assets,False,False)['frame_budget']['action']=='restored_original'
assert atlas.prepare(root,metadata,assets,False)['action']=='restored_original'
for name in ['FNA.dll','ClassicUO.Renderer.dll','TazUO.dll']:
    assert (root/name).read_bytes()==(work/'original'/name).read_bytes()
assert atlas.prepare(root,metadata,assets,False)['action']=='unchanged_disabled'
assert atlas.prepare(root,metadata,assets,True)['active']
print('PRODUCTION_ATLAS_DELTAS_MIGRATION_RESTORE_OK')
PY
dotnet build tests/atlas-upload-probe/AtlasUploadProbe.csproj -c Release -m:1 --nologo
dotnet tests/atlas-upload-probe/bin/Release/net10.0/AtlasUploadProbe.dll
gcc -shared -fPIC -O2 -Wall -Werror tests/atlas-boundary-probe/native-shim.c -o "$work/libatlas-shim.so"
gcc -shared -fPIC -O2 -Wall -Werror -DOMIT_TEST_ENTRY tests/atlas-boundary-probe/native-shim.c -o "$work/libatlas-shim-fail.so"
dotnet build tests/atlas-boundary-probe/AtlasBoundaryProbe.csproj -c Release -m:1 --nologo
for item in original:disabled patched:enabled patched:disabled patched:failure; do
  folder="${item%:*}";mode="${item#*:}"
  shim="$work/libatlas-shim.so"
  if [ "$mode" = failure ]; then shim="$work/libatlas-shim-fail.so"; fi
  dotnet tests/atlas-boundary-probe/bin/Release/net10.0/AtlasBoundaryProbe.dll "$work/$folder" "$shim" "$mode"
done
if [ "${1:-}" = --host-only ]; then exit 0; fi
dotnet publish tests/atlas-boundary-probe/AtlasBoundaryProbe.csproj -c Release -r win-x64 --self-contained true -p:RuntimeFrameworkVersion=10.0.8 -o "$work/probe" --nologo
# Force the same external startup-hook load order as the Android launcher.
rm "$work/probe/Memento.FrameBudget.dll" "$work/probe/Memento.AtlasUploads.dll"
x86_64-w64-mingw32-gcc -shared -O2 -Wall -Werror tests/atlas-boundary-probe/native-shim.c -o "$work/atlas-shim.dll"
x86_64-w64-mingw32-gcc -shared -O2 -Wall -Werror -DOMIT_TEST_ENTRY tests/atlas-boundary-probe/native-shim.c -o "$work/atlas-shim-fail.dll"
export WINEPREFIX="$PWD/runtime-work/dotnet-wine/prefix" WINEDEBUG=-all
export WINEDLLOVERRIDES='winemenubuilder,mshtml=;mscoree=b'
xvfb-run -a python3 tests/verify_atlas_wine.py "$work" "$PWD/runtime-work/dotnet-wine/wine/bin/wine" > "$work/logs/wine.log" 2>&1 || { cat "$work/logs/wine.log"; exit 1; }
cat "$work/logs/wine.log"
