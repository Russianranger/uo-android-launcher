#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p runtime-work/session-archive-test
compiler=(javac)
if ! command -v javac >/dev/null; then compiler=(java -m jdk.compiler/com.sun.tools.javac.Main); fi
"${compiler[@]}" -d runtime-work/session-archive-test app/src/main/java/io/github/russianranger/trasc/SessionArchive.java tests/SessionArchiveHostTest.java
java -cp runtime-work/session-archive-test io.github.russianranger.trasc.SessionArchiveHostTest
