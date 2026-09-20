#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
dotnet build diagnostics/Memento.Diagnostics.csproj -c Release -o runtime-work/diagnostics --nologo
mkdir -p backend-assets
cp runtime-work/diagnostics/Memento.Diagnostics.dll backend-assets/Memento.Diagnostics.dll
