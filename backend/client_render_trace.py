"""Reversible, exact-hash diagnostic instrumentation. This is not a crash fix."""
import base64
import bz2
import hashlib
import os
from pathlib import Path
import tempfile

from client_graphics import digest
from uo_content import confined

ORIGINAL = 'b04066be1b1b475ca00e6982a980e2dd11b93abede00c79c68bde566bdcf947e'
INSTRUMENTED = '0dd83f1af66262f51871ab5eecf4e8a1da5798e5de3c4a5eb4b87f4a4dd8e305'
FNA = '399c91458ccbd08bcd8094bde39a1091f5edd545fd77a9b4579016e7ac5498c6'
PATCH = 'tazuo-5.2-render-trace.patch.b64'
HELPER = 'Memento.RenderTrace.dll'
BACKUP = 'TazUO.dll.before-memento-render-trace'
LIMIT = 16 * 1024 * 1024


def number(data):
    if len(data) != 8:raise ValueError('Incomplete render diagnostic delta')
    value = int.from_bytes(data, 'little')
    return -(value & ((1 << 63) - 1)) if value >> 63 else value


def unpack(data):
    decoder = bz2.BZ2Decompressor()
    result = decoder.decompress(data, max_length=LIMIT + 1)
    if len(result) > LIMIT or not decoder.eof or decoder.unused_data:
        raise ValueError('Invalid render diagnostic delta section')
    return result


def apply_delta(original, patch):
    if len(original) > LIMIT or len(patch) > LIMIT or patch[:8] != b'BSDIFF40':
        raise ValueError('Invalid render diagnostic delta')
    controls, differences, size = (number(patch[i:i+8]) for i in (8, 16, 24))
    if min(controls, differences, size) < 0 or size > LIMIT or 32 + controls + differences > len(patch):
        raise ValueError('Invalid render diagnostic delta lengths')
    control = unpack(patch[32:32+controls])
    diff = unpack(patch[32+controls:32+controls+differences])
    extra = unpack(patch[32+controls+differences:])
    output = bytearray(size)
    src = dst = dp = ep = cp = 0
    while dst < size:
        if cp + 24 > len(control):raise ValueError('Incomplete render diagnostic controls')
        add, copy, seek = (number(control[cp+i:cp+i+8]) for i in (0, 8, 16));cp += 24
        if min(add, copy) < 0 or dst + add + copy > size or dp + add > len(diff) or ep + copy > len(extra):
            raise ValueError('Invalid render diagnostic control')
        for i in range(add):
            prior = original[src+i] if 0 <= src+i < len(original) else 0
            output[dst+i] = (diff[dp+i] + prior) & 255
        dst += add;src += add;dp += add
        output[dst:dst+copy] = extra[ep:ep+copy]
        dst += copy;ep += copy;src += seek
    if (cp, dp, ep) != (len(control), len(diff), len(extra)):
        raise ValueError('Trailing render diagnostic data')
    return bytes(output)


def atomic_write(target, data, expected):
    if target.is_symlink():raise ValueError('Render diagnostic path must not be a symbolic link')
    if hashlib.sha256(data).hexdigest() != expected:raise ValueError('Render diagnostic checksum mismatch')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.memento-render-', delete=False) as stream:
            temporary = Path(stream.name);stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def prepare(root, metadata, runtime_assets, enabled):
    if not isinstance(enabled, bool):raise ValueError('Invalid render trace option')
    folder = confined(root, metadata['executable']).parent
    def library(name):
        matches = [p for p in folder.iterdir() if p.name.lower() == name.lower()]
        if len(matches) > 1:raise ValueError('Duplicate client library: ' + name)
        candidate = matches[0] if matches else folder/name
        if candidate.is_symlink():raise ValueError('Render diagnostic library must not be a symbolic link')
        return confined(root, candidate.relative_to(root))
    target, fna = library('TazUO.dll'), library('FNA.dll')
    current, fna_hash = digest(target), digest(fna)
    report = {'requested':enabled, 'diagnostic_only':True, 'before_sha256':current, 'fna_sha256':fna_hash, 'active':False}
    backup = folder/BACKUP
    if current == INSTRUMENTED and (not enabled or fna_hash != FNA):
        if backup.is_symlink() or digest(backup) != ORIGINAL:
            raise ValueError('Original TazUO diagnostic backup is missing or changed; restore TazUO.dll from the original client package')
        atomic_write(target, backup.read_bytes(), ORIGINAL)
        report['action'] = 'restored_original'
    elif enabled and current in (ORIGINAL, INSTRUMENTED) and fna_hash == FNA:
        assets = Path(runtime_assets)
        # Require the preloaded helper before committing the assembly reference.
        if not (assets/HELPER).is_file():raise ValueError('Render trace component is missing; reinstall the current APK')
        if backup.is_symlink() or (backup.exists() and digest(backup) != ORIGINAL):
            raise ValueError('Original TazUO diagnostic backup has changed')
        if current == ORIGINAL:
            original = target.read_bytes()
            raw = (assets/PATCH).read_bytes()
            if len(raw) > LIMIT:raise ValueError('Render diagnostic delta is too large')
            patched = apply_delta(original, base64.b64decode(raw.strip(), validate=True))
            if hashlib.sha256(patched).hexdigest() != INSTRUMENTED:
                raise ValueError('Render diagnostic output checksum mismatch')
            if not backup.exists():atomic_write(backup, original, ORIGINAL)
            atomic_write(target, patched, INSTRUMENTED)
            report['action'] = 'instrumented_known_client'
        else:
            if not backup.exists():raise ValueError('Original TazUO diagnostic backup is missing')
            report['action'] = 'already_instrumented'
        report['active'] = True
        report['helper_sha256'] = digest(assets/HELPER)
    else:
        report['action'] = 'unchanged_original' if not enabled else 'unchanged_unrecognized_client'
    report['active_sha256'] = digest(target)
    return report
