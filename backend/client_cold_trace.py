"""Opt-in passive graphics observations on the verified atlas/client pair."""
import base64
import hashlib
import json
from pathlib import Path
import client_atlas_uploads as atlas
import client_frame_budget as frame
import client_render_trace as trace
from client_graphics import digest
from uo_content import confined

PATCHED = '18c88d506dbe15dcb4bb56f98e4b1756d9f8074ba8ab485ad36e10c087f168b1'
PATCH = 'tazuo-5.2-cold-trace-fna.patch.b64'
BACKUP_SUFFIX = '.before-memento-cold-trace'
LAYER = 'VK_LAYER_MEMENTO_cold_trace'
LIBRARY = 'libmemento-vulkan-trace.so'


def target(root, metadata):
    folder = confined(root, metadata['executable']).parent
    matches = [p for p in folder.iterdir() if p.name.lower() == 'fna.dll']
    if len(matches) > 1:raise ValueError('Duplicate client FNA library')
    if matches and matches[0].is_symlink():raise ValueError('Cold trace library cannot be a symbolic link')
    return confined(root, (matches[0] if matches else folder/'FNA.dll').relative_to(root))


def restore(root, metadata):
    """Unstack only our known diagnostic layer before ordinary atlas selection.

    This also handles option/renderer changes and interrupted launches. The
    original 0.2.14 atlas backups remain responsible for full restoration.
    """
    fna = target(root, metadata)
    if digest(fna) != PATCHED:return False
    backup = fna.with_name(fna.name + BACKUP_SUFFIX)
    if backup.is_symlink() or digest(backup) != atlas.FNA_PATCHED:
        raise ValueError('Verified cold trace FNA backup is missing or changed')
    if not atlas.supported_fna(fna.parent, atlas.FNA_PATCHED):
        raise ValueError('Original atlas FNA backup is unavailable')
    trace.atomic_write(fna, backup.read_bytes(), atlas.FNA_PATCHED)
    return True


def prepare(root, metadata, assets, session, requested, eligible):
    if not isinstance(requested, bool):raise ValueError('Invalid cold-load diagnostics option')
    report = {'requested':requested, 'active':False, 'revision':1, 'diagnostic_only':True,
              'long_frame_ms':50, 'max_long_records_per_5s':8}
    if not requested:return dict(report, action='disabled')
    fna = target(root, metadata)
    if not eligible or digest(fna) != atlas.FNA_PATCHED:
        return dict(report, action='unsupported', reason='Requires supported TazUO 5.2, Turnip and Smooth world loading')
    assets = Path(assets)
    binary = assets/LIBRARY
    manifest = json.loads((assets/'vulkan-trace-bundle.json').read_text())
    if manifest.get('format') != 1 or manifest.get('revision') != 1 or binary.is_symlink() or digest(binary) != manifest.get('sha256'):
        raise ValueError('Vulkan diagnostic observer failed verification')
    if not (assets/frame.HELPER).is_file():raise ValueError('Cold trace helper is missing')
    backup = fna.with_name(fna.name + BACKUP_SUFFIX)
    if backup.is_symlink() or (backup.exists() and digest(backup) != atlas.FNA_PATCHED):
        raise ValueError('Cold trace FNA backup has changed')
    raw = (assets/PATCH).read_bytes()
    if len(raw) > trace.LIMIT:raise ValueError('Cold trace delta is too large')
    output = trace.apply_delta(fna.read_bytes(), base64.b64decode(raw.strip(),validate=True))
    if hashlib.sha256(output).hexdigest() != PATCHED:raise ValueError('Cold trace output checksum mismatch')
    # Write manifest before modifying the imported assembly. Paths refer to the
    # native ARM64 observer, not a replacement ICD or translated Windows DLL.
    layer = {'file_format_version':'1.0.0', 'layer': {
        'name':LAYER, 'type':'GLOBAL', 'library_path':str(binary),
        'api_version':'1.3.0', 'implementation_version':1,
        'description':'Memento passive cold-load graphics timing'}}
    directory = Path(session)/'vulkan-trace';directory.mkdir(exist_ok=True)
    (directory/'memento-cold-trace.json').write_text(json.dumps(layer)+'\n')
    if not backup.exists():trace.atomic_write(backup,fna.read_bytes(),atlas.FNA_PATCHED)
    trace.atomic_write(fna,output,PATCHED)
    return dict(report,active=True,action='observing_known_client',fna_sha256=PATCHED,
                layer_sha256=digest(binary),layer_path=str(directory))
