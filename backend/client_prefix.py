"""Recover damaged Wine registry hives without replacing the prefix or game data."""
import hashlib
import os
from pathlib import Path
import tempfile
from uo_content import confined, sync_directory

HIVES = ('system.reg', 'userdef.reg', 'user.reg')
MAX_HIVE_BYTES = 64 * 1024 * 1024
CHECKPOINT = '.memento-registry-last-good'


def checked(prefix, relative):
    path = confined(prefix, relative)
    if path.is_symlink(): raise ValueError('Wine registry recovery cannot follow symlinks')
    return path


def inspect_hive(path):
    if not path.exists(): return {'state':'missing'}
    if not path.is_file(): raise ValueError('Wine registry must be a regular file')
    size = path.stat().st_size
    if size > MAX_HIVE_BYTES: raise ValueError('Wine registry exceeds the recovery size limit; original retained')
    data = path.read_bytes()
    result = {'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()}
    # Wine's initial loader requires this header and derives architecture from
    # system.reg. A broken header can make native ARM64 Wine report win32.
    lines = data[:4096].splitlines()
    header = lines and lines[0] == b'WINE REGISTRY Version 2'
    options = []
    for line in lines[1:]:
        if line.startswith(b'['): break
        if line.startswith(b'#arch='): options.append(line)
    reason = ('empty' if not data else 'zero_filled_bytes' if b'\0' in data else
              'invalid_header' if not header else 'invalid_architecture' if options != [b'#arch=win64'] else
              'incomplete_tail' if not data.endswith(b'\n') else None)
    return dict(result, state='damaged' if reason else 'valid', reason=reason)


def inspect(prefix):
    return {name:inspect_hive(checked(prefix, name)) for name in HIVES}


def atomic_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=target.name + '.new-', dir=target.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as out, source.open('rb') as inp:
            while block := inp.read(65536): out.write(block)
            out.flush(); os.fsync(out.fileno())
        os.replace(temp, target)
        sync_directory(target.parent)
    finally:
        temp.unlink(missing_ok=True)


def recover(prefix):
    """Caller must stop this prefix's wineserver before moving/restoring hives."""
    prefix = Path(prefix).resolve()
    before = inspect(prefix)
    plans = []
    for name, state in before.items():
        if state['state'] == 'valid': continue
        backup = checked(prefix, CHECKPOINT + '/' + name)
        valid_backup = inspect_hive(backup)['state'] == 'valid'
        plans.append((name, state, backup if valid_backup else None))
    # Validate all paths before any mutation. Healthy user hives, drive_c,
    # dosdevices, imported client, profiles and realm saves are left in place.
    archive = None
    if any(state['state'] == 'damaged' for _, state, _ in plans):
        parent = checked(prefix, '.memento-registry-recovery')
        parent.mkdir(exist_ok=True)
        archive = Path(tempfile.mkdtemp(prefix='interrupted-', dir=parent))
        sync_directory(parent); sync_directory(prefix)
    actions = {}
    for name, state, backup in plans:
        target = checked(prefix, name)
        if state['state'] == 'damaged':
            # Persist exact bytes before removing them from Wine's active set.
            with target.open('rb') as source: os.fsync(source.fileno())
            os.replace(target, archive / name)
            sync_directory(archive); sync_directory(prefix)
        if backup:
            atomic_copy(backup, target)
            actions[name] = 'restored_checkpoint'
        else:
            actions[name] = 'regenerate_with_wineboot'
    return {'before':before, 'actions':actions, 'damaged_hives_preserved':archive is not None}


def checkpoint(prefix):
    """Snapshot only a complete validated set after wineserver has exited."""
    prefix = Path(prefix).resolve()
    states = inspect(prefix)
    if any(state['state'] != 'valid' for state in states.values()):
        raise RuntimeError('Wine registry repair is incomplete. Original hives and earlier backups were retained. Open client-prefix-health.json.')
    targets = {name:checked(prefix, CHECKPOINT + '/' + name) for name in HIVES}
    for name, target in targets.items(): atomic_copy(checked(prefix, name), target)
    sync_directory(prefix)
    return states
