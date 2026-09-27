#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p runtime-work/launch-sequence-test
compiler=(javac)
if ! command -v javac >/dev/null; then compiler=(java -m jdk.compiler/com.sun.tools.javac.Main); fi
"${compiler[@]}" -d runtime-work/launch-sequence-test \
  app/src/main/java/io/github/russianranger/trasc/SessionActions.java \
  app/src/main/java/io/github/russianranger/trasc/LaunchSequence.java \
  tests/LaunchSequenceHostTest.java
java -cp runtime-work/launch-sequence-test io.github.russianranger.trasc.LaunchSequenceHostTest
