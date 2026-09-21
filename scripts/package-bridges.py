"""Package deployed native bridge bytes, including rebuilt audio and display endpoints."""
from pathlib import Path
import hashlib
import json
import zipfile

root=Path(__file__).resolve().parents[1]
archive=root/'runtime-work/downloads/runtime-bridges.zip'
files={f'assets/{name}':root/'backend-assets'/name for name in ('libasound_module_pcm_trasc.so','audio-bundle.json','x11-frame-bridge','presentation-bundle.json','presentation-notices.txt')}
manifest=json.loads(files['assets/audio-bundle.json'].read_text())
assert hashlib.sha256(files['assets/libasound_module_pcm_trasc.so'].read_bytes()).hexdigest()==manifest['sha256']
presentation=json.loads(files['assets/presentation-bundle.json'].read_text())
assert presentation['metadata_cache']==1
assert hashlib.sha256(files['assets/x11-frame-bridge'].read_bytes()).hexdigest()==presentation['sha256']
updated=archive.with_suffix('.new.zip')
with zipfile.ZipFile(archive) as source,zipfile.ZipFile(updated,'w',zipfile.ZIP_DEFLATED) as dest:
    if set(files)-set(source.namelist()):raise ValueError('Retained archive lacks expected bridge entries')
    for info in source.infolist():
        dest.writestr(info,files[info.filename].read_bytes() if info.filename in files else source.read(info))
updated.replace(archive)
print('Native bridge archive contains the rebuilt, checksum-verified audio and display endpoints')
