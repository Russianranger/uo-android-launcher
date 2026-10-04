"""Opt-in passive graphics observations on the verified atlas/client pair."""
import base64
import hashlib
import json
from pathlib import Path
import client_atlas_uploads as atlas
import client_frame_budget as frame
import client_render_trace as trace
import client_cold_resources as resources
import client_graphics as graphics
from client_graphics import digest
from uo_content import confined

PATCHED = '18c88d506dbe15dcb4bb56f98e4b1756d9f8074ba8ab485ad36e10c087f168b1'
PATCH = 'tazuo-5.2-cold-trace-fna.patch.b64'
BACKUP_SUFFIX = '.before-memento-cold-trace'
LAYER = 'VK_LAYER_MEMENTO_cold_trace'
LIBRARY = 'libmemento-vulkan-trace.so'


def target(root, metadata, name='FNA.dll'):
    folder = confined(root, metadata['executable']).parent
    matches = [p for p in folder.iterdir() if p.name.lower() == name.lower()]
    if len(matches) > 1:raise ValueError('Duplicate cold trace library: '+name)
    if matches and matches[0].is_symlink():raise ValueError('Cold trace library cannot be a symbolic link')
    return confined(root, (matches[0] if matches else folder/name).relative_to(root))


def restore(root, metadata):
    """Unstack only our known diagnostic layer before ordinary atlas selection.

    This also handles option/renderer changes and interrupted launches. The
    original 0.2.14 atlas backups remain responsible for full restoration.
    """
    pending = []
    for name in dict.fromkeys(row[0] for row in resources.VARIANTS):
        library = target(root, metadata, name)
        current = digest(library)
        row = next((row for row in resources.VARIANTS if row[0] == name and row[2] == current), None)
        if name == 'FNA.dll' and (current == PATCHED or row is not None):
            base = atlas.FNA_PATCHED
            backup = library.with_name(library.name + BACKUP_SUFFIX)
            if not atlas.supported_fna(library.parent, atlas.FNA_PATCHED):
                raise ValueError('Original atlas FNA backup is unavailable')
        elif row is not None:
            base = row[1]
            backup = resources.backup_name(library, base)
        else:
            continue
        if backup.is_symlink() or digest(backup) != base:
            raise ValueError('Verified cold trace backup is missing or changed: '+name)
        pending.append((library, backup.read_bytes(), base))
    # Validate every known active component before restoring any of them. If a
    # process dies between atomic replaces, the next launch recognizes exactly
    # the remaining outputs and completes restoration idempotently.
    for library, data, base in pending:trace.atomic_write(library, data, base)
    return bool(pending)


def prepare(root, metadata, assets, session, requested, eligible):
    if not isinstance(requested, bool):raise ValueError('Invalid cold-load diagnostics option')
    report = {'requested':requested, 'active':False, 'revision':3, 'native_revision':2, 'diagnostic_only':True,
              'long_frame_ms':50, 'max_long_records_per_5s':8}
    if not requested:return dict(report, action='disabled')
    fna = target(root, metadata)
    if not eligible or digest(fna) != atlas.FNA_PATCHED:
        return dict(report, action='unsupported', reason='Requires supported TazUO 5.2, Turnip and Smooth world loading')
    if digest(target(root, metadata, 'SDL3.dll')) != graphics.ORIGINAL_SDL:
        return dict(report, action='unsupported', reason='Cold-load diagnostics require the verified original SDL library')
    selected = []
    for name in dict.fromkeys(row[0] for row in resources.VARIANTS):
        library = target(root, metadata, name)
        source = PATCHED if name == 'FNA.dll' else digest(library)
        row = next((row for row in resources.VARIANTS if row[0] == name and row[1] == source), None)
        if row is None:
            return dict(report, action='unsupported', reason='Unrecognized cold resource library: '+name)
        selected.append((library, row))
    assets = Path(assets)
    binary = assets/LIBRARY
    manifest = json.loads((assets/'vulkan-trace-bundle.json').read_text())
    if manifest.get('format') != 1 or manifest.get('revision') != 2 or binary.is_symlink() or digest(binary) != manifest.get('sha256'):
        raise ValueError('Vulkan diagnostic observer failed verification')
    if not (assets/frame.HELPER).is_file():raise ValueError('Cold trace helper is missing')
    backup = fna.with_name(fna.name + BACKUP_SUFFIX)
    if backup.is_symlink() or (backup.exists() and digest(backup) != atlas.FNA_PATCHED):
        raise ValueError('Cold trace FNA backup has changed')
    raw = (assets/PATCH).read_bytes()
    if len(raw) > trace.LIMIT:raise ValueError('Cold trace delta is too large')
    output = trace.apply_delta(fna.read_bytes(), base64.b64decode(raw.strip(),validate=True))
    if hashlib.sha256(output).hexdigest() != PATCHED:raise ValueError('Cold trace output checksum mismatch')
    pending = []
    for library, row in selected:
        name, base, patched, patch = row
        data = output if name == 'FNA.dll' else library.read_bytes()
        resource_backup = backup if name == 'FNA.dll' else resources.backup_name(library, base)
        backup_hash = atlas.FNA_PATCHED if name == 'FNA.dll' else base
        if resource_backup.is_symlink() or (resource_backup.exists() and digest(resource_backup) != backup_hash):
            raise ValueError('Cold resource backup has changed: '+name)
        raw = (assets/patch).read_bytes()
        if len(raw) > trace.LIMIT:raise ValueError('Cold resource delta is too large')
        updated = trace.apply_delta(data, base64.b64decode(raw.strip(),validate=True))
        if hashlib.sha256(updated).hexdigest() != patched:raise ValueError('Cold resource output checksum mismatch: '+name)
        pending.append((library, resource_backup, fna.read_bytes() if name == 'FNA.dll' else data, backup_hash, updated, patched))
    # Write manifest before modifying the imported assembly. Paths refer to the
    # native ARM64 observer, not a replacement ICD or translated Windows DLL.
    layer = {'file_format_version':'1.0.0', 'layer': {
        'name':LAYER, 'type':'GLOBAL', 'library_path':str(binary),
        'api_version':'1.3.0', 'implementation_version':2,
        'description':'Memento passive cold-load graphics timing'}}
    directory = Path(session)/'vulkan-trace';directory.mkdir(exist_ok=True)
    (directory/'memento-cold-trace.json').write_text(json.dumps(layer)+'\n')
    for library, resource_backup, data, base, updated, patched in pending:
        if not resource_backup.exists():trace.atomic_write(resource_backup,data,base)
    for library, resource_backup, data, base, updated, patched in pending:
        trace.atomic_write(library,updated,patched)
    return dict(report,active=True,action='observing_known_client',fna_sha256=digest(fna),
                resource_boundaries=24, resource_locks=5, resource_libraries={row[0]:row[2] for _,row in selected},
                layer_sha256=digest(binary),layer_path=str(directory))
