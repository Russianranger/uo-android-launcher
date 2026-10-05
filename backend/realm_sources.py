"""Validated Realm source selection, ZIP layouts and Android Mono deployment."""
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit

from uo_content import REPOSITORY, confined


UPSTREAM_REPOSITORY = 'https://github.com/Jascen/ultima-memento.git'
SOURCE_MARKER = 'realm-source.json'
CORE_FLAGS = ['-optimize+', '-unsafe', '-t:exe', '-win32icon:../System/icon.ico',
              '-nowarn:219,414', '-d:NEWTIMERS', '-d:NEWPARENT', '-d:MONO',
              '-recurse:../System/*.cs', '-main:Server.Core']
NETWORK_PATCHES = (
    ('ServerList.cs', 'public static readonly string Address = MySettings.S_Address;',
     'public static readonly string Address = "127.0.0.1";'),
    ('ServerList.cs', 'public static readonly bool AutoDetect = MySettings.S_AutoDetect;',
     'public static readonly bool AutoDetect = false;'),
    ('SocketOptions.cs', 'new IPEndPoint( IPAddress.Any, MySettings.S_Port )',
     'new IPEndPoint( IPAddress.Loopback, 2593 )'),
)


def repository_url(value):
    if not isinstance(value, str):
        raise ValueError('Enter an HTTPS Git repository URL')
    value = value.strip()
    parsed = urlsplit(value)
    if (len(value)>2048 or parsed.scheme != 'https' or not parsed.hostname or
            parsed.username is not None or parsed.password is not None or
            parsed.query or parsed.fragment or any(ord(c)<33 for c in value)):
        raise ValueError('Enter an HTTPS Git repository URL without credentials, a query or a fragment')
    # No protocol helpers, option injection, encoded traversal or ambiguous
    # host/path delimiters. HTTPS Git hosts may use subgroup paths and ports.
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',parsed.hostname) or '..' in parsed.hostname:
        raise ValueError('Enter an HTTPS Git repository URL with a valid hostname')
    try: port=parsed.port
    except ValueError as error: raise ValueError('Invalid Git repository port') from error
    parts = parsed.path.rstrip('/').split('/')
    if (len(parts)<2 or parts[0] or any(not re.fullmatch(r'[A-Za-z0-9_~][A-Za-z0-9._~-]{0,199}',p) or p in ('.','..') for p in parts[1:])):
        raise ValueError('Use a repository URL such as https://github.com/owner/repository')
    if parsed.hostname.lower()=='github.com':
        if port not in (None,443) or len(parts)!=3:
            raise ValueError('Use a GitHub repository URL such as https://github.com/owner/repository')
        parts[-1]=parts[-1].removesuffix('.git')+'.git'
    host=parsed.hostname.lower()+(':'+str(port) if port not in (None,443) else '')
    return 'https://'+host+'/'.join(parts)


def source_kind(repository):
    repository = repository_url(repository)
    if repository.casefold() == UPSTREAM_REPOSITORY.casefold(): return 'upstream'
    if repository.casefold() == REPOSITORY.casefold(): return 'fork'
    return 'custom'


def checked_ref(value):
    if not isinstance(value, str): raise ValueError('Enter a branch, tag or commit SHA')
    value = value.strip()
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,159}', value) or
            '..' in value or '//' in value or value.endswith(('/', '.', '.lock'))):
        raise ValueError('Enter a branch, tag or commit SHA')
    return value


def selection(args, previous=None):
    """New installs default upstream; old callers retain their selected source."""
    kind = args.get('source')
    if kind is None and previous:
        if previous.get('source') == 'zip':
            raise ValueError('Compile the imported server ZIP, or choose an online source explicitly')
        repository = repository_url(previous['repository'])
        kind = source_kind(repository)
    elif kind in (None, 'upstream'):
        kind, repository = 'upstream', UPSTREAM_REPOSITORY
    elif kind == 'fork':
        repository = REPOSITORY
    elif kind == 'custom':
        repository = repository_url(args.get('repository'))
    else:
        raise ValueError('Choose upstream, your fork or a custom repository')
    ref = checked_ref(args.get('ref') or (previous.get('ref', 'main') if previous and args.get('source') is None else 'main'))
    return {'format': 1, 'source': kind, 'repository': repository, 'ref': ref}


def source_info(root):
    marker = Path(root) / SOURCE_MARKER
    if not marker.is_file(): return None
    if marker.is_symlink(): raise ValueError('Server source metadata must be a real file')
    data = json.loads(marker.read_text())
    if not isinstance(data, dict) or data.get('format') != 1:
        raise ValueError('Unsupported server source metadata')
    # ZIP names and embedded build markers never identify a trusted repository.
    if data.get('source') == 'zip':
        if not re.fullmatch(r'[a-f0-9]{64}', data.get('archive_sha256', '')):
            raise ValueError('Invalid server ZIP metadata')
        return dict(data)
    repository = repository_url(data.get('repository'))
    kind = data.get('source')
    if kind not in ('upstream', 'fork', 'custom'):
        raise ValueError('Invalid server source selection')
    if kind != 'custom' and source_kind(repository) != kind:
        raise ValueError('Server source metadata does not match its repository')
    if not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', data.get('revision', '')):
        raise ValueError('Invalid server source revision')
    return dict(data, repository=repository, ref=checked_ref(data.get('ref')))


def inspect_server(root):
    """Accept a repo ZIP, a wrapped release ZIP, or a flat World folder ZIP."""
    root = Path(root).resolve()
    candidates = [path.parents[2] for path in root.rglob('compile-world-linux.sh')
                  if path.relative_to(root).parts[-3:] == ('Source', 'Tools', 'compile-world-linux.sh')]
    if len(candidates) != 1:
        raise ValueError('Choose a ZIP with exactly one supported Memento World/Source/Tools/compile-world-linux.sh layout')
    world = candidates[0]
    for name in ('Source/Tools/compile-world-linux.sh', 'Source/System/icon.ico',
                 'Source/Scripts/System/Misc/ServerList.cs', 'Source/Scripts/System/Misc/SocketOptions.cs',
                 'Info/Scripts/Settings.cs', 'Data/System/CFG/Assemblies.cfg'):
        path = confined(world, name)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Server source is incomplete: missing ' + name)
    if not any((world/'Source/System').glob('*.cs')):
        raise ValueError('Server source is incomplete: missing Mono core source files')
    # Reject changed network layouts during import, before replacing prepared source.
    check_network(world)
    return world


def check_network(world, patch=False):
    misc = Path(world)/'Source/Scripts/System/Misc'
    for name, before, after in NETWORK_PATCHES:
        path = confined(world, 'Source/Scripts/System/Misc/'+name)
        text = path.read_text()
        if text.count(before) != 1:
            # App-exported source may already have our exact local patch.
            if text.count(after) != 1:
                raise ValueError('Upstream '+name+' changed; review its local-network patch before compiling')
        elif patch:
            path.write_text(text.replace(before, after))
    if patch:
        shutil.copy2(Path(__file__).with_name('MementoAndroidControl.cs'), misc/'MementoAndroidControl.cs')


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        while chunk := source.read(1024*1024): digest.update(chunk)
    return digest.hexdigest()


def add_missing_settings(retained, defaults):
    """Keep user values/code and add new literal settings required by an update."""
    import server_settings
    existing = server_settings.masked(retained, strings=True)
    additions = []
    for match in server_settings.FIELDS.finditer(server_settings.masked(defaults)):
        name, kind = match['name'], re.sub(r'\s', '', match['type'])
        if re.search(r'\b'+re.escape(name)+r'\b', existing): continue
        try: server_settings.literal(kind, match['value'])
        except (ValueError, TypeError): continue
        additions.append((name, defaults[match.start():match.end()].strip()))
    if not additions: return retained, []
    declarations = list(re.finditer(r'\bclass\s+MySettings\b', existing))
    if len(declarations) != 1:
        raise ValueError('New source requires settings additions; review your custom MySettings class before updating')
    opening = existing.find('{', declarations[0].end())
    depth, closing = 0, None
    for offset in range(opening, len(existing)):
        if existing[offset] == '{': depth += 1
        elif existing[offset] == '}':
            depth -= 1
            if depth == 0:
                closing = offset
                break
    if opening == -1 or closing is None:
        raise ValueError('Unable to add new source settings safely; review your custom MySettings class')
    text = '\n\t// New source defaults; existing settings and custom code were retained.\n'
    text += '\n'.join('\t'+declaration for _, declaration in additions)+'\n'
    return retained[:closing]+text+retained[closing:], [name for name, _ in additions]


def compile_server(world, command):
    """Compile both core and scripts before a new deployment can replace a world."""
    world = Path(world)
    check_network(world, patch=True)
    executable = world/'WorldLinux.exe'
    executable.unlink(missing_ok=True)
    command(['mcs', '-out:'+str(executable)] + CORE_FLAGS, cwd=world/'Source/Tools')
    if not executable.is_file(): raise ValueError('Mono did not produce WorldLinux.exe')
    references = [line.strip() for line in (world/'Data/System/CFG/Assemblies.cfg').read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith('#')]
    files = sorted((world/'Source/Scripts').rglob('*.cs')) + sorted((world/'Info/Scripts').rglob('*.cs'))
    response, checked = world/'memento-scripts-check.rsp', world/'memento-scripts-check.dll'
    try:
        paths = [str(path.relative_to(world)) for path in files]
        if any('"' in path or any(ord(c) < 32 for c in path) for path in paths):
            raise ValueError('Unsupported characters in a server script path')
        response.write_text('\n'.join('"./'+path+'"' for path in paths))
        # Match the defines supplied by ScriptCompiler.GetDefines under Mono.
        command(['mcs', '-t:library', '-d:MONO', '-d:Framework_2_0', '-d:x64',
                 '-out:'+str(checked), '-r:'+str(executable)] + ['-r:'+r for r in references] + ['@'+str(response)], cwd=world)
    finally:
        response.unlink(missing_ok=True)
        checked.unlink(missing_ok=True)
    # Force the normal runtime compiler to build a fresh cache against this core.
    for path in (world/'Data').glob('Data*.bin'): path.unlink()
    for name in ('Data.hash', 'Data.ref'): (world/'Data'/name).unlink(missing_ok=True)
    return len(files)
