"""Reversible music enumeration cache for the exact supported Assets assembly."""
import base64
import hashlib
from pathlib import Path

from client_graphics import digest
from client_render_trace import apply_delta, atomic_write, LIMIT
from uo_content import confined

ORIGINAL = '1dd53cf0eea718aefeda33fba105c9797b138188be22562b47548c310524100d'
CACHED = '84340a487aeae33c0f17ae1b20a0c8d1b54122d1e23801e5a582452c7db905c9'
LIBRARY = 'ClassicUO.Assets.dll'
BACKUP = LIBRARY + '.before-memento-music-cache'
PATCH = 'tazuo-5.2-music-cache.patch.b64'


def prepare(root, metadata, runtime_assets, enabled=True):
    if not isinstance(enabled, bool):raise ValueError('Invalid music cache option')
    folder = confined(root, metadata['executable']).parent
    matches = [p for p in folder.iterdir() if p.name.lower() == LIBRARY.lower()]
    if len(matches) > 1:raise ValueError('Duplicate music library')
    target = matches[0] if matches else folder/LIBRARY
    if target.is_symlink():raise ValueError('Music library must not be a symbolic link')
    target = confined(root, target.relative_to(root))
    current = digest(target)
    report = {'requested':enabled, 'before_sha256':current, 'active':False, 'cache_revision':1}
    backup = folder/BACKUP
    if current == CACHED and not enabled:
        if backup.is_symlink() or digest(backup) != ORIGINAL:
            raise ValueError('Original music library backup is missing or changed; restore ClassicUO.Assets.dll from the original client package')
        atomic_write(target, backup.read_bytes(), ORIGINAL)
        report['action'] = 'restored_original'
    elif enabled and current in (ORIGINAL, CACHED):
        if backup.is_symlink() or (backup.exists() and digest(backup) != ORIGINAL):
            raise ValueError('Original music library backup has changed')
        if current == ORIGINAL:
            original = target.read_bytes()
            raw = (Path(runtime_assets)/PATCH).read_bytes()
            if len(raw) > LIMIT:raise ValueError('Music cache patch is too large')
            updated = apply_delta(original, base64.b64decode(raw.strip(), validate=True))
            if hashlib.sha256(updated).hexdigest() != CACHED:raise ValueError('Music cache output checksum mismatch')
            if not backup.exists():atomic_write(backup, original, ORIGINAL)
            atomic_write(target, updated, CACHED)
            report['action'] = 'cached_known_client'
        else:
            if not backup.exists():raise ValueError('Original music library backup is missing')
            report['action'] = 'already_cached'
        report['active'] = True
    else:
        report['action'] = 'unchanged_original' if not enabled else 'unchanged_unrecognized_client'
    report['active_sha256'] = digest(target)
    return report
