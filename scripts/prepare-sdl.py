"""Official SDL binary, fixed checksum, also used by the Wine graphics gate."""
from pathlib import Path
import hashlib
import urllib.request
import zipfile

root = Path(__file__).resolve().parents[1]
cache = root/'runtime-work/downloads/SDL3-3.4.16-win32-x64.zip'
cache.parent.mkdir(parents=True, exist_ok=True)
expected = '4217944b4e51457af4a59c82d883f8443b3e65964b2acd8943484c492756c4b6'
if not cache.exists() or hashlib.sha256(cache.read_bytes()).hexdigest() != expected:
    with urllib.request.urlopen('https://github.com/libsdl-org/SDL/releases/download/release-3.4.16/SDL3-3.4.16-win32-x64.zip', timeout=90) as source:
        cache.write_bytes(source.read())
if hashlib.sha256(cache.read_bytes()).hexdigest() != expected:raise ValueError('SDL download checksum mismatch')
assets = root/'backend-assets';assets.mkdir(exist_ok=True)
with zipfile.ZipFile(cache) as archive:
    (assets/'SDL3-3.4.16-x64.dll').write_bytes(archive.read('SDL3.dll'))
    (assets/'SDL3-LICENSE.txt').write_bytes(archive.read('LICENSE.txt'))
print('Verified SDL 3.4.16 x64 and its license')
