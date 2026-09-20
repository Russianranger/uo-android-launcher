#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
probe="$PWD/runtime-work/fna-paint"
mkdir -p "$probe/logs"
# Exact FNA submodule used by TazUO 5.2, not the synthetic diagnostics fixture.
if [ ! -d "$probe/FNA/.git" ]; then
  git clone --quiet --no-checkout https://github.com/FNA-XNA/FNA.git "$probe/FNA"
fi
git -C "$probe/FNA" checkout --quiet fb477d965e2e7c531a7dba3a10295ff1f8d1fb9f
git -C "$probe/FNA" submodule update --init --depth 1 lib/SDL2-CS lib/SDL3-CS lib/FAudio lib/Theorafile
dotnet build "$probe/FNA/FNA.Core.csproj" -p:TargetFramework=net10.0 -c Release -o "$probe/fna-build" --nologo
dotnet publish tests/paint-probe/PaintProbe.csproj -c Release -o "$probe/app" --nologo
cp runtime-work/sdl-probe/updated/FNA3D.dll runtime-work/sdl-probe/updated/SDL3.dll "$probe/app/"
client_ref=https://raw.githubusercontent.com/PlayTazUO/TazUO/73768f6653d39788b00f5bce5b2a063dc76452aa/external/x64
for library in FAudio.dll libtheorafile.dll; do
  curl -fLsS --retry 3 "$client_ref/$library" -o "$probe/app/$library"
done
echo "cbb99eef92a03d7a28f713011132b0dbe52543439e77ac41852b6a2ae8b08271  $probe/app/FAudio.dll" | sha256sum --check
echo "3db76c1590d92d179ed6cc0532ea28be362cf9f0ac30b248e8c7453847182a47  $probe/app/libtheorafile.dll" | sha256sum --check
xvfb-run -a python3 tests/verify_paint_wine.py "$probe"
