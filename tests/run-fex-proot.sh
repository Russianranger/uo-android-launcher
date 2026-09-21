#!/usr/bin/env bash
# One PRoot process owns Wine, services and probes, just as the Android supervisor does.
set -euo pipefail
trap '/opt/wine/bin/wineserver -k || true' EXIT
/bin/true
WINEDLLOVERRIDES="winemenubuilder,mshtml,mscoree=" timeout 180 /opt/wine/bin/wine wineboot -u >/check/logs/proot-prefix.log 2>&1
WINEDEBUG=-all,err+all,trace+loaddll timeout 150 /opt/wine/bin/wine /check/stress/FexProbe.exe >/check/logs/proot-stress.log 2>&1
grep -q FEX_DOTNET_STRESS_OK /check/logs/proot-stress.log
FNA3D_FORCE_DRIVER=Vulkan SDL_GPU_DRIVER=vulkan timeout 180 /opt/wine/bin/wine /check/graphics/probe.exe >/check/logs/proot-graphics.log 2>&1
grep -q FNA_VULKAN_LIFETIME_OK /check/logs/proot-graphics.log
