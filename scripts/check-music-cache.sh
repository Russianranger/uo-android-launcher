#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
work="$PWD/runtime-work/music-fixture"
mkdir -p "$work/logs" "$work/patched"
python3 scripts/fetch-music-fixture.py "$work/original"
dotnet run --project diagnostics/music-patcher/MusicPatcher.csproj -- "$work/original/ClassicUO.Assets.dll" "$work/regenerated.dll"
dotnet run --project diagnostics/render-verify/RenderVerify.csproj -- "$work/original/ClassicUO.Assets.dll" "$work/regenerated.dll" --music
python3 - <<'PY'
from pathlib import Path
import shutil,sys
sys.path.insert(0,'backend')
import client_music_cache as music
work=Path('runtime-work/music-fixture').resolve()
for p in (work/'original').glob('*.dll'):shutil.copy2(p,work/'patched'/p.name)
metadata={'executable':'TazUO.exe'}
report=music.prepare(work/'patched',metadata,Path('backend'))
assert report['active'] and report['action']=='cached_known_client',report
assert (work/'patched'/music.LIBRARY).read_bytes()==(work/'regenerated.dll').read_bytes()
assert music.prepare(work/'patched',metadata,Path('backend'))['action']=='already_cached'
print('PRODUCTION_MUSIC_DELTA_OK')
PY
dotnet run --project tests/music-probe/MusicProbe.csproj -- "$work/original" "$work/patched"
dotnet publish tests/music-probe/MusicProbe.csproj -c Release -r win-x64 --self-contained true -p:RuntimeFrameworkVersion=10.0.8 -o "$work/probe" --nologo
export WINEPREFIX="$PWD/runtime-work/dotnet-wine/prefix" WINEDEBUG=-all
export WINEDLLOVERRIDES='winemenubuilder,mshtml=;mscoree=b'
xvfb-run -a python3 tests/verify_music_wine.py "$work" "$PWD/runtime-work/dotnet-wine/wine/bin/wine" > "$work/logs/wine.log" 2>&1 || { cat "$work/logs/wine.log"; exit 1; }
cat "$work/logs/wine.log"
python3 - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0,'backend')
import client_music_cache as music
root=Path('runtime-work/music-fixture/patched').resolve()
assert music.prepare(root,{'executable':'TazUO.exe'},Path('backend'),False)['action']=='restored_original'
assert (root/music.LIBRARY).read_bytes()==Path('runtime-work/music-fixture/original',music.LIBRARY).read_bytes()
print('PRODUCTION_MUSIC_RESTORE_OK')
PY
