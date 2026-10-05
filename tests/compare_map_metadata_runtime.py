"""Require equivalent real vendor chunk outputs and fewer original Length calls."""
from pathlib import Path
import sys


def record(text, marker):
    lines = [line.strip() for line in text.splitlines() if line.startswith(marker + ' ')]
    assert len(lines) == 1, (marker, len(lines), text[-16000:])
    return dict(item.split('=', 1) for item in lines[0].split()[1:] if '=' in item)


def qualify(text):
    probe = record(text, 'MAP_METADATA_PROBE_OK')
    vendor = record(text, 'MAP_METADATA_VENDOR_OK')
    counts = record(text, 'MAP_METADATA_COUNTS')
    policy, mode = probe['optimization'], probe['mode']
    assert policy in ('baseline', 'optimized') and mode in ('enabled', 'disabled'), probe
    assert probe['jit_vendor_boundaries'] == '2' and probe['startup_getter_unchanged'] == 'true', probe
    assert probe['cpu_queries'] == 'false', probe
    assert vendor['optimization'] == policy and vendor['mode'] == mode, vendor
    for field in ('actual_chunk_load', 'actual_tile_z', 'actual_sanitize', 'actual_live_length',
                  'map0_map1', 'null_empty_fallback', 'original_out', 'original_exceptions'):
        assert vendor[field] == 'true', (field, vendor)
    assert vendor['land'] == '64' and vendor['statics'] == '1', vendor
    fingerprint = vendor['fingerprint']
    assert len(fingerprint) == 64 and all(c in '0123456789abcdef' for c in fingerprint), vendor
    assert counts['optimization'] == policy and counts['map1_sanitizations'] == '705', counts
    assert counts['reader_identities'] == '3', counts
    assert counts['map1_original_length_calls'] == ('3' if policy == 'optimized' else '2115'), counts
    if policy == 'optimized':
        lifetime = record(text, 'MAP_METADATA_LIFETIME_OK')
        for field in ('nested', 'thread_local', 'current_chunk_snapshot', 'refresh_next_chunk',
                      'reader_replacement', 'disposed_current_chunk_exception', 'failed_getter_uncached',
                      'bounded_capacity', 'warm_allocation_free', 'refs_cleared', 'unknown_shape_pass_through'):
            assert lifetime[field] == 'true', (field, lifetime)
    return policy, mode, fingerprint


def compare(outputs):
    rows = [qualify(output) for output in outputs]
    assert len(rows) >= 2, 'Supply at least baseline and optimized probe outputs'
    assert {row[0] for row in rows} == {'baseline', 'optimized'}, rows
    assert len({row[2] for row in rows}) == 1, ('Vendor chunk output changed', rows)
    if len(rows) > 2:
        assert {(row[0], row[1]) for row in rows} == {
            ('baseline', 'disabled'), ('baseline', 'enabled'),
            ('optimized', 'disabled'), ('optimized', 'enabled')}, rows
    print('MAP_METADATA_COMPARE_OK outputs=' + str(len(rows)) +
          ' fingerprint=' + rows[0][2] + ' original_length_calls=2115->3', flush=True)


if __name__ == '__main__':
    compare([Path(path).read_text(errors='replace') for path in sys.argv[1:]])
