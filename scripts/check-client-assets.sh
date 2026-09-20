#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
apk_path="${1:-app/build/outputs/apk/debug/app-debug.apk}"
mkdir -p runtime-work/client-assets-test
compiler=(javac)
if ! command -v javac >/dev/null; then compiler=(java -m jdk.compiler/com.sun.tools.javac.Main); fi
"${compiler[@]}" -d runtime-work/client-assets-test app/src/main/java/io/github/russianranger/trasc/ClientRuntimeAssets.java tests/ClientRuntimeAssetsHostTest.java
java -cp runtime-work/client-assets-test io.github.russianranger.trasc.ClientRuntimeAssetsHostTest "$apk_path"
