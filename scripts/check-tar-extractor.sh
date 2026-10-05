#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
verify_dir="$(mktemp -d)"
trap 'rm -rf "$verify_dir"' EXIT
compiler=(javac)
if ! command -v javac >/dev/null; then compiler=(java -m jdk.compiler/com.sun.tools.javac.Main); fi
"${compiler[@]}" -d "$verify_dir/classes" \
  tests/tar-extractor-stubs/android/system/Os.java \
  app/src/main/java/io/github/russianranger/trasc/TarExtractor.java \
  tests/TarExtractorHostTest.java
java -cp "$verify_dir/classes" io.github.russianranger.trasc.TarExtractorHostTest
# Pass the accepted client/server archives to qualify their unchanged contents.
if [ "$#" -gt 0 ]; then
  python3 tests/verify_runtime_extraction.py "$verify_dir/classes" "$@"
fi
