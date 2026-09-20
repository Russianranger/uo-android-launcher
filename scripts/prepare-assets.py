"""Restore pinned prebuilt Android bridges and DXVK without committing binaries."""
from pathlib import Path
import hashlib
import io
import tarfile
import urllib.error
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'runtime-work/downloads'
CACHE.mkdir(parents=True,exist_ok=True)

def fetch(name,urls,digest):
    path=CACHE/name
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==digest:return path
    for url in urls:
        try:
            with urllib.request.urlopen(url,timeout=90) as source,path.open('wb') as out:
                import shutil
                shutil.copyfileobj(source,out)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('Checksum mismatch for '+name)
            return path
        except urllib.error.HTTPError as error:
            if error.code!=404:raise
    raise RuntimeError('Pinned asset unavailable: '+name)

apk=fetch('runtime-bridges.zip',[
    'https://github.com/Russianranger/uo-android-launcher/releases/download/v0.1.0/runtime-bridges.zip',
    'https://github.com/Russianranger/trasc-server-android/releases/download/preview/trasc-server-android-preview.apk'],
    'c5d0d6e2680039dcc1e035b2adb93b4569a1da5d8d2f0ec3c4646b2e793673aa')
assets=['x11-frame-bridge','presentation-bundle.json','libasound_module_pcm_trasc.so','audio-bundle.json','turnip-26.0.0.so','presentation-notices.txt']
with zipfile.ZipFile(apk) as z:
    for name in ['libproot.so','libproot-loader.so','libvirgl-server.so','libtrasc-presentation.so']:
        target=ROOT/'app/src/main/jniLibs/arm64-v8a'/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(z.read('lib/arm64-v8a/'+name))
    for name in assets:
        target=ROOT/'backend-assets'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read('assets/'+name))
dxvk=fetch('dxvk-2.7.1.tar.gz',['https://github.com/doitsujin/dxvk/releases/download/v2.7.1/dxvk-2.7.1.tar.gz'],
           'd85ce7c79f57ecd765aaa1b9e7007cb875e6fde9f6d331df799bce73d513ce87')
with tarfile.open(dxvk) as archive:
    for arch,folder in [('x86','x32'),('x64','x64')]:
        for dll in ['d3d11','dxgi']:
            target=ROOT/'backend-assets'/f'dxvk-{dll}-{arch}.dll'
            target.write_bytes(archive.extractfile(f'dxvk-2.7.1/{folder}/{dll}.dll').read())
print('Verified and prepared Android runtime bridges, Turnip 26 and DXVK 2.7.1')
