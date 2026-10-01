#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p runtime-work/presentation-test
jdk="${MEMENTO_JNI_ROOT:-${JAVA_HOME:-$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")}}"
cc -std=c11 -O2 -Wall -Wextra -Werror -I"$jdk/include" -I"$jdk/include/linux" -Itests/native-surface-stubs tests/presentation-surface-probe.c -o runtime-work/presentation-test/surface-probe
runtime-work/presentation-test/surface-probe
