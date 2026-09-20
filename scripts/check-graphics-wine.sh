#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Wine services retain X connections after the first process exits. Keep the
# same display for both variants and stop services before xvfb-run tears down.
if [ "${MEMENTO_GRAPHICS_XVFB:-}" != 1 ]; then
  exec xvfb-run -a env MEMENTO_GRAPHICS_XVFB=1 bash "$0"
fi
probe="$PWD/runtime-work/sdl-probe"
mkdir -p "$probe/logs" "$probe/sdk" "$probe/original" "$probe/updated"
python3 scripts/prepare-sdl.py
curl -fLsS --retry 3 https://github.com/libsdl-org/SDL/releases/download/release-3.4.16/SDL3-devel-3.4.16-mingw.tar.gz -o "$probe/sdk.tar.gz"
echo "c7ef65bd72eabac6e5b535411dbd8d5824d0aab24fd62ff8812666b336f18a9c  $probe/sdk.tar.gz" | sha256sum --check
tar -xzf "$probe/sdk.tar.gz" --strip-components=1 -C "$probe/sdk"
curl -fLsS --retry 3 https://raw.githubusercontent.com/FNA-XNA/FNA3D/de4870e6cd215ea97ea6109cc72c25c0276f1bec/include/FNA3D.h -o "$probe/FNA3D.h"
client_ref=https://raw.githubusercontent.com/PlayTazUO/TazUO/73768f6653d39788b00f5bce5b2a063dc76452aa/external/x64
curl -fLsS --retry 3 "$client_ref/FNA3D.dll" -o "$probe/original/FNA3D.dll"
curl -fLsS --retry 3 "$client_ref/SDL3.dll" -o "$probe/original/SDL3.dll"
echo "93ca16fb415438830bd1591ac25fabb92a2b532cb629b215c8bd7d73ca806eb8  $probe/original/FNA3D.dll" | sha256sum --check
echo "f53fbe656b784365dc1db0de61958a51a41b5923ab9623bf2f7af4eca9649c09  $probe/original/SDL3.dll" | sha256sum --check
x86_64-w64-mingw32-gcc -O2 -Wall -Wextra -Werror tests/fna-vulkan-probe.c -I "$probe" \
  -I "$probe/sdk/x86_64-w64-mingw32/include" -L "$probe/sdk/x86_64-w64-mingw32/lib" -lSDL3 -o "$probe/original/probe.exe"
cp "$probe/original/probe.exe" "$probe/original/FNA3D.dll" "$probe/updated/"
cp backend-assets/SDL3-3.4.16-x64.dll "$probe/updated/SDL3.dll"
export WINEPREFIX="$PWD/runtime-work/dotnet-wine/prefix" WINEDEBUG=-all,err+all
export WINEDLLOVERRIDES='winemenubuilder,mshtml=;mscoree=b;d3d11,dxgi=b'
export FNA3D_FORCE_DRIVER=Vulkan SDL_GPU_DRIVER=vulkan
wine="$PWD/runtime-work/dotnet-wine/wine/bin/wine"
wine_server="$PWD/runtime-work/dotnet-wine/wine/bin/wineserver"
trap 'timeout 15 "$wine_server" -k; timeout 15 "$wine_server" -w' EXIT
for variant in original updated; do
  if ! timeout 120 "$wine" "$probe/$variant/probe.exe" > "$probe/logs/$variant.log" 2>&1; then
    cat "$probe/logs/$variant.log"; exit 1
  fi
  cat "$probe/logs/$variant.log"
  grep -q FNA_VULKAN_LIFETIME_OK "$probe/logs/$variant.log"
  grep -qi 'Vulkan' "$probe/logs/$variant.log"
done
grep -q SDL=3004016 "$probe/logs/updated.log"
