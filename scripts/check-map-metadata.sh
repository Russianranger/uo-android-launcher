#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
work="$PWD/runtime-work/map-metadata-fixture"
mkdir -p "$work/logs"
# check-resource-trace generates the exact accepted ordinary and .19 inputs.
dotnet build diagnostics/frame-budget/Memento.FrameBudget.csproj -c Release -o runtime-work/frame-budget --nologo
dotnet build diagnostics/map-metadata-patcher/MapMetadataPatcher.csproj -c Release --nologo
dotnet build diagnostics/map-metadata-verify/MapMetadataVerify.csproj -c Release --nologo
python3 - <<'PY'
from pathlib import Path
import shutil
work=Path('runtime-work/map-metadata-fixture')
r=Path('runtime-work/resource-fixture')
for variant in ('ordinary','ordinary-render','resource','resource-render'):
    root=work/('base-'+variant);root.mkdir(exist_ok=True)
    source=r/('patched' if variant.startswith('resource') else 'base')
    for p in source.glob('*.dll'):shutil.copy2(p,root/p.name)
    if variant.endswith('render'):
        for name in ('TazUO.dll','ClassicUO.Assets.dll'):
            shutil.copy2(r/'variants'/(name+'.new' if variant.startswith('resource') else name),root/name)
    shutil.copy2('runtime-work/frame-budget/Memento.FrameBudget.dll',root/'Memento.FrameBudget.dll')
    patched=work/('patched-'+variant);patched.mkdir(exist_ok=True)
    for p in root.glob('*.dll'):shutil.copy2(p,patched/p.name)
PY
for variant in ordinary ordinary-render resource resource-render; do
  for library in TazUO ClassicUO.Assets; do
    dotnet run --project diagnostics/map-metadata-patcher/MapMetadataPatcher.csproj -c Release --no-build -- "$work/base-$variant/$library.dll" runtime-work/frame-budget/Memento.FrameBudget.dll "$work/patched-$variant/$library.dll"
    dotnet run --project diagnostics/map-metadata-verify/MapMetadataVerify.csproj -c Release --no-build -- "$work/base-$variant/$library.dll" "$work/patched-$variant/$library.dll"
  done
done
python3 - <<'PY'
from pathlib import Path
import base64,hashlib,sys
sys.path.insert(0,'backend')
import client_map_metadata_variants as variants,client_render_trace as trace
work=Path('runtime-work/map-metadata-fixture')
expected={(name,base):(out,delta) for name,base,out,delta in variants.VARIANTS}
assert len(expected)==8,'Generate and commit the eight exact map metadata deltas first'
for variant in ('ordinary','ordinary-render','resource','resource-render'):
    for name in ('TazUO.dll','ClassicUO.Assets.dll'):
        before=(work/('base-'+variant)/name).read_bytes();after=(work/('patched-'+variant)/name).read_bytes()
        base=hashlib.sha256(before).hexdigest();out,delta=expected[name,base]
        assert hashlib.sha256(after).hexdigest()==out,(name,variant)
        assert trace.apply_delta(before,base64.b64decode(Path('backend',delta).read_bytes(),validate=True))==after,delta
print('MAP_METADATA_DELTAS_VERIFIED variants=8 original_diagnostics_preserved=true')
PY
# Resource dependencies are already downloaded by the previous qualification
# gate. The only fixture inputs are synthetic MUL/static gate files generated
# by the probe; complete user client/map files are never needed here.
dotnet build tests/map-metadata-probe/MapMetadataProbe.csproj -c Release --nologo -m:1
logs=()
for variant in ordinary ordinary-render resource resource-render; do
  modes=(disabled)
  if [[ "$variant" == resource* ]]; then modes=(enabled disabled); fi
  for mode in "${modes[@]}"; do
    for policy in baseline optimized; do
      selection=base
      if [[ "$policy" == optimized ]]; then selection=patched; fi
      log="$work/logs/host-$variant-$mode-$policy.log"
      dotnet run --project tests/map-metadata-probe/MapMetadataProbe.csproj -c Release --no-build -- "$work/$selection-$variant" "$mode" "$policy" > "$log" 2>&1 || { cat "$log"; exit 1; }
      cat "$log"
      logs+=("$log")
    done
  done
done
python3 tests/compare_map_metadata_runtime.py "${logs[@]}"
if [ "${1:-}" = --host-only ]; then exit 0; fi
dotnet publish tests/map-metadata-probe/MapMetadataProbe.csproj -c Release -r win-x64 --self-contained true -p:RuntimeFrameworkVersion=10.0.8 -o "$work/probe" --nologo
rm "$work/probe/Memento.FrameBudget.dll"
export WINEPREFIX="$PWD/runtime-work/dotnet-wine/prefix" WINEDEBUG=-all WINEDLLOVERRIDES='winemenubuilder,mshtml=;mscoree=b'
xvfb-run -a python3 tests/verify_map_metadata_wine.py "$work" "$PWD/runtime-work/dotnet-wine/wine/bin/wine" > "$work/logs/wine.log" 2>&1 || { cat "$work/logs/wine.log"; exit 1; }
cat "$work/logs/wine.log"
