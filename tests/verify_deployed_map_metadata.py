"""Exercise exact map optimization payloads extracted from the built APK.

Supply only pinned original DLLs as fixture inputs. All previous transformation
layers, new deltas, manifests, import dependencies and helper bytes come from the
APK deployment; repository backend modules are deliberately not on sys.path.
"""
from pathlib import Path
import base64
import hashlib
import itertools
import shutil
import sys
import tempfile

deployed, original, helper = (Path(item).resolve() for item in sys.argv[1:])
sys.path.insert(0, str(deployed))
import client_map_metadata as cache
import client_map_metadata_variants as variants
import client_render_trace as trace
import client_frame_budget as frame
import client_music_cache as music
import client_cold_resources as resources

assert Path(cache.__file__).resolve().parent == deployed
assert Path(variants.__file__).resolve().parent == deployed
assert len(variants.VARIANTS) == 8
packaged_helper = (deployed / frame.HELPER).read_bytes()
assert packaged_helper == helper.read_bytes(), 'APK did not deploy its freshly built helper'
assert packaged_helper[:2] == b'MZ' and b'ChunkMetadata' in packaged_helper


def digest(data):
    return hashlib.sha256(data).hexdigest()


def patch(data, filename):
    encoded = (deployed / filename).read_bytes()
    return trace.apply_delta(data, base64.b64decode(encoded.strip(), validate=True))


# Reconstruct each existing ordinary and .19 observer input independently from
# packaged deltas. This detects a payload accidentally built against stale DLLs.
candidates = {}
for name in (*cache.LIBRARIES, 'ClassicUO.IO.dll'):
    data = (original / name).read_bytes()
    candidates[name, digest(data)] = data
taz = (original / 'TazUO.dll').read_bytes()
for delta in (frame.PATCH, frame.COMBINED_PATCH):
    data = patch(taz, delta)
    candidates['TazUO.dll', digest(data)] = data
data = patch((original / 'ClassicUO.Assets.dll').read_bytes(), music.PATCH)
candidates['ClassicUO.Assets.dll', digest(data)] = data
for name, before, after, delta in resources.VARIANTS:
    if (name, before) not in candidates:
        continue
    data = patch(candidates[name, before], delta)
    assert digest(data) == after, ('Packaged .19 observer mismatch', name, delta)
    candidates[name, after] = data

for name, before, after, delta in variants.VARIANTS:
    data = patch(candidates[name, before], delta)
    assert digest(data) == after, ('Packaged optimization mismatch', name, delta)
assert len({row[3] for row in variants.VARIANTS}) == 8
assert len({(row[0], row[1]) for row in variants.VARIANTS}) == 8

# Pair all four client and four assets inputs, including render/resource/music
# combinations. Check actual patched bytes, idempotence and rollback to .19.
client_rows = [r for r in variants.VARIANTS if r[0] == 'TazUO.dll']
asset_rows = [r for r in variants.VARIANTS if r[0] == 'ClassicUO.Assets.dll']
assert len(client_rows) == len(asset_rows) == 4
original_io = (original / 'ClassicUO.IO.dll').read_bytes()
resource_io_row = next(r for r in resources.VARIANTS if r[0] == 'ClassicUO.IO.dll')
resource_io = candidates[resource_io_row[0], resource_io_row[2]]
assert digest(original_io) in cache.SUPPORTED_IO and digest(resource_io) in cache.SUPPORTED_IO
metadata = {'executable': 'TazUO.exe'}
pairs = 0
with tempfile.TemporaryDirectory(prefix='memento-apk-map-') as temporary:
    work = Path(temporary)
    for client_row, asset_row in itertools.product(client_rows, asset_rows):
        root = work / str(pairs)
        root.mkdir()
        (root / 'TazUO.exe').write_bytes(b'pinned executable path fixture')
        inputs = {row[0]: candidates[row[0], row[1]] for row in (client_row, asset_row)}
        for name, data in inputs.items():
            (root / name).write_bytes(data)
        io_input = resource_io if '-resource' in client_row[3] else original_io
        (root / 'ClassicUO.IO.dll').write_bytes(io_input)
        report = cache.prepare(root, metadata, deployed, True, True)
        assert report['active'] and report['action'] == 'cached_known_client', report
        assert report['io_sha256'] == digest(io_input), report
        assert report['lifetime'] == 'chunk_load_call' and report['max_readers'] == 16, report
        assert report['max_depth'] == 8, report
        for name, before, after, delta in (client_row, asset_row):
            assert digest((root / name).read_bytes()) == after
            assert report['active_sha256'][name] == after
            assert cache.backup_name(root / name, before).read_bytes() == inputs[name]
        assert cache.prepare(root, metadata, deployed, True, True)['action'] == 'already_active'
        disabled = cache.prepare(root, metadata, deployed, False, True)
        assert not disabled['active'] and disabled['action'] == 'restored_previous', disabled
        assert all((root / name).read_bytes() == data for name, data in inputs.items())
        assert (root / 'ClassicUO.IO.dll').read_bytes() == io_input
        assert not cache.restore(root, metadata)
        assert not cache.prepare(root, metadata, deployed, True, False)['active']
        pairs += 1

    # A changed client must remain untouched, including the recognized assets
    # counterpart. Missing helper must be rejected before any DLL replacement.
    root = work / 'unsupported'
    root.mkdir()
    (root / 'TazUO.exe').write_bytes(b'executable path fixture')
    (root / 'ClassicUO.IO.dll').write_bytes(original_io)
    (root / 'TazUO.dll').write_bytes(b'unknown client update')
    assets_input = candidates[asset_rows[0][0], asset_rows[0][1]]
    (root / 'ClassicUO.Assets.dll').write_bytes(assets_input)
    report = cache.prepare(root, metadata, deployed, True, True)
    assert not report['active'] and report['action'] == 'unchanged_unrecognized_client', report
    assert (root / 'TazUO.dll').read_bytes() == b'unknown client update'
    assert (root / 'ClassicUO.Assets.dll').read_bytes() == assets_input
    assert not list(root.glob('*' + cache.BACKUP_SUFFIX + '*'))
    (root / 'TazUO.dll').write_bytes(candidates[client_rows[0][0], client_rows[0][1]])
    known = {name: (root / name).read_bytes() for name in cache.LIBRARIES}
    (root / 'ClassicUO.IO.dll').write_bytes(b'unknown IO implementation')
    report = cache.prepare(root, metadata, deployed, True, True)
    assert not report['active'] and report['action'] == 'unsupported', report
    assert 'Unrecognized map file reader' in report['reason'], report
    assert all((root / name).read_bytes() == data for name, data in known.items())
    assert not list(root.glob('*' + cache.BACKUP_SUFFIX + '*'))
    (root / 'ClassicUO.IO.dll').write_bytes(original_io)
    missing = work / 'missing-helper'
    missing.mkdir()
    for row in variants.VARIANTS:
        shutil.copy2(deployed / row[3], missing / row[3])
    before = {name: (root / name).read_bytes() for name in cache.LIBRARIES}
    try:
        cache.prepare(root, metadata, missing, True, True)
    except ValueError as error:
        assert 'component is missing' in str(error), error
    else:
        raise AssertionError('Missing packaged helper was accepted')
    assert all((root / name).read_bytes() == data for name, data in before.items())

print(f'DEPLOYED_MAP_METADATA_OK variants={len(variants.VARIANTS)} pairs={pairs}', flush=True)
