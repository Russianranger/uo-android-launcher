#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
work="$PWD/runtime-work/frame-fixture"
mkdir -p "$work/logs" "$work/patched" "$work/combined"
python3 scripts/fetch-music-fixture.py "$work/original"
dotnet build diagnostics/frame-budget/Memento.FrameBudget.csproj -c Release -o runtime-work/frame-budget --nologo
dotnet build diagnostics/render-trace/Memento.RenderTrace.csproj -c Release -o runtime-work/render-trace --nologo
python3 - <<'PY'
from pathlib import Path
import base64,sys
sys.path.insert(0,'backend')
import client_render_trace as trace
work=Path('runtime-work/frame-fixture')
data=trace.apply_delta((work/'original/TazUO.dll').read_bytes(),base64.b64decode(Path('backend',trace.PATCH).read_bytes()))
assert __import__('hashlib').sha256(data).hexdigest()==trace.INSTRUMENTED
(work/'render.dll').write_bytes(data)
PY
dotnet run --project diagnostics/frame-patcher/FramePatcher.csproj -- "$work/original/TazUO.dll" runtime-work/frame-budget/Memento.FrameBudget.dll "$work/budget.dll"
dotnet run --project diagnostics/frame-patcher/FramePatcher.csproj -- "$work/render.dll" runtime-work/frame-budget/Memento.FrameBudget.dll "$work/combined.dll"
dotnet run --project diagnostics/render-verify/RenderVerify.csproj -- "$work/original/TazUO.dll" "$work/budget.dll" --frame
dotnet run --project diagnostics/render-verify/RenderVerify.csproj -- "$work/render.dll" "$work/combined.dll" --frame
python3 - <<'PY'
from pathlib import Path
import shutil,sys
sys.path.insert(0,'backend')
import client_frame_budget as frame
work=Path('runtime-work/frame-fixture').resolve()
for folder,render,name in [('patched',False,'budget.dll'),('combined',True,'combined.dll')]:
    root=work/folder
    for p in (work/'original').glob('*.dll'):shutil.copy2(p,root/p.name)
    assets=work/'assets';assets.mkdir(exist_ok=True)
    for p in Path('backend').glob('*.b64'):shutil.copy2(p,assets/p.name)
    for path in ['runtime-work/frame-budget/Memento.FrameBudget.dll','runtime-work/render-trace/Memento.RenderTrace.dll']:
        shutil.copy2(path,assets/Path(path).name)
    result=frame.prepare(root,{'executable':'TazUO.exe'},assets,True,render)
    assert result['frame_budget']['active'] and result['render_trace']['active']==render,result
    assert (root/'TazUO.dll').read_bytes()==(work/name).read_bytes()
    assert frame.prepare(root,{'executable':'TazUO.exe'},assets,True,render)['frame_budget']['action']=='already_active'
print('PRODUCTION_FRAME_DELTAS_OK')
PY
for mode in original patched combined; do
  expected=budget; if [ "$mode" = original ]; then expected=original; fi
  dotnet run --project tests/frame-probe/FrameProbe.csproj -- "$work/$mode" "$expected"
done
if [ "${1:-}" = --host-only ]; then exit 0; fi
dotnet publish tests/frame-probe/FrameProbe.csproj -c Release -r win-x64 --self-contained true -p:RuntimeFrameworkVersion=10.0.8 -o "$work/probe" --nologo
# The helper is deliberately absent beside the executable. Resolve it through
# the same absolute startup-hook path used by the launcher, before client JIT.
rm "$work/probe/Memento.FrameBudget.dll"
export WINEPREFIX="$PWD/runtime-work/dotnet-wine/prefix" WINEDEBUG=-all
export WINEDLLOVERRIDES='winemenubuilder,mshtml=;mscoree=b'
xvfb-run -a python3 tests/verify_frame_wine.py "$work" "$PWD/runtime-work/dotnet-wine/wine/bin/wine" > "$work/logs/wine.log" 2>&1 || { cat "$work/logs/wine.log"; exit 1; }
cat "$work/logs/wine.log"
python3 - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0,'backend')
import client_frame_budget as frame
work=Path('runtime-work/frame-fixture').resolve()
for name in ['patched','combined']:
    result=frame.prepare(work/name,{'executable':'TazUO.exe'},work/'assets',False,False)
    assert result['frame_budget']['action']=='restored_original'
    assert (work/name/'TazUO.dll').read_bytes()==(work/'original/TazUO.dll').read_bytes()
print('PRODUCTION_FRAME_RESTORE_OK')
PY
