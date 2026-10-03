#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
work="$PWD/runtime-work/vulkan-trace"
mkdir -p "$work/logs" "$work/layer"
cc -std=c11 -O2 -Wall -Wextra -Werror tests/vulkan-layer-lifetime-probe.c -pthread -o "$work/lifetime-probe"
"$work/lifetime-probe" > "$work/logs/late-dispatch.log" 2>&1
grep -q VULKAN_LAYER_LIFETIME_OK "$work/logs/late-dispatch.log"
cc -std=c11 -O2 -Wall -Wextra -Werror tests/vulkan-correlation-probe.c -pthread -o "$work/correlation-probe"
"$work/correlation-probe" > "$work/logs/correlation.log" 2>&1
grep -q VULKAN_CORRELATION_OK "$work/logs/correlation.log"
cc -std=c11 -shared -fPIC -O2 -Wall -Wextra -Werror -Wl,-Bsymbolic native/graphics-diagnostics/layer.c -pthread -o "$work/layer/libmemento-vulkan-trace.so"
python3 - "$work" <<'PY'
from pathlib import Path
import json,sys
w=Path(sys.argv[1]);(w/'layer/trace.json').write_text(json.dumps({'file_format_version':'1.0.0','layer':{'name':'VK_LAYER_MEMENTO_cold_trace','type':'GLOBAL','library_path':str(w/'layer/libmemento-vulkan-trace.so'),'api_version':'1.3.0','implementation_version':2,'description':'Memento passive timing'}}))
PY
cc -std=c11 -O2 -Wall -Wextra -Werror tests/vulkan-trace-probe.c -lvulkan -o "$work/probe"
"$work/probe" > "$work/logs/original.log" 2>&1
VK_LAYER_PATH="$work/layer" VK_INSTANCE_LAYERS=VK_LAYER_MEMENTO_cold_trace "$work/probe" > "$work/logs/observed.log" 2>&1
"$work/probe" slow > "$work/logs/timeout-original.log" 2>&1
VK_LAYER_PATH="$work/layer" VK_INSTANCE_LAYERS=VK_LAYER_MEMENTO_cold_trace "$work/probe" slow > "$work/logs/timeout-observed.log" 2>&1
grep -q VULKAN_TRACE_GPU_OK "$work/logs/original.log"
grep -q VULKAN_TRACE_GPU_OK "$work/logs/observed.log"
grep -q VULKAN_TRACE_ACTIVE "$work/logs/observed.log"
for operation in vkCreateShaderModule vkCreateComputePipelines vkCreateBuffer vkCreateImage vkCmdCopyBufferToImage vkAllocateMemory vkMapMemory vkQueueSubmit vkWaitForFences; do
  grep -q "op=$operation " "$work/logs/observed.log"
done
grep -q VULKAN_TRACE_TIMEOUT_OK "$work/logs/timeout-original.log"
grep -q VULKAN_TRACE_TIMEOUT_OK "$work/logs/timeout-observed.log"
python3 - "$work" <<'PY'
from pathlib import Path
import sys
lines=(Path(sys.argv[1])/'logs/timeout-observed.log').read_text().splitlines()
slow=[dict(item.split('=',1) for item in line.split()[1:]) for line in lines if line.startswith('VULKAN_CALL ')]
assert len(slow)==8,slow
assert all(s['op']=='vkWaitForFences' and s['result']=='2' and float(s['wall_ms'])>=50 and float(s['thread_cpu_ms'])<float(s['wall_ms']) for s in slow),slow
assert any('slow_records_suppressed=4' in s for s in lines),lines
assert any('image_2048_square_creates=1' in s for s in lines),lines
assert any('op=vkWaitForFences calls=14 ' in s for s in lines),lines
assert all(':reset_unattributed:' in s['fences'] and s['device_id']!='0' and s['refs_omitted']=='0' for s in slow),slow
assert all(float(s['metadata_ms'])<float(s['wall_ms']) for s in slow),slow
correlation=(Path(sys.argv[1])/'logs/correlation.log').read_text().splitlines()
record=[dict(item.split('=',1) for item in line.split()[1:]) for line in correlation if line.startswith('VULKAN_CALL ')]
assert len(record)==1 and record[0]['op']=='vkWaitForFences' and record[0]['result']=='2',record
r=record[0]
assert ':submit:1:' in r['fences'] and r['missing_refs']=='0',r
source=r['fence_submit_evidence'].split(':')
assert source[1:4]==['1','1','1'] and source[9:13]==['2048','2048','0','0'],source
assert float(r['wall_ms'])>=50 and float(r['metadata_ms'])<float(r['wall_ms']),r
print('VULKAN_TRACE_BOUNDED_OK result_preserved=true wait_vs_cpu=true all_calls_counted=true')
PY
echo VULKAN_TRACE_LIFETIME_OK
echo VULKAN_TRACE_CORRELATION_OK
