#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
work="$PWD/runtime-work/cold-trace"
mkdir -p "$work/logs" "$work/patched"
# The atlas suite has verified the production base and original pixel behavior.
cp runtime-work/atlas-fixture/patched/*.dll "$work/patched/"
dotnet build diagnostics/frame-budget/Memento.FrameBudget.csproj -c Release -o runtime-work/frame-budget --nologo
dotnet run --project diagnostics/graphics-patcher/GraphicsPatcher.csproj -- runtime-work/atlas-fixture/patched/FNA.dll runtime-work/frame-budget/Memento.FrameBudget.dll "$work/patched/FNA.dll"
dotnet run --project diagnostics/graphics-verify/GraphicsVerify.csproj -- runtime-work/atlas-fixture/patched/FNA.dll "$work/patched/FNA.dll"
python3 - <<'PY'
from pathlib import Path
import base64,sys
sys.path.insert(0,'backend')
import client_cold_trace as cold,client_render_trace as trace
base=Path('runtime-work/atlas-fixture/patched/FNA.dll').read_bytes()
shipped=trace.apply_delta(base,base64.b64decode(Path('backend',cold.PATCH).read_bytes()))
assert shipped==Path('runtime-work/cold-trace/patched/FNA.dll').read_bytes()
print('PRODUCTION_COLD_DELTA_OK')
PY
cc -shared -fPIC -O2 -Wall -Wextra -Werror tests/atlas-boundary-probe/native-shim.c -o "$work/shim.so"
cc -shared -fPIC -O2 -DOMIT_TEST_ENTRY -Wall -Wextra -Werror tests/atlas-boundary-probe/native-shim.c -o "$work/failure.so"
dotnet build tests/cold-trace-probe/ColdTraceProbe.csproj -c Release --nologo -m:1
dotnet build tests/atlas-boundary-probe/AtlasBoundaryProbe.csproj -c Release --nologo -m:1
dotnet build tests/graphics-boundary-probe/GraphicsBoundaryProbe.csproj -c Release --nologo -m:1
for mode in enabled disabled; do
  dotnet run --project tests/cold-trace-probe/ColdTraceProbe.csproj -c Release --no-build -- "$mode"
  MEMENTO_COLD_TRACE=1 dotnet run --project tests/atlas-boundary-probe/AtlasBoundaryProbe.csproj -c Release --no-build -- "$work/patched" "$work/shim.so" "$mode"
done
MEMENTO_COLD_TRACE=1 dotnet run --project tests/atlas-boundary-probe/AtlasBoundaryProbe.csproj -c Release --no-build -- "$work/patched" "$work/failure.so" failure
MEMENTO_COLD_TRACE=1 dotnet run --project tests/graphics-boundary-probe/GraphicsBoundaryProbe.csproj -c Release --no-build -- "$work/patched" "$work/shim.so"
if [ "${1:-}" = --host-only ]; then exit 0; fi
x86_64-w64-mingw32-gcc -shared -O2 -Wall -Wextra -Werror tests/atlas-boundary-probe/native-shim.c -o "$work/shim.dll"
dotnet publish tests/graphics-boundary-probe/GraphicsBoundaryProbe.csproj -c Release -r win-x64 --self-contained true -p:RuntimeFrameworkVersion=10.0.8 -o "$work/probe" --nologo
rm "$work/probe/Memento.FrameBudget.dll"
export WINEPREFIX="$PWD/runtime-work/dotnet-wine/prefix" WINEDEBUG=-all WINEDLLOVERRIDES='winemenubuilder,mshtml=;mscoree=b'
xvfb-run -a python3 tests/verify_cold_wine.py "$work" "$PWD/runtime-work/dotnet-wine/wine/bin/wine" > "$work/logs/wine.log" 2>&1 || { cat "$work/logs/wine.log"; exit 1; }
cat "$work/logs/wine.log"
