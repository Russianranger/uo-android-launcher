#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p runtime-work/input-test
compiler=(javac)
if ! command -v javac >/dev/null; then compiler=(java -m jdk.compiler/com.sun.tools.javac.Main); fi
"${compiler[@]}" -d runtime-work/input-test app/src/main/java/io/github/russianranger/trasc/ControllerInput.java tests/InputHostTest.java
java -cp runtime-work/input-test io.github.russianranger.trasc.InputHostTest
