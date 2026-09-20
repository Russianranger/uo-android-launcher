#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p runtime-work/readiness-test
compiler=(javac)
if ! command -v javac >/dev/null; then compiler=(java -m jdk.compiler/com.sun.tools.javac.Main); fi
"${compiler[@]}" -d runtime-work/readiness-test app/src/main/java/io/github/russianranger/trasc/ClientReadiness.java tests/ClientReadinessHostTest.java
java -cp runtime-work/readiness-test io.github.russianranger.trasc.ClientReadinessHostTest
