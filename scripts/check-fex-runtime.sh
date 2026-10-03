#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test "$(uname -m)" = aarch64
show_failure_logs() {
  result=$?
  if [ "$result" != 0 ]; then
    python3 - <<'PYLOG'
from pathlib import Path
for p in sorted(Path('runtime-work/fex/logs').glob('*.log')):
    print(p.name, flush=True)
    print(p.read_text(errors='replace')[-16000:], flush=True)
PYLOG
  fi
  exit "$result"
}
trap show_failure_logs EXIT
mkdir -p runtime-work/fex/logs runtime-work/fex/app runtime-work/fex/stress runtime-work/fex/graphics
dotnet publish tests/managed-probe/ManagedProbe.csproj -c Release -o runtime-work/fex/app --nologo
dotnet publish tests/fex-probe/FexProbe.csproj -c Release -o runtime-work/fex/stress --nologo
probe="$PWD/runtime-work/fex"
git init "$probe/proot"
git -C "$probe/proot" remote add origin https://github.com/termux/proot.git
git -C "$probe/proot" fetch --depth 1 origin 7266fb3e8516535682f5a9c8f3a7e70f6506eddb
git -C "$probe/proot" checkout --detach FETCH_HEAD
git -C "$probe/proot" apply "$PWD/native/proot-acceleration.patch" "$PWD/native/proot-sysvipc.patch"
python3 - <<'PY'
from pathlib import Path
p=Path('runtime-work/fex/proot/src/extension/ashmem_memfd/ashmem_memfd.c')
p.write_text('#include <string.h>\n'+p.read_text())
PY
cp tests/run-fex-proot.sh "$probe/proot-probes.sh"
cp backend/client_runtime.py "$probe/client_runtime.py"
mkdir -p "$probe/backend"
cp backend/*.py "$probe/backend/"
mkdir -p "$probe/trace-layer"
cp backend-assets/libmemento-vulkan-trace.so "$probe/trace-layer/"
python3 - <<'PY'
from pathlib import Path
import json
Path('runtime-work/fex/trace-layer/trace.json').write_text(json.dumps({'file_format_version':'1.0.0','layer':{'name':'VK_LAYER_MEMENTO_cold_trace','type':'GLOBAL','library_path':'/check/trace-layer/libmemento-vulkan-trace.so','api_version':'1.3.0','implementation_version':1,'description':'Memento passive timing'}}))
PY
# Exercise the actual managed diagnostic FNA under the retained Windows x64
# translator, in addition to host ABI verification and the real native GPU run.
bash scripts/check-atlas-uploads.sh --host-only > "$probe/logs/atlas-host.log" 2>&1
bash scripts/check-cold-trace.sh --host-only > "$probe/logs/cold-host.log" 2>&1
cp -a runtime-work/cold-trace/patched "$probe/cold-fixture"
cp runtime-work/frame-budget/Memento.FrameBudget.dll "$probe/trace-layer/"
x86_64-w64-mingw32-gcc -shared -O2 -Wall -Wextra -Werror tests/atlas-boundary-probe/native-shim.c -o "$probe/trace-layer/shim.dll"
dotnet publish tests/graphics-boundary-probe/GraphicsBoundaryProbe.csproj -c Release -r win-x64 --self-contained true -p:RuntimeFrameworkVersion=10.0.8 -o "$probe/cold-boundaries" --nologo
dotnet publish tests/cold-trace-probe/ColdTraceProbe.csproj -c Release -r win-x64 --self-contained true -p:RuntimeFrameworkVersion=10.0.8 -o "$probe/cold-frames" --nologo
rm "$probe/cold-boundaries/Memento.FrameBudget.dll"
cp native/pcm_trasc.c tests/check_wasapi_audio.py "$probe/"
cp tests/prefix-wine-probe.py "$probe/prefix-wine-probe.py"
curl -fLsS --retry 3 https://github.com/libsdl-org/SDL/releases/download/release-3.4.16/SDL3-devel-3.4.16-mingw.tar.gz -o "$probe/sdk.tar.gz"
echo "c7ef65bd72eabac6e5b535411dbd8d5824d0aab24fd62ff8812666b336f18a9c  $probe/sdk.tar.gz" | sha256sum --check
mkdir -p "$probe/sdk"
tar -xzf "$probe/sdk.tar.gz" --strip-components=1 -C "$probe/sdk"
curl -fLsS --retry 3 https://raw.githubusercontent.com/FNA-XNA/FNA3D/de4870e6cd215ea97ea6109cc72c25c0276f1bec/include/FNA3D.h -o "$probe/FNA3D.h"
client_ref=https://raw.githubusercontent.com/PlayTazUO/TazUO/73768f6653d39788b00f5bce5b2a063dc76452aa/external/x64
curl -fLsS --retry 3 "$client_ref/FNA3D.dll" -o "$probe/graphics/FNA3D.dll"
curl -fLsS --retry 3 "$client_ref/SDL3.dll" -o "$probe/graphics/SDL3.dll"
echo "93ca16fb415438830bd1591ac25fabb92a2b532cb629b215c8bd7d73ca806eb8  $probe/graphics/FNA3D.dll" | sha256sum --check
echo "f53fbe656b784365dc1db0de61958a51a41b5923ab9623bf2f7af4eca9649c09  $probe/graphics/SDL3.dll" | sha256sum --check
x86_64-w64-mingw32-gcc -O2 -Wall -Wextra -Werror tests/fna-vulkan-probe.c -I "$probe" \
  -I "$probe/sdk/x86_64-w64-mingw32/include" -L "$probe/sdk/x86_64-w64-mingw32/lib" -lSDL3 -o "$probe/graphics/probe.exe"
x86_64-w64-mingw32-gcc -O2 -Wall -Wextra -Werror tests/wasapi-audio-probe.c \
  -I "$probe/sdk/x86_64-w64-mingw32/include" -L "$probe/sdk/x86_64-w64-mingw32/lib" -lSDL3 -lm -o "$probe/graphics/audio-probe.exe"
# Run Windows x64 .NET on a native ARM64 Wine/FEX image, without Box64.
docker run --rm --init -i --cap-add SYS_PTRACE --security-opt seccomp=unconfined -v "$PWD/runtime-work/fex:/check" memento-fex:1 bash <<'PROBE'
set -euo pipefail
python3 -c "import sys,json; sys.path.insert(0,'/check'); import client_runtime; print(json.dumps(client_runtime.inspect(),indent=2))" >/check/logs/runtime-identity.log
export WINEPREFIX=/tmp/fex-prefix WINEARCH=win64 WINEDEBUG=-all,err+all
export DISPLAY=:8
Xtigervnc :8 -geometry 1280x720 -depth 24 -rfbport -1 -SecurityTypes None -nolisten tcp -ac >/check/logs/display.log 2>&1 &
trap "/opt/wine/bin/wineserver -k || true" EXIT
sleep 2
WINEDLLOVERRIDES="winemenubuilder,mshtml,mscoree=" timeout 180 /opt/wine/bin/wine wineboot -u >/check/logs/prefix.log 2>&1
export WINEDLLOVERRIDES="winemenubuilder,mshtml=;mscoree=b"
timeout 120 /opt/wine/bin/wine /check/app/ManagedProbe.exe >/check/logs/dotnet.log 2>&1
grep -q "MEMENTO_MANAGED_OK .NET 10.0.8 System.Runtime" /check/logs/dotnet.log
test ! -e /usr/local/bin/box64
timeout 150 /opt/wine/bin/wine /check/stress/FexProbe.exe >/check/logs/stress.log 2>&1
grep -q FEX_DOTNET_STRESS_OK /check/logs/stress.log
FNA3D_FORCE_DRIVER=Vulkan SDL_GPU_DRIVER=vulkan timeout 180 /opt/wine/bin/wine /check/graphics/probe.exe >/check/logs/graphics.log 2>&1
grep -q FNA_VULKAN_LIFETIME_OK /check/logs/graphics.log
FNA3D_FORCE_DRIVER=Vulkan SDL_GPU_DRIVER=vulkan VK_LAYER_PATH=/check/trace-layer VK_INSTANCE_LAYERS=VK_LAYER_MEMENTO_cold_trace timeout 180 /opt/wine/bin/wine /check/graphics/probe.exe >/check/logs/graphics-observed.log 2>&1
grep -q FNA_VULKAN_LIFETIME_OK /check/logs/graphics-observed.log
grep -q VULKAN_TRACE_ACTIVE /check/logs/graphics-observed.log
MEMENTO_COLD_TRACE=1 DOTNET_STARTUP_HOOKS='Z:\check\trace-layer\Memento.FrameBudget.dll' timeout 120 /opt/wine/bin/wine /check/cold-boundaries/GraphicsBoundaryProbe.exe 'Z:\check\cold-fixture' 'Z:\check\trace-layer\shim.dll' >/check/logs/cold-boundaries.log 2>&1
grep -q GRAPHICS_BOUNDARY_OK /check/logs/cold-boundaries.log
grep -q COLD_TRACE_ACTIVE /check/logs/cold-boundaries.log
timeout 120 /opt/wine/bin/wine /check/cold-frames/ColdTraceProbe.exe enabled >/check/logs/cold-frames.log 2>&1
grep -q 'COLD_TRACE_OK mode=enabled' /check/logs/cold-frames.log
# Build the app's pinned PRoot sources/patches against Linux libc for this test.
# Android's Bionic build and device kernel still need device validation.
apt-get update -qq >/check/logs/proot-install.log 2>&1
apt-get install -y --no-install-recommends build-essential libtalloc-dev libasound2-dev gawk >>/check/logs/proot-install.log 2>&1
mkdir -p /check/audio
cc -O2 -shared -fPIC -DPIC -Wall -Wextra -Werror /check/pcm_trasc.c -lasound -o /check/audio/libasound_module_pcm_trasc.so
# All guest Linux processes are ARM64; Windows x86 is handled by FEX in Wine.
# Debian's ARM64 GCC cannot build PRoot's unused ARM32 loader via -m32.
make -C /check/proot/src -j4 HAS_LOADER_32BIT= PROOT_UNBUNDLE_LOADER=/unused >/check/logs/proot-build.log 2>&1
/opt/wine/bin/wineserver -k || true
/opt/wine/bin/wineserver -w
export WINEPREFIX=/tmp/fex-prefix-proot
# Verify both the retained compatibility mode and automatic acceleration.
export PROOT_LOADER=/check/proot/src/loader/loader PROOT_TMP_DIR=/tmp TRASC_PROOT_REPORT=1
for mode in compatibility accelerated; do
  export WINEPREFIX="/tmp/fex-prefix-$mode"
  if [ "$mode" = compatibility ]; then export PROOT_NO_SECCOMP=1; else unset PROOT_NO_SECCOMP; fi
  timeout 480 /check/proot/src/proot --kill-on-exit --sysvipc -0 -r / /bin/bash /check/proot-probes.sh >"/check/logs/proot-$mode.log" 2>&1
  if [ "$mode" = accelerated ]; then grep -q 'seccomp acceleration observed' "/check/logs/proot-$mode.log"; fi
  # Preserve diagnostics separately instead of overwriting the first result.
  mkdir -p "/check/logs/$mode"
  cp /check/logs/proot-*.log "/check/logs/$mode/"
done
echo "Windows x64 .NET 10.0.8 JIT/GC and FNA Vulkan passed on ARM64 FEX, directly and under PRoot"
PROBE
