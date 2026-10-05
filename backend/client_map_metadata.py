"""Reversible, exact-client map metadata reuse within one synchronous chunk load.

This outer layer is restored before the cold diagnostic layer. Its supported
inputs include the unchanged 0.2.19 observers, so disabling this optimization
retains the previous diagnostic path without altering its deltas.
"""
import base64
import hashlib
from pathlib import Path

import client_frame_budget as frame
import client_map_metadata_variants as variants
import client_render_trace as trace
from client_graphics import digest
from uo_content import confined

LIBRARIES = ('TazUO.dll', 'ClassicUO.Assets.dll')
BACKUP_SUFFIX = '.before-memento-map-metadata-'
SUPPORTED_IO = ('334d1932f6fefe22731cccbbd812a6761d55ffa607ff0a4a291c2bc796c78483',
                'bb86c8148cb572cd1a1623cbfac6a7215c01d803c2ac466811b5b67097acc34c')


def target(root, metadata, name):
    folder = confined(root, metadata['executable']).parent
    matches = [p for p in folder.iterdir() if p.name.lower() == name.lower()]
    if len(matches) > 1:raise ValueError('Duplicate map metadata library: '+name)
    library = matches[0] if matches else folder/name
    if library.is_symlink():raise ValueError('Map metadata library cannot be a symbolic link')
    return confined(root, library.relative_to(root))


def backup_name(library, base):
    return library.with_name(library.name + BACKUP_SUFFIX + base[:12])


def restore(root, metadata):
    """Unstack our known outputs before existing client/diagnostic preparation.

All recognized outputs are validated before the first replacement. A process
interrupted between replacements leaves recognizable outputs for the next
launch. An updated, unknown assembly is left untouched.
    """
    pending = []
    for name in LIBRARIES:
        library = target(root, metadata, name)
        current = digest(library)
        row = next((r for r in variants.VARIANTS if r[0] == name and r[2] == current), None)
        if row is None:continue
        backup = backup_name(library, row[1])
        if backup.is_symlink() or digest(backup) != row[1]:
            raise ValueError('Verified map metadata backup is missing or changed: '+name)
        data = backup.read_bytes()
        if hashlib.sha256(data).hexdigest() != row[1]:raise ValueError('Map metadata backup changed during restoration: '+name)
        pending.append((library, data, row[1]))
    for library, data, base in pending:trace.atomic_write(library, data, base)
    return bool(pending)


def prepare(root, metadata, assets, requested=True, eligible=True):
    if not isinstance(requested, bool) or not isinstance(eligible, bool):
        raise ValueError('Invalid map metadata cache option')
    io_hash = digest(target(root, metadata, 'ClassicUO.IO.dll'))
    report = {'requested':requested, 'active':False, 'revision':1, 'io_sha256':io_hash,
              'lifetime':'chunk_load_call', 'max_readers':16, 'max_depth':8}
    if not requested or not eligible:
        restored = restore(root, metadata)
        return dict(report, action='restored_previous' if restored else 'disabled' if not requested else 'unsupported')
    # The cache admission observes FileReader's exact backing-stream lifetime;
    # an unrelated client IO implementation must never inherit those semantics.
    if io_hash not in SUPPORTED_IO:
        return dict(report, action='unsupported', reason='Unrecognized map file reader library')
    selected = []
    before = {}
    for name in LIBRARIES:
        library = target(root, metadata, name)
        current = digest(library)
        before[name] = current
        row = next((r for r in variants.VARIANTS if r[0] == name and current in (r[1], r[2])), None)
        if row is None:
            return dict(report, action='unchanged_unrecognized_client', before_sha256=before)
        backup = backup_name(library, row[1])
        if backup.is_symlink() or (backup.exists() and digest(backup) != row[1]):
            raise ValueError('Verified map metadata backup has changed: '+name)
        if current == row[2] and digest(backup) != row[1]:
            raise ValueError('Verified map metadata backup is missing: '+name)
        selected.append((library, row, backup, current))
    assets = Path(assets)
    if not (assets/frame.HELPER).is_file():raise ValueError('Map metadata component is missing; reinstall the current APK')
    pending = []
    for library, row, backup, current in selected:
        name, base, optimized, patch = row
        if current == optimized:continue
        original = library.read_bytes()
        if hashlib.sha256(original).hexdigest() != base:raise ValueError('Map metadata input changed during preparation: '+name)
        raw = (assets/patch).read_bytes()
        if len(raw) > trace.LIMIT:raise ValueError('Map metadata delta is too large')
        updated = trace.apply_delta(original, base64.b64decode(raw.strip(), validate=True))
        if hashlib.sha256(updated).hexdigest() != optimized:
            raise ValueError('Map metadata output checksum mismatch: '+name)
        pending.append((library, backup, original, base, updated, optimized))
    # Preserve the complete verified inputs before replacing either assembly.
    for library, backup, original, base, updated, optimized in pending:
        if not backup.exists():trace.atomic_write(backup, original, base)
    for library, backup, original, base, updated, optimized in pending:
        trace.atomic_write(library, updated, optimized)
    return dict(report, active=True, action='cached_known_client' if pending else 'already_active',
                before_sha256=before, active_sha256={name:digest(target(root,metadata,name)) for name in LIBRARIES},
                helper_sha256=digest(assets/frame.HELPER))
