#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test "$(uname -m)" = aarch64
probe="$PWD/runtime-work/box64-return"
mkdir -p "$probe/logs"
git clone https://github.com/ptitSeb/box64.git "$probe/source"
git -C "$probe/source" checkout 2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a
cmake -S "$probe/source" -B "$probe/build" -DARM_DYNAREC=ON -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build "$probe/build" -j 4 > "$probe/logs/build.log" 2>&1
x86_64-linux-gnu-gcc -O2 -fno-omit-frame-pointer -Wall -Wextra -Werror \
    tests/box64-jit-return.c -o "$probe/jit-return"
printf '[jit-return]\nBOX64_MAXCPU=0\n' > "$probe/box64.rc"
export BOX64_RCFILE="$probe/box64.rc" BOX64_LOG=1 BOX64_DYNAREC_BIGBLOCK=0
export BOX64_DYNAREC_STRONGMEM=1 BOX64_DYNAREC_WEAKBARRIER=1 BOX64_DYNAREC_SAFEFLAGS=2
export BOX64_LD_LIBRARY_PATH=/usr/x86_64-linux-gnu/lib
# Stock mode is an observation, not a required failure: reuse timing differs
# between runs. Keep its complete output and outcome as a negative comparison.
set +e
timeout 120 env BOX64_DYNAREC_CALLRET=2 "$probe/build/box64" "$probe/jit-return" > "$probe/logs/stock.log" 2>&1
stock=$?
set -e
printf 'Stock CALLRET=2 exit=%s\n' "$stock" | tee "$probe/logs/comparison.txt"
if ! timeout 120 env BOX64_DYNAREC_CALLRET=0 "$probe/build/box64" "$probe/jit-return" > "$probe/logs/workaround.log" 2>&1; then
    cat "$probe/logs/workaround.log"; exit 1
fi
cat "$probe/logs/workaround.log"
grep -q 'BOX64_JIT_RETURN_OK' "$probe/logs/workaround.log"
