"""Reversible exact-client atlas upload batching; preserve unknown binaries."""
import base64
import hashlib
from pathlib import Path

import client_render_trace as trace
from client_graphics import digest, ORIGINAL_SDL, FIXED_SDL, SUPPORTED_FNA
from uo_content import confined

HELPER = 'Memento.AtlasUploads.dll'
FNA_ORIGINAL = '399c91458ccbd08bcd8094bde39a1091f5edd545fd77a9b4579016e7ac5498c6'
RENDERER_ORIGINAL = '52068cb6033327f6d3683acd0fe89c5e4d61c33ea694395ec207a7ef8599c171'
UTILITY = '209db31075fbe310bbe5f827ef62cf3419eef50b77b4be351d8387eda72f62b3'
FNA_PATCHED = 'd295aab6eac90d404f4b8a584785545688c72e63a855c7bba492947814f6e61b'
RENDERER_PATCHED = '1b0c7d0e7bcbf4f54e9d9c7f7229aa33d1ac84c9cdb40ebe4b45d2419676e906'
FNA_PATCH = 'tazuo-5.2-atlas-fna.patch.b64'
RENDERER_PATCH = 'tazuo-5.2-atlas-renderer.patch.b64'
BACKUP_SUFFIX = '.before-memento-atlas-uploads'


def supported_fna(folder, current):
    if current == FNA_ORIGINAL:
        return True
    if current != FNA_PATCHED:
        return False
    backup = next((p for p in Path(folder).iterdir() if p.name.lower() == 'fna.dll' + BACKUP_SUFFIX), None)
    if backup is None or backup.is_symlink() or digest(backup) != FNA_ORIGINAL:
        raise ValueError('Original atlas FNA backup is missing or changed')
    return True


def prepare(root, metadata, runtime_assets, enabled):
    if not isinstance(enabled, bool):
        raise ValueError('Invalid atlas upload batching option')
    import client_frame_budget as frame
    folder = confined(root, metadata['executable']).parent

    def library(name):
        matches = [p for p in folder.iterdir() if p.name.lower() == name.lower()]
        if len(matches) > 1:
            raise ValueError('Duplicate client library: ' + name)
        target = matches[0] if matches else folder / name
        if target.is_symlink():
            raise ValueError('Atlas library must not be a symbolic link')
        return confined(root, target.relative_to(root))

    fna, renderer = library('FNA.dll'), library('ClassicUO.Renderer.dll')
    entries = [(fna, FNA_ORIGINAL, FNA_PATCHED, FNA_PATCH),
               (renderer, RENDERER_ORIGINAL, RENDERER_PATCHED, RENDERER_PATCH)]
    # Validate every retained original and compute both outputs before the first
    # mutation. A failed second atomic write leaves a recoverable verified pair.
    originals = {}
    before = {}
    for target, original, patched, patch_name in entries:
        current = digest(target)
        before[target.name] = current
        backup = target.with_name(target.name + BACKUP_SUFFIX)
        if current == patched:
            if backup.is_symlink() or digest(backup) != original:
                raise ValueError('Original atlas backup is missing or changed: ' + backup.name)
            originals[target] = backup.read_bytes()
        elif current == original:
            if backup.is_symlink() or (backup.exists() and digest(backup) != original):
                raise ValueError('Original atlas backup has changed: ' + backup.name)
            originals[target] = target.read_bytes()

    taz = digest(library('TazUO.dll'))
    known_taz = (trace.ORIGINAL, trace.INSTRUMENTED, frame.BUDGET, frame.COMBINED,
                 frame.LEGACY_BUDGET, frame.LEGACY_COMBINED)
    native = digest(library('FNA3D.dll'))
    sdl = digest(library('SDL3.dll'))
    utility = digest(library('ClassicUO.Utility.dll'))
    active = (enabled and len(originals) == 2 and taz in known_taz and
              native == SUPPORTED_FNA and sdl in (ORIGINAL_SDL, FIXED_SDL) and utility == UTILITY)
    report = {'requested': enabled, 'active': active, 'revision': 1,
              'before_sha256': before, 'native_fna3d_sha256': native,
              'sdl_sha256': sdl, 'utility_sha256': utility, 'pending_limit_bytes': 4 * 1024 * 1024}
    assets = Path(runtime_assets)
    outputs = {}
    if active:
        for helper in (HELPER, frame.HELPER):
            if not (assets / helper).is_file():
                raise ValueError('Atlas upload component is missing; reinstall the current APK')
        for target, original, patched, patch_name in entries:
            if before[target.name] == patched:
                outputs[target] = (target.read_bytes(), patched)
            else:
                raw = (assets / patch_name).read_bytes()
                if len(raw) > trace.LIMIT:
                    raise ValueError('Atlas delta is too large')
                output = trace.apply_delta(originals[target], base64.b64decode(raw.strip(), validate=True))
                if hashlib.sha256(output).hexdigest() != patched:
                    raise ValueError('Atlas output checksum mismatch: ' + target.name)
                outputs[target] = (output, patched)
    else:
        for target, original, patched, patch_name in entries:
            if before[target.name] == patched:
                outputs[target] = (originals[target], original)

    changed = False
    for target, original, patched, patch_name in entries:
        if target not in outputs:
            continue
        output, desired = outputs[target]
        if before[target.name] == desired:
            continue
        backup = target.with_name(target.name + BACKUP_SUFFIX)
        if active and not backup.exists():
            trace.atomic_write(backup, originals[target], original)
        trace.atomic_write(target, output, desired)
        changed = True
    report['action'] = ('batched_known_client' if changed else 'already_batched') if active else (
        'restored_original' if changed else 'unchanged_disabled' if not enabled else 'unchanged_unrecognized_client')
    report['active_sha256'] = {target.name: digest(target) for target, *_ in entries}
    if active:
        report['helper_sha256'] = digest(assets / HELPER)
    return report
