#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ${1:-} == android ]]; then
    llvm="${ANDROID_HOME:?}/ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64/bin"
    mkdir -p app/src/main/jniLibs/arm64-v8a
    "$llvm/aarch64-linux-android26-clang" -shared -fPIC -O2 -Wall -Wextra -Werror native/presentation/android-surface.c -landroid -o app/src/main/jniLibs/arm64-v8a/libtrasc-presentation.so
else
    mkdir -p backend-assets
    docker build --platform linux/arm64 -t trasc-presentation:1 native/presentation
    frame_container=$(docker create trasc-presentation:1)
    trap 'docker rm -f "$frame_container" >/dev/null 2>&1 || true' EXIT
    docker cp "$frame_container:/out/x11-frame-bridge" backend-assets/
    docker cp "$frame_container:/out/presentation-notices.txt" backend-assets/
    python3 - <<'PY'
import pathlib,hashlib,json
p=pathlib.Path('backend-assets/x11-frame-bridge')
p.with_name('presentation-bundle.json').write_text(json.dumps({'format':1,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})+'\n')
PY
fi
