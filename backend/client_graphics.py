"""Reversible SDL Vulkan fixes for the verified TazUO 5.2 x64 library pair.

Never replace an unknown/newer client library. Backups and replacements are
checksum checked and committed atomically before Wine starts.
"""
import hashlib
import os
from pathlib import Path
import tempfile

from uo_content import confined

ORIGINAL_SDL = 'f53fbe656b784365dc1db0de61958a51a41b5923ab9623bf2f7af4eca9649c09'
SUPPORTED_FNA = '93ca16fb415438830bd1591ac25fabb92a2b532cb629b215c8bd7d73ca806eb8'
FIXED_SDL = '1f98969319302a100931f4385e5918a0bd53ab07773040682d22e7edb54858c0'
ASSET = 'SDL3-3.4.16-x64.dll'
BACKUP = 'SDL3.dll.before-memento-3.4.16'


def digest(path):
    if not path.is_file():return None
    result = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(1024 * 1024):result.update(chunk)
    return result.hexdigest()


def atomic_copy(source, target, expected):
    if target.is_symlink():raise ValueError('Graphics library backup must not be a symbolic link')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.memento-sdl-', delete=False) as out:
            temporary = Path(out.name)
            with source.open('rb') as stream:
                while chunk := stream.read(1024 * 1024):out.write(chunk)
            out.flush();os.fsync(out.fileno())
        if digest(temporary) != expected:raise ValueError('Graphics library checksum mismatch')
        os.replace(temporary, target)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def prepare(root, metadata, runtime_assets, enabled):
    folder = confined(root, metadata['executable']).parent
    # Case-insensitive Windows imports can retain either filename spelling.
    def library(name):
        matches = [p for p in folder.iterdir() if p.name.lower() == name.lower()]
        if len(matches) > 1:raise ValueError('Duplicate graphics library: ' + name)
        return confined(root, (matches[0] if matches else folder/name).relative_to(root))
    sdl, fna = library('SDL3.dll'), library('FNA3D.dll')
    current, fna_hash = digest(sdl), digest(fna)
    report = {'requested':enabled, 'before_sha256':current, 'fna3d_sha256':fna_hash}
    backup = folder/BACKUP
    if current == FIXED_SDL and not enabled:
        if not backup.exists() and not backup.is_symlink():
            report['action'] = 'unchanged_no_original_backup'
        else:
            if backup.is_symlink() or digest(backup) != ORIGINAL_SDL:
                raise ValueError('Original SDL backup has changed; restore the original SDL3.dll from your client package')
            atomic_copy(backup, sdl, ORIGINAL_SDL)
            report['action'] = 'restored_original'
    elif enabled and current == ORIGINAL_SDL and fna_hash == SUPPORTED_FNA and metadata.get('architecture') == 'x64':
        source = Path(runtime_assets)/ASSET
        if digest(source) != FIXED_SDL:raise ValueError('Bundled SDL graphics library is missing or damaged; reinstall the current APK')
        if backup.is_symlink() or (backup.exists() and digest(backup) != ORIGINAL_SDL):
            raise ValueError('Original SDL backup has changed; keep it and restore the original client package before retrying')
        if not backup.exists():atomic_copy(sdl, backup, ORIGINAL_SDL)
        atomic_copy(source, sdl, FIXED_SDL)
        report['action'] = 'updated_known_tazuo_5.2_pair'
    elif current == FIXED_SDL:
        report['action'] = 'already_updated'
    else:
        report['action'] = 'unchanged_original' if not enabled else 'unchanged_unrecognized_libraries'
    report['active_sha256'] = digest(sdl)
    report['active_version'] = {ORIGINAL_SDL:'3.2.27 (TazUO 5.2)', FIXED_SDL:'3.4.16'}.get(report['active_sha256'], 'unrecognized')
    return report
