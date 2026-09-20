#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p runtime-work/logs-test
compiler=(javac)
if ! command -v javac >/dev/null; then compiler=(java -m jdk.compiler/com.sun.tools.javac.Main); fi
source=app/src/main/java/io/github/russianranger/trasc
"${compiler[@]}" -d runtime-work/logs-test "$source/LocalLogs.java" "$source/LogRetention.java" tests/LocalLogsHostTest.java
java -cp runtime-work/logs-test io.github.russianranger.trasc.LocalLogsHostTest
