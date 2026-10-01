#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p runtime-work/presentation-test
probe="$PWD/runtime-work/presentation-test"
bridge="${1:-$probe/x11-frame-bridge}"
if [ "$#" -eq 0 ]; then
  cc -std=c11 -O2 -Wall -Wextra -Werror native/presentation/x11-frame-bridge.c -lXdamage -lXtst -lX11 -lXext -lXfixes -o "$bridge"
fi
bridge=$(realpath "$bridge")
cc -std=c11 -O2 -Wall -Wextra -Werror tests/presentation-cache-probe.c -lX11 -lXfixes -o "$probe/probe"
export DISPLAY=:91
Xtigervnc "$DISPLAY" -geometry 1280x720 -depth 24 -SecurityTypes None -localhost -rfbport -1 > "$probe/xserver.log" 2>&1 &
xserver=$!
trap 'kill "$xserver" 2>/dev/null || true' EXIT
for attempt in $(seq 1 100); do
  if xrandr >/dev/null 2>&1; then break; fi
  sleep .05
done
for mode in shared fallback; do
  for transport in full regions; do
    fps=30
    if [ "$mode-$transport" = fallback-regions ]; then fps=60; fi
    if ! timeout 30 "$probe/probe" "$bridge" "$probe/frame.sock" "$mode" "$transport" "$fps" 2> "$probe/$mode-$transport.log"; then
      cat "$probe/$mode-$transport.log" "$probe/xserver.log"; exit 1
    fi
    cat "$probe/$mode-$transport.log"
  done
done
python3 - <<'PY'
import json,pathlib
for mode in ('shared-full','shared-regions','fallback-full','fallback-regions'):
    reports=[json.loads(x) for x in pathlib.Path(f'runtime-work/presentation-test/{mode}.log').read_text().splitlines() if x.startswith('{')]
    assert reports, mode
    totals={key:sum(r[key] for r in reports) for key in ('requests','window_queries','cursor_queries','pointer_queries')}
    assert totals['requests']>=25, totals
    assert totals['window_queries']<totals['requests']//2, totals
    assert totals['cursor_queries']<totals['requests']//2, totals
    assert totals['pointer_queries']==totals['requests'], totals
    frames={key:sum(r[key] for r in reports) for key in ('region_frames','pixel_bytes','full_frame_bytes')}
    if mode.endswith('regions'):
        assert frames['region_frames']>=4 and frames['pixel_bytes']<frames['full_frame_bytes'], frames
    else:
        assert frames['region_frames']==0 and frames['pixel_bytes']==frames['full_frame_bytes'], frames
    print('CACHED_X11_QUERIES_OK',mode,totals)
    print('CHANGED_FRAME_DELIVERY_OK',mode,frames)
PY
