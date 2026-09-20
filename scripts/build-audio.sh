#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backend-assets
docker build --platform linux/arm64 -f native/audio.Dockerfile -t trasc-audio:1 native
audio_container=$(docker create trasc-audio:1)
trap 'docker rm -f "$audio_container" >/dev/null 2>&1 || true' EXIT
docker cp "$audio_container:/out/libasound_module_pcm_trasc.so" backend-assets/
docker run --rm --network none -v "$PWD/tests:/tests:ro" trasc-audio:1 python3 /tests/check_audio_native.py /out/libasound_module_pcm_trasc.so
python3 - <<'PY'
import hashlib,json,pathlib,struct
p=pathlib.Path('backend-assets/libasound_module_pcm_trasc.so');data=p.read_bytes()
assert data[:5]==b'\x7fELF\x02' and struct.unpack_from('<H',data,18)[0]==183
p.with_name('audio-bundle.json').write_text(json.dumps({'protocol':1,'architecture':'arm64-glibc','sha256':hashlib.sha256(data).hexdigest()},indent=2)+'\n')
PY
