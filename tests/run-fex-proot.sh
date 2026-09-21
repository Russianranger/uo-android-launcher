#!/usr/bin/env bash
# One PRoot process owns Wine, services and probes, just as the Android supervisor does.
set -euo pipefail
export DISPLAY=:9
# Keep X11 and Wine in the same SysV IPC namespace, as in the app.
Xtigervnc :9 -geometry 1280x720 -depth 24 -rfbport -1 -SecurityTypes None -nolisten tcp -ac >/check/logs/proot-display.log 2>&1 &
display_pid=$!
trap '/opt/wine/bin/wineserver -k || true; kill "$display_pid" || true' EXIT
sleep 2
/bin/true
WINEDLLOVERRIDES="winemenubuilder,mshtml,mscoree=" timeout 180 /opt/wine/bin/wine wineboot -u >/check/logs/proot-prefix.log 2>&1
python3 /check/prefix-wine-probe.py >/check/logs/proot-prefix-recovery.log 2>&1
grep -q FEX_PREFIX_RECOVERY_OK /check/logs/proot-prefix-recovery.log
WINEDEBUG=-all,err+all,trace+loaddll timeout 150 /opt/wine/bin/wine /check/stress/FexProbe.exe >/check/logs/proot-stress.log 2>&1
grep -q FEX_DOTNET_STRESS_OK /check/logs/proot-stress.log
FNA3D_FORCE_DRIVER=Vulkan SDL_GPU_DRIVER=vulkan timeout 180 /opt/wine/bin/wine /check/graphics/probe.exe >/check/logs/proot-graphics.log 2>&1
grep -q FNA_VULKAN_LIFETIME_OK /check/logs/proot-graphics.log
