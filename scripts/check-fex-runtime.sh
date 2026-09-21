#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test "$(uname -m)" = aarch64
mkdir -p runtime-work/fex/logs runtime-work/fex/app
dotnet publish tests/managed-probe/ManagedProbe.csproj -c Release -o runtime-work/fex/app --nologo
# Run Windows x64 .NET on a native ARM64 Wine/FEX image, without Box64.
docker run --rm --init -v "$PWD/runtime-work/fex:/check" memento-fex:1 bash -c '
set -euo pipefail
export WINEPREFIX=/check/prefix WINEARCH=win64 WINEDEBUG=-all,err+all
export DISPLAY=:8
XvfbMissing=0
Xtigervnc :8 -geometry 1280x720 -depth 24 -rfbport -1 -SecurityTypes None -nolisten tcp -ac >/check/logs/display.log 2>&1 &
trap "/opt/wine/bin/wineserver -k || true" EXIT
sleep 2
WINEDLLOVERRIDES="winemenubuilder,mshtml,mscoree=" timeout 180 /opt/wine/bin/wine wineboot -u >/check/logs/prefix.log 2>&1
export WINEDLLOVERRIDES="winemenubuilder,mshtml=;mscoree=b"
timeout 120 /opt/wine/bin/wine /check/app/ManagedProbe.exe >/check/logs/dotnet.log 2>&1
grep -q "MEMENTO_MANAGED_OK .NET 10.0.8 System.Runtime" /check/logs/dotnet.log
test ! -e /usr/local/bin/box64
fileNotNeeded=0
echo "Windows x64 .NET 10.0.8 passed on native ARM64 Wine + FEX"
'
