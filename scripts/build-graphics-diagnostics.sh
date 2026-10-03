#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backend-assets
docker build --platform linux/arm64 -t memento-graphics-diagnostics:1 native/graphics-diagnostics
trace_container=$(docker create memento-graphics-diagnostics:1)
trap 'docker rm -f "$trace_container" >/dev/null 2>&1 || true' EXIT
docker cp "$trace_container:/out/libmemento-vulkan-trace.so" backend-assets/
docker cp "$trace_container:/out/vulkan-trace-notices.txt" backend-assets/
python3 - <<'PY'
from pathlib import Path
import hashlib,json
p=Path('backend-assets/libmemento-vulkan-trace.so')
p.with_name('vulkan-trace-bundle.json').write_text(json.dumps({'format':1,'revision':1,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})+'\n')
PY
