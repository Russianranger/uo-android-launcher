"""Fetch the two checksum-pinned native DLLs used to gate atlas preparation."""
from pathlib import Path
import importlib.util
import sys

spec = importlib.util.spec_from_file_location('music_fixture', Path(__file__).with_name('fetch-music-fixture.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
# The pinned Memento ZIP stores native x64 libraries below the managed client
# directory. Keep the bounded RemoteZip range reader and checksum validation.
fixture.FOLDER += 'x64/'
fixture.FILES = {
    'FNA3D.dll': '93ca16fb415438830bd1591ac25fabb92a2b532cb629b215c8bd7d73ca806eb8',
    'SDL3.dll': 'f53fbe656b784365dc1db0de61958a51a41b5923ab9623bf2f7af4eca9649c09',
}
fixture.fetch(Path(sys.argv[1] if len(sys.argv) > 1 else 'runtime-work/music-fixture/original'))
