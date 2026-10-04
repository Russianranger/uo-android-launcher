"""Compare actual vendor chunk outputs across unwrapped and diagnostic bodies."""
from pathlib import Path
import re
import sys


def qualify(text, mode):
    for marker in ('RESOURCE_TRACE_OK', 'RESOURCE_STARTUP_READS_OK',
                   'RESOURCE_STARTUP_ASSETS_OK', 'CHUNK_VENDOR_OK'):
        assert marker + ' mode=' + mode in text, (marker, mode)
    assert 'jit_all_scopes=32' in text
    match = re.search(r'^CHUNK_VENDOR_OK .* fingerprint=([0-9a-f]{64})$', text, re.M)
    assert match, 'Missing actual vendor chunk fingerprint'
    if mode == 'enabled':
        assert 'COLD_TRACE_ACTIVE revision=4' in text
        assert 'CHUNK_ACCOUNTING_OK ' in text
        assert 'CHUNK_LOAD ' in text
        for proof in ('nested=true', 'thread_local=true', 'depth_caps=true',
                      'independent_parent_budget=true', 'suppressed_peak=true',
                      'deferred=true', 'warm_allocation_free=true', 'cpu_queries=false'):
            assert proof in text, proof
    else:
        assert 'COLD_TRACE_ACTIVE ' not in text
        assert 'CHUNK_LOAD ' not in text and 'CHUNK_WINDOW ' not in text
    return match.group(1)


def compare(base, disabled, enabled):
    fingerprints = (qualify(base, 'disabled'), qualify(disabled, 'disabled'),
                    qualify(enabled, 'enabled'))
    assert len(set(fingerprints)) == 1, ('Vendor chunk result changed', fingerprints)
    print('CHUNK_BASELINE_EQUIVALENCE_OK actual_vendor_bodies=true '
          'base_disabled=patched_disabled=patched_enabled fingerprint=' + fingerprints[0])


if __name__ == '__main__':
    assert len(sys.argv) == 4, 'base-disabled.log patched-disabled.log patched-enabled.log'
    compare(*(Path(path).read_text(errors='replace') for path in sys.argv[1:]))
