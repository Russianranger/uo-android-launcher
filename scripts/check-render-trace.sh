#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
probe="$PWD/runtime-work/render-probe"
dotnet build diagnostics/render-trace/Memento.RenderTrace.csproj -c Release -o runtime-work/render-trace --nologo
dotnet publish tests/render-probe/RenderProbe.csproj -c Release -r win-x64 --self-contained true -p:RuntimeFrameworkVersion=10.0.8 -o "$probe" --nologo
dotnet run --project diagnostics/render-patcher/RenderPatcher.csproj -- "$probe/RenderProbe.dll" runtime-work/render-trace/Memento.RenderTrace.dll "$probe/RenderProbe.traced.dll" --fixture
mv "$probe/RenderProbe.traced.dll" "$probe/RenderProbe.dll"
# Use the same Wine build/prefix as the managed-loader gate; no graphics needed.
export WINEPREFIX="$PWD/runtime-work/dotnet-wine/prefix"
export WINEDEBUG=-all
mkdir -p "$probe/logs"
xvfb-run -a python3 tests/verify_render_trace.py "$probe/RenderProbe.exe" runtime-work/render-trace/Memento.RenderTrace.dll "$PWD/runtime-work/dotnet-wine/wine/bin/wine" > "$probe/logs/trace.log" 2>&1
cat "$probe/logs/trace.log"
