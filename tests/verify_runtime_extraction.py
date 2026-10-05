"""Qualify real GNU runtime archives through the Java/Android-denial extractor."""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.digest()


def qualify(classes, archive):
    # Sequential temporary roots avoid retaining several expanded runtimes.
    with tempfile.TemporaryDirectory(prefix='memento-runtime-extraction-') as tmp:
        root = Path(tmp) / 'root'
        subprocess.run(['java', '-cp', classes,
                        'io.github.russianranger.trasc.TarExtractorHostTest',
                        str(archive), str(root)], check=True)
        hardlinks = []
        symlinks = 0
        with tarfile.open(archive, 'r|gz') as stream:
            for entry in stream:
                path = root / entry.name
                if entry.issym():
                    assert path.is_symlink(), f'Symlink lost: {entry.name}'
                    assert os.readlink(path) == entry.linkname, f'Guest symlink changed: {entry.name}'
                    symlinks += 1
                elif entry.islnk():
                    hardlinks.append(entry)
                elif entry.isfile():
                    assert path.is_file() and not path.is_symlink(), f'File lost: {entry.name}'
                    assert path.stat().st_size == entry.size, f'Size changed: {entry.name}'
                    expected = 0o755 if entry.mode & 0o111 else 0o644
                    assert stat.S_IMODE(path.stat().st_mode) == expected, f'Mode changed: {entry.name}'
        for entry in hardlinks:
            path, source = root / entry.name, root / entry.linkname
            assert path.is_file() and not path.is_symlink(), f'Hardlink not materialized: {entry.name}'
            assert not os.path.samefile(path, source), f'Hardlink inode retained: {entry.name}'
            assert digest(path) == digest(source), f'Hardlink bytes changed: {entry.name}'
            assert stat.S_IMODE(path.stat().st_mode) == stat.S_IMODE(source.stat().st_mode), f'Hardlink mode changed: {entry.name}'
        print(f'PASS: {archive.name}: {len(hardlinks)} independent hardlink copies, {symlinks} preserved guest symlinks; file sizes and modes verified', flush=True)


if __name__ == '__main__':
    for archive in sys.argv[2:]:
        qualify(sys.argv[1], Path(archive).resolve())
