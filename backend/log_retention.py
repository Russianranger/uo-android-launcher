"""Bounded history for closed logs. Writers must close a log before rotating it."""
import os
from pathlib import Path
import tempfile

LIMIT = 8 * 1024**2


def count(directory):
    directory = Path(directory)
    if directory.name == 'logs' and directory.parent.name == 'server':
        directory = directory.parent.parent / 'logs'
    path = directory / 'retention-count.txt'
    try:
        if path.is_symlink() or path.stat().st_size > 16:
            return 5
        value = int(path.read_text().strip())
        return value if value in (2, 3, 4, 5) else 5
    except (OSError, ValueError):
        return 5


def history(path, index):
    return path.with_name(path.stem + ('.previous' if index == 1 else f'.previous.{index}') + '.log')


def shift(path):
    path = Path(path)
    keep = count(path.parent)
    # Only our known archive names; never follow a symlink.
    for index in range(5, 0, -1):
        old = history(path, index)
        if old.is_symlink():
            raise ValueError('Log history cannot contain a symlink')
        if not old.is_file():
            continue
        try:
            if index >= keep:
                old.unlink()
            else:
                os.replace(old, history(path, index + 1))
        except FileNotFoundError:
            # Native cleanup may have removed excess history after the user
            # lowered the limit. A missing old archive must not fail a launch.
            continue
    return history(path, 1)


def rotate(path, limit=LIMIT):
    path = Path(path)
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('Log path cannot be a symlink')
    if not path.is_file() or not path.stat().st_size:
        return
    target = shift(path)
    size = path.stat().st_size
    if size <= limit:
        os.replace(path, target)
        return
    marker = f'\n[TRASC: previous log shortened from {size} bytes; startup and final output retained]\n'.encode()
    head = limit // 2
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='log-history-', suffix='.tmp', delete=False) as out:
        temporary = Path(out.name)
        try:
            with path.open('rb') as source:
                out.write(source.read(head))
                out.write(marker)
                source.seek(-(limit - head - len(marker)), os.SEEK_END)
                out.write(source.read(limit - head - len(marker)))
            out.close()
            os.replace(temporary, target)
            path.unlink()
        finally:
            temporary.unlink(missing_ok=True)
