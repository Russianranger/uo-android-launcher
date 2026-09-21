#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p runtime-work/audio-test
compiler=(javac)
if ! command -v javac >/dev/null; then compiler=(java -m jdk.compiler/com.sun.tools.javac.Main); fi
"${compiler[@]}" -d runtime-work/audio-test app/src/main/java/io/github/russianranger/trasc/AudioBufferPolicy.java tests/AudioPolicyHostTest.java
java -cp runtime-work/audio-test io.github.russianranger.trasc.AudioPolicyHostTest
"${compiler[@]}" -d runtime-work/audio-test app/src/main/java/io/github/russianranger/trasc/AudioPcmSession.java app/src/main/java/io/github/russianranger/trasc/AudioDeliveryStats.java tests/AudioDeliveryHostTest.java
java -cp runtime-work/audio-test io.github.russianranger.trasc.AudioDeliveryHostTest
"${compiler[@]}" -d runtime-work/audio-test app/src/main/java/io/github/russianranger/trasc/AudioPcmSession.java tests/AudioTransportHostTest.java
java -cp runtime-work/audio-test io.github.russianranger.trasc.AudioTransportHostTest
