"""Memento imports and portable TazUO runtime metadata. No shell interpolation."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import tempfile
import urllib.request
import zipfile

REPOSITORY = 'https://github.com/Russianranger/ultima-memento.git'
MAX_BYTES = 32 * 1024**3
# Asset/protocol version, not the TazUO executable or .NET version.
# https://uo-memento.com/setup/desktop-client/#server-information
MEMENTO_CLIENT_VERSION = '7.0.15.1'


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A unique sibling cannot follow a stale .new symlink after an interrupted
    # write. Sync both contents and the rename before returning to the caller.
    fd, name = tempfile.mkstemp(prefix=path.name + '.new-', dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(data, out, indent=2, allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
        sync_directory(path.parent)
    finally:
        temp.unlink(missing_ok=True)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def confined(root, relative):
    name = str(relative).replace('\\', '/')
    parts = PurePosixPath(name)
    if not name or parts.is_absolute() or '..' in parts.parts or ':' in name or '\0' in name:
        raise ValueError('Unsafe file path')
    root = Path(root).resolve()
    path = root.joinpath(*parts.parts)
    if not path.resolve().is_relative_to(root):
        raise ValueError('File path escapes workspace')
    return path


SETTINGS_BACKUPS = ('.memento-last-good', '.before-memento-pacing', '.before-memento')
PROFILE_BACKUPS = ('.memento-last-good', '.before-memento-layout')


def read_json_object(path):
    def invalid_constant(_): raise ValueError('Non-finite JSON value')
    data = json.loads(path.read_text(encoding='utf-8-sig'), parse_constant=invalid_constant)
    if not isinstance(data, dict): raise ValueError('Expected a JSON object')
    return data


def configuration_json(root, path, suffixes):
    """Read valid configuration or select a valid backup, without changing files."""
    root = Path(root).resolve()
    path = confined(root, path.relative_to(root))
    exists = path.exists()
    if exists:
        try: return read_json_object(path), None
        except (ValueError, UnicodeError): pass
    backups = [confined(root, path.with_name(path.name + suffix).relative_to(root)) for suffix in suffixes]
    # Stable ties favor last-good, then the newer pacing migration backup.
    backups = sorted((p for p in backups if p.is_file()), key=lambda p:p.stat().st_mtime_ns, reverse=True)
    for backup in backups:
        try: data = read_json_object(backup)
        except (ValueError, UnicodeError): continue
        return data, backup.name[len(path.name):]
    if exists or backups:
        raise ValueError(path.name + ' is damaged (a JSON object is required), and no valid recovery backup was found. '
                         'The original file was kept. Restore this file from your client backup before launching.')
    return {}, None


def save_configuration(root, path, data, recovered_from=None):
    root = Path(root).resolve()
    path = confined(root, path.relative_to(root))
    checkpoint = confined(root, path.with_name(path.name + '.memento-last-good').relative_to(root))
    if recovered_from and path.exists():
        # Keep the exact damaged bytes locally; never export configuration or
        # credentials. Exclusive creation preserves earlier interrupted copies.
        fd, name = tempfile.mkstemp(prefix=path.name + '.interrupted-', dir=path.parent)
        with os.fdopen(fd, 'wb') as out, path.open('rb') as source:
            shutil.copyfileobj(source, out)
            out.flush()
            os.fsync(out.fileno())
        sync_directory(path.parent)
    write_json(checkpoint, data)
    write_json(path, data)


def checkpoint_client_settings(root, metadata):
    """Snapshot only a validated file; a failed game write cannot poison backup."""
    root = Path(root).resolve()
    path = confined(root, metadata['settings'])
    backup = confined(root, path.with_name(path.name + '.memento-last-good').relative_to(root))
    write_json(backup, read_json_object(path))


def extract_zip(archive, destination, max_bytes=MAX_BYTES):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        members = z.infolist()
        if len(members) > 250000 or sum(x.file_size for x in members) > max_bytes:
            raise ValueError('Archive exceeds import limits')
        names = set()
        for item in members:
            path = confined(destination, item.filename)
            key = str(path.relative_to(destination.resolve())).casefold()
            if key in names:
                raise ValueError('Duplicate or case-conflicting archive entry: ' + item.filename)
            names.add(key)
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError('Links and special files are not supported in imports')
        total = 0
        for item in members:
            path = confined(destination, item.filename)
            if item.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            if shutil.disk_usage(destination).free < item.file_size + 128*1024**2:
                raise ValueError('Not enough storage to unpack the import')
            path.parent.mkdir(parents=True, exist_ok=True)
            with z.open(item) as source, path.open('xb') as out:
                while chunk := source.read(1024*1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError('Archive exceeds expanded size limit')
                    out.write(chunk)


def pe_architecture(path):
    with Path(path).open('rb') as f:
        if f.read(2) != b'MZ':
            raise ValueError('Select a Windows TazUO executable')
        f.seek(60)
        offset = struct.unpack('<I', f.read(4))[0]
        f.seek(offset)
        if f.read(4) != b'PE\0\0':
            raise ValueError('Invalid Windows executable')
        machine = struct.unpack('<H', f.read(2))[0]
    if machine not in (0x8664, 0x14c):
        raise ValueError('Import the Windows x64 or x86 client; ARM64EC packages are not supported by this runtime')
    return 'x64' if machine == 0x8664 else 'x86'


def inspect_client(root):
    root = Path(root)
    candidates = [p for p in root.rglob('*') if p.is_file() and p.name.lower() in ('tazuo.exe', 'classicuo.exe')]
    if not candidates:
        raise ValueError('No TazUO.exe or ClassicUO.exe found. Import the complete Memento client folder, not the launcher alone.')
    if len(candidates) != 1:
        raise ValueError('Multiple clients found. Import a folder/ZIP containing one client installation.')
    exe = candidates[0]
    architecture = pe_architecture(exe)
    configs = [p for p in exe.parent.iterdir() if p.name.lower() == exe.stem.lower()+'.runtimeconfig.json']
    if len(configs) != 1:
        raise ValueError('The client runtimeconfig.json is missing; import the complete .NET TazUO client.')
    options = json.loads(configs[0].read_text(encoding='utf-8-sig'))['runtimeOptions']
    frameworks = options.get('frameworks', []) + ([options['framework']] if 'framework' in options else [])
    included = options.get('includedFrameworks', [])
    for framework in frameworks + included:
        if framework['name'] != 'Microsoft.NETCore.App':
            raise ValueError('This client requires '+framework['name']+'. Import the standalone TazUO game client.')
        if not re.fullmatch(r'\d+\.\d+\.\d+', framework['version']):
            raise ValueError('Unsupported .NET runtime version')
    required = next((f['version'] for f in frameworks if f['name']=='Microsoft.NETCore.App'), None)
    if not required and not (exe.parent/'coreclr.dll').is_file():
        raise ValueError('Neither a framework requirement nor a bundled CoreCLR runtime was found')
    assets = [p.parent for p in root.rglob('*') if p.is_file() and p.name.lower()=='tiledata.mul']
    if len(assets) != 1:
        raise ValueError('Include exactly one Memento asset folder containing tiledata.mul')
    files = {p.name.lower() for p in assets[0].iterdir() if p.is_file()}
    if not {'cliloc.enu', 'map0.mul'}.issubset(files):
        raise ValueError('Memento server requires cliloc.enu and map0.mul beside tiledata.mul')
    return {'format':1, 'executable':str(exe.relative_to(root)), 'architecture':architecture,
            'dotnet_version':required, 'self_contained':not bool(required),
            'assets':str(assets[0].relative_to(root)), 'settings':str((exe.parent/'settings.json').relative_to(root))}


def local_client_settings(root, metadata):
    root = Path(root).resolve()
    path = confined(root, metadata['settings'])
    assets = confined(root, metadata['assets'])
    if not assets.is_dir():
        raise ValueError('Imported UO data directory is missing: ' + metadata['assets'])
    files = {p.name.lower() for p in assets.iterdir() if p.is_file()}
    missing = sorted({'tiledata.mul', 'map0.mul', 'cliloc.enu'} - files)
    if missing:
        raise ValueError('Imported UO data directory is incomplete; missing: ' + ', '.join(missing))
    settings, recovered = configuration_json(root, path, SETTINGS_BACKUPS)
    backup = confined(root, path.with_suffix('.json.before-memento').relative_to(root))
    if path.exists() and not backup.exists():
        write_json(backup, settings)
    relative = str(assets.relative_to(root)).replace('/', '\\')
    directory = 'D:\\' + ('' if relative == '.' else relative)
    version_source = 'settings.json'
    if not str(settings.get('clientversion') or '').strip():
        settings['clientversion'] = MEMENTO_CLIENT_VERSION
        version_source = 'Memento default'
    # v0.1.0–0.1.2 wrote an unknown property which TazUO silently ignored.
    settings.pop('ultimaonline', None)
    settings.update(ip='127.0.0.1', port=2593, ultimaonlinedirectory=directory,
                    reconnect=False, autologin=False, skip_login_screen=False)
    save_configuration(root, path, settings, recovered)
    # Explicit allowlist: support bundles must never include saved credentials.
    return {'settings':metadata['settings'], 'settings_recovery':recovered, 'ultimaonlinedirectory':directory,
            'clientversion':settings['clientversion'], 'version_source':version_source,
            'required_assets':sorted({'tiledata.mul', 'map0.mul', 'cliloc.enu'}),
            'ip':'127.0.0.1', 'port':2593}


def renderer_settings(root, metadata, renderer):
    # 5.2.0 has no auto mode (3): it falls through to OpenGL. Vulkan (2)
    # is supported by both that imported version and current TazUO builds.
    path = confined(root, metadata['settings'])
    settings = json.loads(path.read_text(encoding='utf-8-sig'))
    settings['force_driver'] = 2 if renderer == 'turnip' else 1
    write_json(path, settings)


def frame_settings(root, metadata, fps):
    """Cap TazUO itself as well as capture; preserve unrelated settings."""
    if type(fps) is not int or fps not in (30, 60):
        raise ValueError('Unsupported game frame target')
    path = confined(root, metadata['settings'])
    settings = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(settings, dict):
        raise ValueError('Client settings must contain a JSON object')
    backup = confined(root, path.with_suffix('.json.before-memento-pacing').relative_to(Path(root).resolve()))
    if not backup.exists():write_json(backup, settings)
    previous = settings.get('fps')
    settings['fps'] = fps
    write_json(path, settings)
    return {'game_fps':fps, 'capture_fps':fps,
            'previous_game_fps':previous if type(previous) is int else None}


def viewport_settings(root, metadata):
    """Set the world camera independently of the full window/UI canvas."""
    root = Path(root).resolve()
    path = confined(root, metadata['settings'])
    settings = json.loads(path.read_text(encoding='utf-8-sig'))
    exe = confined(root, metadata['executable'])
    custom = (settings.get('profilespath') or '').replace('\\', '/')
    if custom.lower().startswith('d:/'):
        profiles = confined(root, custom[3:] or '.')
    elif custom:
        profiles = confined(root, str(exe.parent.relative_to(root) / custom))
    else:
        profiles = exe.parent/'Data/Profiles'
    profiles = confined(root, profiles.relative_to(root))
    targets = [profiles/'default.json']
    if profiles.exists():
        targets += sorted(p for p in profiles.rglob('profile.json') if p.is_file())
    layout = {'window_client_bounds':{'X':1280,'Y':720},
              'game_window_position':{'X':0,'Y':0},
              'game_window_size':{'X':1098,'Y':720},
              'game_window_full_size':False,'game_window_lock':True,'window_borderless':True}
    pending = []
    for target in targets:
        target = confined(root, target.relative_to(root))
        profile, recovered = configuration_json(root, target, PROFILE_BACKUPS)
        backup = confined(root, target.with_suffix('.json.before-memento-layout').relative_to(root))
        pending.append((target, backup, profile, recovered))
    # Validate all profile paths/JSON first; never reset unrelated character data.
    for target, backup, profile, recovered in pending:
        if target.exists() and not backup.exists():write_json(backup, profile)
        save_configuration(root, target, dict(profile, **layout), recovered)
    settings.update(window_size={'X':1280,'Y':720},window_position={'X':0,'Y':0},is_win_maximized=False)
    write_json(path, settings)
    return {'window':[1280,720], 'world_viewport':[1098,720], 'gump_space_width':182,
            'profiles_updated':len(targets), 'profiles_recovered':sum(bool(p[3]) for p in pending),
            'profile_backup_suffix':'.json.before-memento-layout'}


def client_binary_report(root, metadata):
    """Record versions/sizes only; no profile contents or account credentials."""
    exe = confined(root, metadata['executable'])
    report = {'architecture':metadata.get('architecture'), 'self_contained':metadata.get('self_contained')}
    deps = exe.with_suffix('.deps.json')
    if deps.is_file():
        data = json.loads(deps.read_text(encoding='utf-8-sig'))
        report['packages'] = [name for name in data.get('libraries',{})
                              if name.startswith(('TazUO/','ClassicUO/','FNA/','runtimepack.Microsoft.NETCore.App.'))]
    assets = confined(root, metadata['assets'])
    report['asset_sizes'] = {p.name:p.stat().st_size for p in assets.iterdir()
                             if p.is_file() and p.name.lower() in ('tiledata.mul','map0.mul','statics0.mul','staidx0.mul')}
    return report


def swap_directory(staging, live):
    """Recoverable directory replacement. Keep the previous copy for rollback."""
    staging, live = Path(staging), Path(live)
    previous = live.with_name(live.name+'.previous')
    if not live.exists() and previous.exists():
        os.replace(previous, live)
    if previous.exists():
        shutil.rmtree(previous)
    if live.exists():
        os.replace(live, previous)
    try:
        os.replace(staging, live)
    except BaseException:
        if previous.exists():
            os.replace(previous, live)
        raise


def download(url, target, sha512=None):
    if not url.startswith('https://'):
        raise ValueError('HTTPS download required')
    target = Path(target)
    digest = hashlib.sha512()
    total = 0
    with urllib.request.urlopen(url, timeout=60) as source, target.open('wb') as out:
        while chunk := source.read(1024*1024):
            total += len(chunk)
            if total > 2*1024**3:
                raise ValueError('Download exceeds limit')
            digest.update(chunk)
            out.write(chunk)
    if sha512 and digest.hexdigest().lower() != sha512.lower():
        target.unlink()
        raise ValueError('Microsoft runtime checksum mismatch')


def install_dotnet(client, output):
    info = json.loads((Path(client)/'memento-client.json').read_text())
    if info['self_contained']:
        return {'message':'The imported client includes its .NET runtime.'}
    version = info['dotnet_version']
    channel = '.'.join(version.split('.')[:2])
    url = 'https://builds.dotnet.microsoft.com/dotnet/release-metadata/'+channel+'/releases.json'
    with urllib.request.urlopen(url, timeout=60) as response:
        releases = json.loads(response.read(8*1024*1024))
    minimum = tuple(map(int, version.split('.')))
    matches = [r['runtime'] for r in releases['releases'] if re.fullmatch(r'\d+\.\d+\.\d+', r.get('runtime',{}).get('version','')) and tuple(map(int,r['runtime']['version'].split('.'))) >= minimum]
    if not matches:
        raise ValueError('No compatible stable .NET runtime is published')
    runtime = max(matches, key=lambda r:tuple(map(int,r['version'].split('.'))))
    package = next(f for f in runtime['files'] if f['rid']=='win-'+info['architecture'] and f['name'].endswith('.zip'))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    archive, staging = output.with_suffix('.zip'), output.with_name('dotnet-staging')
    shutil.rmtree(staging, ignore_errors=True)
    try:
        download(package['url'], archive, package['hash'])
        extract_zip(archive, staging, 1024**3)
        if not (staging/'dotnet.exe').is_file():
            raise ValueError('Microsoft runtime archive is incomplete')
        write_json(staging/'memento-dotnet.json', {'version':runtime['version'],'architecture':info['architecture'],'sha512':package['hash']})
        swap_directory(staging, output)
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
    return {'message':'.NET '+runtime['version']+' '+info['architecture']+' installed'}
