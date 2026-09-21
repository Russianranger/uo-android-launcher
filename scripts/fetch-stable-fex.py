"""Reuse the exact 0.2.0 runtime already validated on Thor; no translator rebuild."""
from pathlib import Path
import hashlib
import json
import subprocess

assets={
 'client-runtime-arm64.tar.gz':'f036c00a290abb953bec26be80c4d8fe492fd986e7a589c51008124432c8641e',
 'client-runtime-manifest.json':'d375adf23b621f83ef7b5fff95365312377399704abb486fd8d4164a1fe29a13',
 'wine-arm64ec-source.tar.gz':'93ffcd86d3f518934da5c93c768d43afe7e97d66f04f355d914f5cfb6731ac74',
 'fex-2510-source-with-submodules.tar.gz':'8a10a8e63cdea41a6c70b0f14d487fe4cb3f11c8fb5baba3e42090098e2745be',
}
folder=Path('runtime-work/fex/release');folder.mkdir(parents=True,exist_ok=True)
for name,digest in assets.items():
    subprocess.run(['gh','release','download','v0.2.0','--repo','Russianranger/uo-android-launcher','--pattern',name,'--dir',str(folder),'--clobber'],check=True)
    with (folder/name).open('rb') as source:actual=hashlib.file_digest(source,'sha256').hexdigest()
    if actual!=digest:raise RuntimeError('Stable FEX asset checksum failed: '+name)
manifest=json.loads((folder/'client-runtime-manifest.json').read_text())
assert manifest['sha256']==assets['client-runtime-arm64.tar.gz'] and manifest['runtime']=='fex-arm64ec-1'
print('Retained exact v0.2.0 Wine/FEX binaries and corresponding sources; SHA-256 verified')
