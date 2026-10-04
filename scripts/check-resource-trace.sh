#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
work="$PWD/runtime-work/resource-fixture"
mkdir -p "$work/logs" "$work/base" "$work/patched" "$work/variants" "$work/assets"
# Earlier suites verify the unmodified client, frame budget and atlas bases.
# This suite only adds passive scopes to those exact published outputs.
dotnet build diagnostics/frame-budget/Memento.FrameBudget.csproj -c Release -o runtime-work/frame-budget --nologo
dotnet build diagnostics/resource-patcher/ResourcePatcher.csproj -c Release --nologo
dotnet build diagnostics/resource-verify/ResourceVerify.csproj -c Release --nologo
dotnet run --project diagnostics/resource-verify/ResourceVerify.csproj -c Release --no-build -- --helper-cpu-policy runtime-work/frame-budget/Memento.FrameBudget.dll
python3 - <<'PY'
from pathlib import Path
import base64,shutil,sys
sys.path.insert(0,'backend')
import client_render_trace as trace,client_frame_budget as frame,client_music_cache as music,client_cold_trace as cold
work=Path('runtime-work/resource-fixture')
for p in Path('runtime-work/atlas-fixture/patched').glob('*.dll'):shutil.copy2(p,work/'base'/p.name)
original=Path('runtime-work/atlas-fixture/original')
for name,base,patch in [('TazUO.dll',original/'TazUO.dll',frame.PATCH),('ClassicUO.Assets.dll',original/'ClassicUO.Assets.dll',music.PATCH),('FNA.dll',work/'base/FNA.dll',cold.PATCH)]:
    data=trace.apply_delta(base.read_bytes(),base64.b64decode(Path('backend',patch).read_bytes()))
    (work/'base'/name).write_bytes(data)
for p in (work/'base').glob('*.dll'):shutil.copy2(p,work/'patched'/p.name)
(work/'variants/TazUO.dll').write_bytes(trace.apply_delta((original/'TazUO.dll').read_bytes(),base64.b64decode(Path('backend',frame.COMBINED_PATCH).read_bytes())))
shutil.copy2(original/'ClassicUO.Assets.dll',work/'variants/ClassicUO.Assets.dll')
PY
for library in TazUO ClassicUO.Assets ClassicUO.IO ClassicUO.Renderer FNA; do
  dotnet run --project diagnostics/resource-patcher/ResourcePatcher.csproj -c Release --no-build -- "$work/base/$library.dll" runtime-work/frame-budget/Memento.FrameBudget.dll "$work/patched/$library.dll"
  dotnet run --project diagnostics/resource-verify/ResourceVerify.csproj -c Release --no-build -- "$work/base/$library.dll" "$work/patched/$library.dll"
done
for library in TazUO ClassicUO.Assets; do
  dotnet run --project diagnostics/resource-patcher/ResourcePatcher.csproj -c Release --no-build -- "$work/variants/$library.dll" runtime-work/frame-budget/Memento.FrameBudget.dll "$work/variants/$library.dll.new"
  dotnet run --project diagnostics/resource-verify/ResourceVerify.csproj -c Release --no-build -- "$work/variants/$library.dll" "$work/variants/$library.dll.new"
done
python3 - <<'PY'
from pathlib import Path
import base64,hashlib,json,shutil,sys
sys.path.insert(0,'backend')
import client_cold_resources as resources,client_cold_trace as cold,client_render_trace as trace,client_atlas_uploads as atlas
work=Path('runtime-work/resource-fixture').resolve()
for name,base,patched,patch in resources.VARIANTS:
    root=work/'variants' if name in ('TazUO.dll','ClassicUO.Assets.dll') and hashlib.sha256((work/'variants'/name).read_bytes()).hexdigest()==base else work/'base'
    before=(root/name).read_bytes()
    after=(work/'variants'/(name+'.new')).read_bytes() if root.name=='variants' else (work/'patched'/name).read_bytes()
    assert hashlib.sha256(before).hexdigest()==base and hashlib.sha256(after).hexdigest()==patched,(name,base)
    assert trace.apply_delta(before,base64.b64decode(Path('backend',patch).read_bytes()))==after,patch
assets=work/'assets';session=work/'session';session.mkdir(exist_ok=True)
for p in Path('backend').glob('*.b64'):shutil.copy2(p,assets/p.name)
shutil.copy2('runtime-work/frame-budget/Memento.FrameBudget.dll',assets/'Memento.FrameBudget.dll')
# This sentinel checks the backend's checksummed manifest/rollback transaction;
# separate native GPU suites exercise the actual ARM64 Vulkan observer.
(assets/cold.LIBRARY).write_bytes(b'backend transaction fixture, not an executable observer')
(assets/'vulkan-trace-bundle.json').write_text(json.dumps({'format':1,'revision':2,'sha256':cold.digest(assets/cold.LIBRARY)}))
root=work/'activation';root.mkdir(exist_ok=True)
for p in root.iterdir():
    if p.is_file():p.unlink()
for p in (work/'base').glob('*.dll'):shutil.copy2(p,root/p.name)
atlas_base=Path('runtime-work/atlas-fixture/patched/FNA.dll')
shutil.copy2(atlas_base,root/'FNA.dll')
shutil.copy2('runtime-work/atlas-fixture/original/FNA.dll',root/('FNA.dll'+atlas.BACKUP_SUFFIX))
before={p.name:p.read_bytes() for p in root.glob('*.dll')}
report=cold.prepare(root,{'executable':'TazUO.exe'},assets,session,True,True)
assert report['active'] and report['revision']==3 and report['native_revision']==2,report
for name,data in report['resource_libraries'].items():assert cold.digest(root/name)==data
assert cold.restore(root,{'executable':'TazUO.exe'})
assert all((root/name).read_bytes()==data for name,data in before.items())
assert not cold.restore(root,{'executable':'TazUO.exe'})
assert not cold.prepare(root,{'executable':'TazUO.exe'},assets,session,False,True)['active']
print('PRODUCTION_RESOURCE_DELTAS_TRANSACTION_RESTORE_OK variants=7 libraries=5')
PY
python3 scripts/fetch-resource-fixture.py "$work/patched"
dotnet build tests/resource-trace-probe/ResourceTraceProbe.csproj -c Release --nologo -m:1
for mode in enabled disabled; do
  dotnet run --project tests/resource-trace-probe/ResourceTraceProbe.csproj -c Release --no-build -- "$work/patched" "$mode"
done
if [ "${1:-}" = --host-only ]; then exit 0; fi
dotnet publish tests/resource-trace-probe/ResourceTraceProbe.csproj -c Release -r win-x64 --self-contained true -p:RuntimeFrameworkVersion=10.0.8 -o "$work/probe" --nologo
rm "$work/probe/Memento.FrameBudget.dll"
export WINEPREFIX="$PWD/runtime-work/dotnet-wine/prefix" WINEDEBUG=-all WINEDLLOVERRIDES='winemenubuilder,mshtml=;mscoree=b'
xvfb-run -a python3 tests/verify_resource_wine.py "$work" "$PWD/runtime-work/dotnet-wine/wine/bin/wine" > "$work/logs/wine.log" 2>&1 || { cat "$work/logs/wine.log"; exit 1; }
cat "$work/logs/wine.log"
