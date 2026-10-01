"""Archive inventory is independent of transient backend jobs."""
from pathlib import Path
import re

from uo_content import confined


BACKUP_NAME = re.compile(r'memento-world-[0-9]+\.zip')


def backup_file(work, name):
    if not isinstance(name, str) or not BACKUP_NAME.fullmatch(name):
        raise ValueError('Select a save-data backup from the list')
    path = confined(Path(work) / 'exports', name)
    if path.is_symlink() or not path.is_file():
        raise ValueError('This backup is no longer available')
    return path


def backup_files(work):
    root = Path(work) / 'exports'
    return sorted((p for p in root.iterdir() if BACKUP_NAME.fullmatch(p.name)
                   and not p.is_symlink() and p.is_file()),
                  key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)


def delete_backup(work, name):
    path = backup_file(work, name)
    path.unlink()
    for prefix in ('metadata-', 'exported-'):
        (Path(work) / 'backups' / (prefix + name + '.json')).unlink(missing_ok=True)
