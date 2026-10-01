"""Portable Memento player data: Info, Saves and Backups, never server files."""
import json
from pathlib import Path
import stat
import zipfile

from uo_content import MAX_BYTES, confined, extract_zip


SAVE_FOLDERS = ('Info', 'Saves', 'Backups')
_FOLDER_NAMES = {name.casefold(): name for name in SAVE_FOLDERS}
_LEGACY_MARKER = 'memento-backup.json'


def inspect_save_data(archive, destination):
    """Accept a three-folder ZIP, optionally wrapped once, or an old app backup.

    Legacy Data entries are checked for unsafe paths but are never extracted.
    The selected output always uses Memento's canonical folder capitalization.
    """
    destination = Path(destination)
    with zipfile.ZipFile(archive) as z:
        entries = []
        members = z.infolist()
        if len(members) > 250000 or sum(item.file_size for item in members) > MAX_BYTES:
            raise ValueError('Archive exceeds import limits')
        seen = set()
        for item in members:
            path = confined(destination, item.filename)
            parts = path.relative_to(destination.resolve()).parts
            key = '/'.join(parts).casefold()
            if key in seen:
                raise ValueError('Duplicate or case-conflicting archive entry: ' + item.filename)
            seen.add(key)
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError('Links and special files are not supported in imports')
            if not parts:
                if item.is_dir():
                    continue
                raise ValueError('Invalid save data archive entry')
            entries.append((item, parts))
        if not entries:
            raise ValueError('Choose a ZIP containing Info, Saves and Backups')

        roots = {parts[0] for _, parts in entries}
        known = set(SAVE_FOLDERS) | {'Data', _LEGACY_MARKER}
        wrapped = len(roots) == 1 and next(iter(roots)).casefold() not in {n.casefold() for n in known}
        if wrapped:
            entries = [(item, parts[1:]) for item, parts in entries if len(parts) > 1 or not item.is_dir()]
            if any(not parts for _, parts in entries):
                raise ValueError('Save data must be inside a folder, not a file')

        marker_entries = [item for item, parts in entries if parts == (_LEGACY_MARKER,)]
        legacy = bool(marker_entries)
        if legacy:
            marker = marker_entries[0]
            if len(marker_entries) != 1 or marker.is_dir() or marker.file_size > 4096:
                raise ValueError('Invalid Memento backup metadata')
            try:
                metadata = json.loads(z.read(marker))
            except (ValueError, UnicodeError) as error:
                raise ValueError('Invalid Memento backup metadata') from error
            if not isinstance(metadata, dict) or type(metadata.get('format')) is not int or metadata['format'] != 1 or metadata.get('kind') != 'world':
                raise ValueError('Choose a supported Memento save data backup')

        selected = {}
        folder_spellings = {}
        for item, parts in entries:
            root = parts[0]
            canonical = _FOLDER_NAMES.get(root.casefold())
            if canonical:
                previous = folder_spellings.setdefault(canonical, root)
                if previous != root:
                    raise ValueError('Conflicting save folder names: ' + previous + ' and ' + root)
                if len(parts) == 1 and not item.is_dir():
                    raise ValueError(canonical + ' must be a folder')
                selected[item.filename] = '/'.join((canonical,) + parts[1:]) + ('/' if item.is_dir() else '')
            elif legacy and (root == 'Data' or parts == (_LEGACY_MARKER,)):
                continue
            else:
                raise ValueError('Only Info, Saves and Backups can be imported; unexpected content: ' + root)
        if 'Saves' not in folder_spellings:
            raise ValueError('Choose a save data ZIP containing a Saves folder')
        files = [item for item in members if item.filename in selected and not item.is_dir()]
        return {'legacy': legacy, 'member_paths': selected,
                'folders': [name for name in SAVE_FOLDERS if name in folder_spellings],
                'files': len(files), 'unpacked_bytes': sum(item.file_size for item in files)}


def extract_save_data(archive, destination):
    metadata = inspect_save_data(archive, destination)
    selected = metadata.pop('member_paths')
    extract_zip(archive, destination, member_paths=selected)
    return metadata
