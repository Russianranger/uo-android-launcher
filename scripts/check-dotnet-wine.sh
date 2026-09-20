#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/build-diagnostics.sh
probe_work="$PWD/runtime-work/dotnet-wine"
mkdir -p "$probe_work/wine"
# Exact Wine 10.0 WoW64 build in the shipped ARM64/Box64 client runtime.
curl -fLsS --retry 3 https://github.com/Kron4ek/Wine-Builds/releases/download/10.0/wine-10.0-amd64-wow64.tar.xz -o "$probe_work/wine.tar.xz"
echo "aeebbbf239e548f0136f1cd72a2e109dd9a572a8f703da3c09fa40d74d5c255f  $probe_work/wine.tar.xz" | sha256sum --check
tar -xJf "$probe_work/wine.tar.xz" --strip-components=1 -C "$probe_work/wine"
dotnet publish tests/managed-probe/ManagedProbe.csproj -c Release -o "$probe_work/app" --nologo
dotnet build tests/graphics-probe/FnaFixture.csproj -c Release -o "$probe_work/fixtures" --nologo
dotnet build tests/graphics-probe/ClientFixture.csproj -c Release -o "$probe_work/fixtures" --nologo
cp "$probe_work/fixtures/FNA.dll" "$probe_work/fixtures/TazUO.dll" "$probe_work/app/"
xvfb-run -a python3 tests/verify_dotnet_wine.py "$probe_work"
