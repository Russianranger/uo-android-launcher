"""Memento imports and portable TazUO runtime metadata. No shell interpolation."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
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
    temp = path.with_name(path.name + '.new')
    with temp.open('w') as out:
        json.dump(data, out, indent=2)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)


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
    settings = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    if not isinstance(settings, dict):
        raise ValueError('The imported settings.json must contain a JSON object')
    backup = confined(root, path.with_suffix('.json.before-memento').relative_to(root))
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
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
    write_json(path, settings)
    # Explicit allowlist: support bundles must never include saved credentials.
    return {'settings':metadata['settings'], 'ultimaonlinedirectory':directory,
            'clientversion':settings['clientversion'], 'version_source':version_source,
            'required_assets':sorted({'tiledata.mul', 'map0.mul', 'cliloc.enu'}),
            'ip':'127.0.0.1', 'port':2593}


def renderer_settings(root, metadata, renderer):
    # TazUO's Main.cs overrides FNA3D_FORCE_DRIVER for force_driver 0/1/2.
    # Auto mode (3) preserves our explicit D3D11 selection for DXVK.
    path = confined(root, metadata['settings'])
    settings = json.loads(path.read_text(encoding='utf-8-sig'))
    settings['force_driver'] = 3 if renderer == 'turnip' else 1
    write_json(path, settings)


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
