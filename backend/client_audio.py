"""Configure the APK's ALSA endpoint without changing the installed rootfs."""
import hashlib
import json
from pathlib import Path
import struct
import re
import zlib
from itertools import islice


# These readers inspect metadata only; they never extract or modify game files.
# PFS layout/CRC: EQEmu/zone-utilities src/common/pfs.cpp and pfs_crc.cpp.
PFS_NAME_CRC = 0x61580ac9
SPELL_WAVS = ('spelcast.wav', 'spell_1.wav', 'spell_2.wav', 'spell_3.wav',
              'spell_4.wav', 'spell_5.wav')


def wav_format(data):
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE': return 'unrecognized'
    offset = 12
    while offset + 8 <= len(data):
        size = struct.unpack_from('<I', data, offset+4)[0]
        if data[offset:offset+4] == b'fmt ' and size >= 16 and offset+24 <= len(data):
            tag, channels, rate = struct.unpack_from('<HHI', data, offset+8)
            bits = struct.unpack_from('<H', data, offset+22)[0]
            return f'tag={tag},channels={channels},rate={rate},bits={bits}'
        offset += 8 + size + (size & 1)
    return 'unrecognized'


def dds_header(data):
    """Describe a DDS header, not whether Direct3D can successfully load it."""
    if len(data) < 128 or data[:4] != b'DDS ': return {'status': 'unrecognized_or_short_header'}
    if struct.unpack_from('<I', data, 4)[0] != 124 or struct.unpack_from('<I', data, 76)[0] != 32:
        return {'status': 'unexpected_header_size'}
    height, width = struct.unpack_from('<II', data, 12)
    return {'status': 'header_read', 'width': width, 'height': height,
            'mipmaps': struct.unpack_from('<I', data, 28)[0],
            'pixel_flags': struct.unpack_from('<I', data, 80)[0],
            'fourcc_hex': data[84:88].hex(), 'rgb_bits': struct.unpack_from('<I', data, 88)[0]}


def pfs_crc(name):
    crc = 0
    for byte in name.lower().encode('ascii') + b'\0':
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04c11db7 if crc & 0x80000000 else 0)) & 0xffffffff
    return crc


def inspect_pfs(path, wanted, budget, header_format=wav_format):
    """Read the index and selected asset headers, with a shared I/O budget.

    Match entries by CRC, not directory order. Never trust archive paths,
    advertised inflate sizes, duplicate names/CRCs, or symlinks.
    """
    if path.is_symlink(): raise ValueError('symlink')
    size = path.stat().st_size
    if not 12 <= size <= 512*1024*1024: raise ValueError('archive_size')
    with path.open('rb') as source:
        def read(offset, count):
            if offset < 0 or count < 0 or offset+count > size: raise ValueError('bounds')
            if count > budget[0]: raise ValueError('read_budget')
            budget[0] -= count
            source.seek(offset); data = source.read(count)
            if len(data) != count: raise ValueError('short_read')
            return data

        header = read(0, 12)
        if header[4:8] != b'PFS ': raise ValueError('signature')
        directory = struct.unpack_from('<I', header)[0]
        if directory < 12: raise ValueError('directory')
        count = struct.unpack('<I', read(directory, 4))[0]
        if not 1 <= count <= 8193: raise ValueError('entry_limit')
        entries = {}
        for crc, offset, length in struct.iter_unpack('<III', read(directory+4, count*12)):
            if crc in entries: raise ValueError('duplicate_crc')
            if not 12 <= offset < directory or not 0 < length <= 64*1024*1024:
                raise ValueError('entry_bounds')
            entries[crc] = (offset, length)

        def inflate(entry, prefix=None):
            offset, length = entry
            need = min(length, prefix) if prefix else length
            if need > 512*1024: raise ValueError('inflate_limit')
            result = bytearray()
            while len(result) < need:
                if offset+8 > directory: raise ValueError('block_bounds')
                compressed, expanded = struct.unpack('<II', read(offset, 8)); offset += 8
                if not 0 < compressed <= 65536 or not 0 < expanded <= 65536:
                    raise ValueError('block_limit')
                if expanded > length-len(result) or offset+compressed > directory:
                    raise ValueError('block_bounds')
                decoder = zlib.decompressobj()
                block = decoder.decompress(read(offset, compressed), expanded+1)
                if len(block) != expanded or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                    raise ValueError('block_size')
                result.extend(block); offset += compressed
            return bytes(result[:need])

        table = entries.pop(PFS_NAME_CRC, None)
        if not table: raise ValueError('filename_table')
        data = inflate(table)
        if len(data) < 4: raise ValueError('filename_table')
        names_count = struct.unpack_from('<I', data)[0]
        if names_count != len(entries): raise ValueError('filename_count')
        offset = 4; names = {}; seen = set()
        for _ in range(names_count):
            if offset+4 > len(data): raise ValueError('filename_bounds')
            length = struct.unpack_from('<I', data, offset)[0]; offset += 4
            if not 2 <= length <= 256 or offset+length > len(data): raise ValueError('filename_bounds')
            raw = data[offset:offset+length]; offset += length
            if raw[-1:] != b'\0': raise ValueError('filename_terminator')
            name = raw[:-1].decode('ascii').lower()
            if not re.fullmatch(r'[a-z0-9_ .-]{1,251}', name) or '..' in name:
                raise ValueError('unsafe_filename')
            crc = pfs_crc(name)
            if name in names or crc in seen or crc not in entries: raise ValueError('ambiguous_filename')
            seen.add(crc); names[name] = entries[crc]
        if offset != len(data): raise ValueError('filename_trailing_data')
        headers = {name: header_format(inflate(names[name], 4096)) for name in wanted if name in names}
        return set(names), headers


class SoundTrace:
    """Retain bounded lifecycle evidence independently of rotating Wine text."""
    hot = frozenset(('IDirectSoundBufferImpl_Lock', 'IDirectSoundBufferImpl_Unlock',
        'IDirectSoundBufferImpl_GetCurrentPosition', 'IDirectSoundBufferImpl_GetStatus',
        'DSOUND_MixOne', 'DSOUND_MixToPrimary', 'DSOUND_PerformMix', 'DSOUND_MixInBuffer',
        'DSOUND_MixerVol', 'mixieee32', 'client_GetCurrentPadding', 'render_GetBuffer',
        'render_ReleaseBuffer', 'clock_GetPosition', 'clock_GetFrequency'))

    def __init__(self):
        self.events = {}; self.filtered = 0; self.dropped = 0

    def observe(self, line):
        # No general file tracing: do not collect arbitrary paths/chat/settings.
        if ':dsound:' not in line and ':mmdevapi:' not in line and ':wave:' not in line: return
        match = re.search(r':(trace|warn|err|fixme):(dsound|mmdevapi|wave):([A-Za-z0-9_]{1,96}) ', line)
        if not match: return
        level, channel, function = match.groups()
        if level == 'trace' and function in self.hot:
            self.filtered += 1; return
        key = ':'.join(match.groups())
        if key not in self.events:
            if len(self.events) >= 96: self.dropped += 1; return
            self.events[key] = {'count': 0, 'first': [], 'last': []}
        item = self.events[key]; item['count'] += 1
        sample = line[:512]
        if len(item['first']) < 3: item['first'].append(sample)
        else: item['last'] = (item['last'] + [sample])[-3:]

    def report(self):
        return {'format': 1, 'filtered_mixer_lines': self.filtered,
                'dropped_event_types': self.dropped, 'events': self.events}


def inspect_client(client, logs, packed=False):
    """Bounded, read-only inventory. Never export INIs, PCM or arbitrary paths.

    Missing loose files may be packed in an archive; report that distinction
    instead of declaring the user's installation broken. Wine resolves case.
    """
    report = {'format': 3, 'settings': {}, 'files': {}, 'loose_wav_count': 0,
              'wav_formats': {}, 'wav_references': 0, 'resolved_loose': 0,
              'unresolved_loose': [], 'unresolved_count': 0, 'unsafe_references': 0,
              'inventory_truncated': False, 'packed_scan_requested': packed,
              'archives': {}, 'spell_files': {}, 'resolved_packed': 0,
              'unresolved_after_packed': None,
              'note': 'Unresolved loose sounds may be packed; this is not proof of missing assets.'}

    def directory(path, limit):
        if path.is_symlink() or not path.is_dir(): return {}
        entries = list(islice(path.iterdir(), limit + 1))
        if len(entries) > limit: report['inventory_truncated'] = True
        found = {}
        for p in entries[:limit]:
            key = p.name.casefold()
            # Reject case collisions and all symlinks rather than selecting one.
            if key in found or p.is_symlink(): found[key] = None
            else: found[key] = p
        return found

    try:
        root = directory(client, 20000)
        sounds = root.get('sounds')
        sound_files = directory(sounds, 20000) if sounds else {}
        for name in ('soundassets.txt', 'sounds.eff', 'mss32.dll', 'msssoft.m3d',
                     'mssds3d.m3d', 'mssdx7.m3d', 'mssmp3.asi', 'spelleffects.eff',
                     'spellsnew.edd', 'spellsnew.eff', 'spells_us.txt', 'eqgraphicsdx9.dll'):
            path = root.get(name)
            report['files'][name] = {'present': bool(path and path.is_file())}
            if path and path.is_file(): report['files'][name]['bytes'] = path.stat().st_size
        # This exact texture was named by the game's particle warning. Check
        # only fixed locations; no recursive client scan or rendering changes.
        particle = {'texture': 'zapmuze.dds', 'loose': {}, 'archives': {},
                    'packed_scan_requested': packed,
                    'note': 'Presence/header metadata does not prove a successful GPU load. Unlocated here is not proof of a missing asset; other archive/search paths are not scanned.'}
        report['particle_texture'] = particle
        for location in ('root', 'spelleffects', 'resources'):
            mapping = root if location == 'root' else directory(root[location], 20000) if root.get(location) else {}
            path = mapping.get('zapmuze.dds')
            entry = {'status': 'not_found_in_location'}
            if 'zapmuze.dds' in mapping and path is None: entry['status'] = 'ambiguous_or_symlink'
            elif path and path.is_file():
                with path.open('rb') as source: header = source.read(128)
                entry = dict(status='present', bytes=path.stat().st_size, header=dds_header(header))
            particle['loose'][location] = entry
        if packed:
            budget = [2*1024*1024]
            # Bounded metadata probe of explicitly named spell archives only.
            # Never extract their assets or enumerate unrelated game archives.
            for name in ('spellsnew.s3d', 'spellsnew.eqg', 'spelleffects.s3d', 'spelleffects.eqg'):
                path = root.get(name)
                if not path or not path.is_file(): continue
                try:
                    names, headers = inspect_pfs(path, {'zapmuze.dds'}, budget, dds_header)
                    particle['archives'][name] = {'status': 'indexed', 'contains_texture': 'zapmuze.dds' in names,
                                                  'header': headers.get('zapmuze.dds')}
                except (OSError, ValueError, zlib.error) as error:
                    particle['archives'][name] = {'status': 'unreadable', 'reason': type(error).__name__}
            path = root.get('eqgraphicsdx9.dll')
            if path and path.is_file() and path.stat().st_size <= 16*1024*1024:
                particle['graphics_dll_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        ini = root.get('eqclient.ini')
        allowed = {'sound', 'music', 'soundvolume', 'musicvolume', 'soundrealism',
                   'envsounds', 'combatmusic', 'speakertype', 'sound44k', 'sound16bit',
                   'usethreepointlighting', 'shownameslevel', 'showspelleffects',
                   'spellparticleopacity', 'spellparticledensity',
                   'spellparticlenearclipplane', 'spellparticlecastfilter'}
        if ini and ini.is_file() and ini.stat().st_size <= 2*1024*1024:
            active = False
            for line in ini.read_bytes().decode('latin-1').lstrip('\xef\xbb\xbf').splitlines():
                line = line.strip()
                if line.startswith('[') and line.endswith(']'): active = line[1:-1].casefold() == 'defaults'
                elif active and '=' in line and not line.startswith((';', '#')):
                    key, value = (v.strip() for v in line.split('=', 1))
                    if key.casefold() in allowed and re.fullmatch(r'[-+0-9A-Za-z. ]{1,32}', value):
                        report['settings'][key.casefold()] = value
        if packed:
            from client_spells import inspect_data, read_table
            resources = root.get('resources')
            resource_files = directory(resources, 20000) if resources else {}
            report['spell_tables'] = {}
            for location, mapping in (('root', root), ('resources', resource_files)):
                path = mapping.get('spells_us.txt')
                if path is None:
                    report['spell_tables'][location] = {'status': 'missing_or_ambiguous'}
                    continue
                try:
                    report['spell_tables'][location] = dict(status='inspected', **inspect_data(read_table(path)))
                except (ValueError, OSError):
                    report['spell_tables'][location] = {'status': 'unreadable_or_invalid'}
        # Inspect headers only, at most 256 files and 4 KiB each. A format
        # count is enough to separate PCM from compressed WAV codecs.
        wave_paths = [p for mapping in (root, sound_files) for key, p in mapping.items()
                      if key.endswith('.wav') and p and p.is_file()]
        report['loose_wav_count'] = len(wave_paths)
        report['wav_headers_checked'] = min(len(wave_paths), 256)
        for path in sorted(wave_paths)[:256]:
            with path.open('rb') as f: data = f.read(4096)
            fmt = wav_format(data)
            report['wav_formats'][fmt] = report['wav_formats'].get(fmt, 0) + 1
        references = set()
        table = root.get('soundassets.txt')
        if table and table.is_file() and table.stat().st_size <= 2*1024*1024:
            for line in table.read_bytes().decode('latin-1').splitlines():
                if line.lstrip().startswith(('#', '//', ';')): continue
                for field in line.split('^'):
                    name = field.strip().strip('"{}').replace('\\', '/').casefold()
                    if not name.endswith('.wav'): continue
                    if not re.fullmatch(r'(?:sounds/)?[a-z0-9_ .-]{1,160}\.wav', name) or '..' in name:
                        report['unsafe_references'] += 1; continue
                    references.add(name)
            report['wav_references'] = len(references)
            for name in sorted(references):
                bare = name.removeprefix('sounds/')
                choices = [sound_files.get(bare)] if name.startswith('sounds/') else [root.get(bare), sound_files.get(bare)]
                if any(p and p.is_file() for p in choices): report['resolved_loose'] += 1
                else:
                    report['unresolved_count'] += 1
                    if len(report['unresolved_loose']) < 24: report['unresolved_loose'].append(name)
        elif table: report['soundassets_unreadable'] = True
        # Probe known classic casting/effect filenames, even if absent from the
        # table. Also include bounded spell-prefixed references from this client.
        wanted = set(SPELL_WAVS)
        wanted.update(sorted(n.removeprefix('sounds/') for n in references
                             if n.removeprefix('sounds/').startswith(('spell', 'spelcast')))[:58])
        packed_names = set(); packed_headers = {}; budget = [8*1024*1024]
        archives = sorted((n, p) for n, p in root.items() if re.fullmatch(r'snd[0-9]{1,3}\.pfs', n))
        if len(archives) > 64: report['inventory_truncated'] = True
        for name, path in archives[:64]:
            record = {'status': 'not_scanned'}; report['archives'][name] = record
            if not path or not path.is_file(): record['status'] = 'ambiguous'; continue
            record['bytes'] = path.stat().st_size
            if not packed: continue
            try:
                names, headers = inspect_pfs(path, wanted, budget)
                record.update(status='indexed', wav_count=sum(n.endswith('.wav') for n in names))
                packed_names.update(names)
                for n, fmt in headers.items(): packed_headers.setdefault(n, []).append({'archive': name, 'format': fmt})
            except (OSError, ValueError, zlib.error) as error:
                # Fixed reason codes only; never export exceptions with paths.
                record.update(status='unreadable', reason=type(error).__name__)
        for name in sorted(wanted):
            entry = {'loose': [], 'packed': packed_headers.get(name, [])}
            for location, mapping in (('root', root), ('sounds', sound_files)):
                path = mapping.get(name)
                if path and path.is_file():
                    with path.open('rb') as f: fmt = wav_format(f.read(4096))
                    entry['loose'].append({'location': location, 'bytes': path.stat().st_size, 'format': fmt})
            report['spell_files'][name] = entry
        if packed:
            loose_missing = {n for n in references if not any(p and p.is_file() for p in
                ([sound_files.get(n.removeprefix('sounds/'))] if n.startswith('sounds/') else [root.get(n), sound_files.get(n)]))}
            report['resolved_packed'] = sum(n.removeprefix('sounds/') in packed_names for n in loose_missing)
            report['unresolved_after_packed'] = len(loose_missing)-report['resolved_packed']
        report['packed_scan_complete'] = packed and not report['inventory_truncated'] and all(
            r['status'] == 'indexed' for r in report['archives'].values())

    except OSError as error:
        # A diagnostic must not stop a working game launch. Do not export an
        # exception string that may contain unrelated imported filenames.
        report['inspection_error'] = type(error).__name__
    target = logs/'client-sound-assets.json'
    previous = logs/'client-sound-assets.previous.json'
    if target.is_file(): target.replace(previous)
    target.write_text(json.dumps(report, indent=2)+'\n')
    return {k: report[k] for k in ('loose_wav_count', 'wav_references', 'resolved_loose', 'unresolved_count', 'settings')}


def configure_environment(env, session):
    env.update(ALSA_CONFIG_PATH=str(session/'asound.conf'), TRASC_AUDIO_SOCKET=str(session/'audio.sock'))
    # Wine's session override avoids persistent driver edits and stale Pulse defaults.
    env['WINEDLLOVERRIDES'] += ';winepulse.drv=d'


def prepare(folder, session):
    library = folder/'libasound_module_pcm_trasc.so'
    data = library.read_bytes()
    manifest = json.loads((folder/'audio-bundle.json').read_text())
    if (manifest.get('protocol'), manifest.get('architecture')) != (1, 'arm64-glibc'):
        raise RuntimeError('Unsupported audio bridge bundle')
    if library.is_symlink() or hashlib.sha256(data).hexdigest() != manifest.get('sha256'):
        raise RuntimeError('Audio bridge checksum failed')
    if data[:5] != b'\x7fELF\x02' or struct.unpack_from('<H', data, 18)[0] != 183:
        raise RuntimeError('Audio bridge is not ARM64')
    if not (session/'audio.sock').is_socket():
        raise RuntimeError('Android audio bridge is not listening')
    # The built-in ALSA plug handles sample-rate, channel and sample-format conversion.
    # Capture is deliberately absent: the game needs playback, no microphone access.
    (session/'asound.conf').write_text(
        '</usr/share/alsa/alsa.conf>\n'
        f'pcm_type.trasc {{ lib "{library}" }}\n'
        'pcm.trasc { type trasc }\n'
        'pcm.!default { type plug slave { pcm "trasc" format S16_LE rate 48000 channels 2 } }\n')
    return {'backend': 'alsa-audiotrack', 'protocol': 1, 'rate': 48000, 'channels': 2,
            'sha256': manifest['sha256']}
