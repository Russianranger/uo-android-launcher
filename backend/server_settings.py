"""Edit literal Memento settings without evaluating or rewriting custom C#."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

from uo_content import confined, sync_directory, write_json


SETTINGS = 'Info/Scripts/Settings.cs'
OVERRIDES = 'Info/Scripts/Settings.override.cs'
NETWORK = {'S_Port': 2593, 'S_Address': '127.0.0.1', 'S_AutoDetect': False}
RANGES = {
    'S_ServerSaveMinutes': (10, 240), 'S_StatGain': (10, 50),
    'S_StatGainDelay': (5, 60), 'S_FloorTrapTrigger': (5, 100),
    'S_GetUnidentifiedChance': (10, 100), 'S_MonsterCharacters': (0, 3),
    'S_FoodCheck': (5, 60), 'S_GuildJoinFee': (200, 2147483647),
    'S_MaxResistance': (40, 90), 'S_DeathPayLevel': (1, 100),
    'S_DeathPayAmount': (1, 2147483647),
    'S_SpellDamageIncreaseVsMonsters': (25, 200),
    'S_SpellDamageIncreaseVsPlayers': (25, 200),
    'S_LowerReg': (0, 100), 'S_LowerMana': (0, 100),
    'S_LowerRegEnchantment': (0, 100), 'S_LowerManaEnchantment': (0, 100),
    'S_PlayerLevelMod': (.5, 3), 'S_MinGold': (0, 10000), 'S_MaxGold': (0, 10000),
    'S_LootChance': (0, 100), 'S_GetTimeBetweenQuests': (0, 240),
    'S_GetTimeBetweenArtifactQuests': (0, 20160), 'S_GetGoldCutRate': (5, 100),
    'S_QuestRewardModifier': (0, 250), 'S_SkillBoost': (0, 10), 'S_SkillGain': (0, 10),
    'S_SpecialWeaponAbilSkill': (20, 2147483647), 'S_TrainMulti': (1, 100),
    'S_Resources': (1, 100), 'S_DispelFailure': (0, 100),
    'S_BoatDecay': (5, 2147483647), 'S_HomeDecay': (30, 2147483647),
    'S_HousesPerAccount': (-1, 2147483647), 'S_PetStatGainDelay': (1, 60),
    'S_DamageToPets': (1, 2147483647), 'S_CriticalToPets': (0, 100),
    'S_Stables': (0, 20), 'S_BondDays': (0, 30),
    **{'S_Safari_' + name: (0, 100) for name in ('Sosaria', 'Lodoria', 'Serpent', 'Kuldar', 'Savaged')},
}
TOKENS = re.compile(r'/\*[\s\S]*?\*/|//[^\n]*|@"(?:[^"]|"")*"|"(?:\\.|[^"\\])*"')
FIELDS = re.compile(r'^[ \t]*public\s+static\s+(?P<type>bool|int\s*\[\s*\]|int|double|string)\s+'
                    r'(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<value>(?:"(?:\\.|[^"\\])*"|[^;])+);', re.M)


def masked(text, strings=False):
    return TOKENS.sub(lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0])
                      if m[0].startswith('/') or strings else m[0], text)


def literal(kind, expression):
    expression = expression.strip()
    if kind == 'bool' and expression in ('true', 'false'):
        return expression == 'true'
    if kind == 'int' and re.fullmatch(r'[+-]?\d+', expression):
        return int(expression)
    if kind == 'double' and re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', expression):
        value = float(expression)
        if math.isfinite(value): return value
    if kind == 'string':
        if expression == 'null': return None
        if expression.startswith('"'):
            return json.loads(expression)
    if kind == 'int[]':
        match = re.fullmatch(r'new\s*(?:int\s*)?\[\s*\]\s*\{([\s\S]*)\}', expression)
        if match:
            values = [v.strip() for v in match[1].split(',') if v.strip()]
            if all(re.fullmatch(r'[+-]?\d+', v) for v in values): return [int(v) for v in values]
    raise ValueError('Custom expression')


def fields(text, overrides=''):
    code = masked(text)
    custom = set(re.findall(r'\bMySettings\.([A-Za-z_]\w*)\s*(?:[+*/-]?=|\+\+|--)', masked(overrides, True)))
    result = []
    section, description, previous = 'Other settings', '', 0
    names = set()
    for match in FIELDS.finditer(code):
        name, kind = match['name'], re.sub(r'\s', '', match['type'])
        if name in names: raise ValueError('Ambiguous setting declarations: ' + name)
        names.add(name)
        comments = []
        for line in text[previous:match.start()].splitlines():
            heading = re.match(r'\s*//\s*\d{3}\s*-\s*(.*?)\s*/{2,}', line)
            if heading:
                section = heading[1].capitalize(); comments = []; description = ''
            elif line.lstrip().startswith('//'):
                comment = line.lstrip()[2:].strip()
                if comment and not comment.startswith('/') and not comment.startswith('public static'):
                    comments.append(comment)
        if comments: description = ' '.join(comments)
        previous = match.end()
        read_only, reason = False, ''
        try: value = literal(kind, match['value'])
        except (ValueError, TypeError):
            value, read_only, reason = text[match.start('value'):match.end('value')].strip(), True, 'Custom expression is preserved.'
        if name in custom:
            read_only, reason = True, 'Defined in your custom override file; change it there.'
            value = None  # Do not present a base value as the effective override.
        if name in NETWORK:
            value, read_only, reason = NETWORK[name], True, 'Managed by the Android launcher for local connections.'
        label = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', name.removeprefix('S_')).replace('_', ' ')
        field = {'name': name, 'label': label, 'type': kind, 'value': value, 'section': section,
                 'description': description, 'read_only': read_only, 'reason': reason}
        if name in RANGES: field.update(min=RANGES[name][0], max=RANGES[name][1])
        if name == 'S_WyrmBody': field['choices'] = [723, 12, 59]
        result.append((field, match.span('value')))
    if not result: raise ValueError('No supported Memento settings were found in ' + SETTINGS)
    return result


def revision(text, overrides):
    return hashlib.sha256((text + '\0' + overrides).encode('utf-8')).hexdigest()


def read(world, checkpoint):
    source = confined(world, SETTINGS)
    if source.is_symlink() or not source.is_file(): raise ValueError('Compile Memento before opening server settings')
    text = source.read_bytes().decode('utf-8')
    override = confined(world, OVERRIDES)
    if override.is_symlink(): raise ValueError('The settings override must be a real file')
    overrides = override.read_bytes().decode('utf-8') if override.is_file() else ''
    current = revision(text, overrides)
    undo = False
    try: undo = json.loads(Path(checkpoint).read_text())['after_revision'] == current
    except (OSError, ValueError, KeyError, TypeError): pass
    return {'revision': current, 'fields': [f for f, _ in fields(text, overrides)],
            'can_undo': undo, 'restart_required': True}, text, overrides


def checked(field, value):
    kind, name = field['type'], field['name']
    if field['read_only']: raise ValueError(name + ': ' + field['reason'])
    if kind == 'bool':
        if type(value) is not bool: raise ValueError(name + ' requires an on/off value')
        return 'true' if value else 'false'
    if kind == 'string':
        if value is not None and (not isinstance(value, str) or len(value) > 2048):
            raise ValueError(name + ' requires text of at most 2048 characters')
        return 'null' if value is None else json.dumps(value, ensure_ascii=True)
    values = value if kind == 'int[]' else [value]
    if not isinstance(values, list) or len(values) > 1000: raise ValueError(name + ' requires a list of whole numbers')
    for item in values:
        if type(item) not in (int, float) or not math.isfinite(item): raise ValueError(name + ' requires a finite number')
        if kind != 'double' and (type(item) is not int or not -2147483648 <= item <= 2147483647):
            raise ValueError(name + ' requires a 32-bit whole number')
        if not field.get('min', -math.inf) <= item <= field.get('max', math.inf):
            raise ValueError(name + ': use a value between ' + str(field['min']) + ' and ' + str(field['max']))
        if 'choices' in field and item not in field['choices']: raise ValueError(name + ': choose ' + str(field['choices']))
    if kind == 'int[]': return 'new int[] { ' + ', '.join(map(str, values)) + ' }'
    return repr(float(value)) if kind == 'double' else str(value)


def changed(text, overrides, changes):
    if not isinstance(changes, dict) or not changes: raise ValueError('Change a setting before saving')
    known = {field['name']: (field, span) for field, span in fields(text, overrides)}
    edits = []
    values = {name: item[0]['value'] for name, item in known.items()}
    for name, value in changes.items():
        if name not in known: raise ValueError('Unknown setting: ' + str(name))
        field, span = known[name]
        edits.append((*span, checked(field, value))); values[name] = value
    for low, high in (('S_MinGold', 'S_MaxGold'), ('S_MinMerchant', 'S_MaxMerchant'), ('S_SpawnMin', 'S_SpawnMax')):
        if (low in changes or high in changes) and isinstance(values.get(low), (int, float)) and isinstance(values.get(high), (int, float)):
            if values[low] > values[high]: raise ValueError(low + ' must not exceed ' + high)
    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def validate_compile(work, world, text):
    with tempfile.TemporaryDirectory(prefix='settings-check-', dir=Path(work) / 'incoming') as temporary:
        root = Path(temporary); source = root / 'Settings.cs'; source.write_text(text, encoding='utf-8')
        command = ['mcs', '-t:library', '-out:' + str(root / 'settings.dll')]
        if (Path(world) / 'WorldLinux.exe').is_file(): command.append('-r:' + str(Path(world) / 'WorldLinux.exe'))
        try:
            result = subprocess.run(command + [str(source)], capture_output=True, text=True, timeout=60)
        except FileNotFoundError as error: raise ValueError('Prepare the Mono compiler before saving settings') from error
        if result.returncode:
            raise ValueError('Settings did not compile; your original file was kept. ' + (result.stderr or result.stdout)[-2000:])


def write_text(path, text):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=path.name + '.new-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as out:
            out.write(text); out.flush(); os.fsync(out.fileno())
        os.replace(name, path); sync_directory(path.parent)
    finally: Path(name).unlink(missing_ok=True)


def save(work, world, args):
    checkpoint = Path(work) / 'backups/settings-last-change.json'
    info, text, overrides = read(world, checkpoint)
    if args.get('revision') != info['revision']: raise ValueError('Settings changed since you opened them. Reload before saving.')
    candidate = changed(text, overrides, args.get('changes'))
    validate_compile(work, world, candidate)
    write_json(checkpoint, {'before': text, 'after_revision': revision(candidate, overrides)})
    write_text(confined(world, SETTINGS), candidate)
    return {'message': 'Server settings saved. They apply on the next server start; Undo is available.'}


def undo(work, world, args):
    checkpoint = Path(work) / 'backups/settings-last-change.json'
    info, _, overrides = read(world, checkpoint)
    if not info['can_undo'] or args.get('revision') != info['revision']:
        raise ValueError('The settings have changed. Reload; the last edit cannot be undone safely.')
    data = json.loads(checkpoint.read_text()); text = data['before']
    validate_compile(work, world, text)
    write_text(confined(world, SETTINGS), text)
    checkpoint.unlink()
    return {'message': 'Previous server settings restored. They apply on the next server start.'}
