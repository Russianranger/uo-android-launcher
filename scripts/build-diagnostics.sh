#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
dotnet build diagnostics/Memento.Diagnostics.csproj -c Release -o runtime-work/diagnostics --nologo
mkdir -p backend-assets
cp runtime-work/diagnostics/Memento.Diagnostics.dll backend-assets/Memento.Diagnostics.dll

dotnet build diagnostics/render-trace/Memento.RenderTrace.csproj -c Release -o runtime-work/render-trace --nologo
cp runtime-work/render-trace/Memento.RenderTrace.dll backend-assets/Memento.RenderTrace.dll
dotnet build diagnostics/frame-budget/Memento.FrameBudget.csproj -c Release -o runtime-work/frame-budget --nologo
cp runtime-work/frame-budget/Memento.FrameBudget.dll backend-assets/Memento.FrameBudget.dll
