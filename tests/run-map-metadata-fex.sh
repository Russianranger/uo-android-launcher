#!/usr/bin/env bash
# Run inside retained ARM64 Wine/FEX, either directly or its PRoot supervisor.
set -euo pipefail
prefix="${1:?Pass the log filename prefix}"
[[ "$prefix" =~ ^[a-z0-9-]+$ ]]
logs=()
for variant in ordinary ordinary-render resource resource-render; do
  modes=(disabled)
  if [[ "$variant" == resource* ]]; then modes=(enabled disabled); fi
  for policy in baseline optimized; do
    if [ "$policy" = optimized ]; then folder="patched-$variant"; else folder="base-$variant"; fi
    for mode in "${modes[@]}"; do
      if [ "$mode" = enabled ]; then cold_enabled=1; else cold_enabled=0; fi
      log="/check/logs/$prefix-$variant-$policy-$mode.log"
      fixture="Z:\\check\\map-metadata-fixture\\$folder"
      MEMENTO_COLD_TRACE="$cold_enabled" DOTNET_STARTUP_HOOKS='Z:\check\trace-layer\Memento.FrameBudget.dll' \
        timeout 120 /opt/wine/bin/wine /check/map-metadata-probe/MapMetadataProbe.exe "$fixture" "$mode" "$policy" >"$log" 2>&1
      grep -q "MAP_METADATA_PROBE_OK mode=$mode optimization=$policy jit_vendor_boundaries=2" "$log"
      grep -q "MAP_METADATA_VENDOR_OK optimization=$policy mode=$mode" "$log"
      if [ "$policy" = optimized ]; then grep -q MAP_METADATA_LIFETIME_OK "$log"; fi
      logs+=("$log")
    done
  done
done
test "${#logs[@]}" = 12
python3 /check/compare_map_metadata_runtime.py "${logs[@]}"
echo "MAP_METADATA_FEX_MATRIX_OK prefix=$prefix cases=${#logs[@]}"
