"""Qualify real offline source compilation and a retained fork-to-upstream world.

Run after installing mono-devel:
    python3 tests/verify_realm_sources_compile.py <fork-checkout> <upstream-checkout>

Both checkouts are pinned below. git archive ignores outputs left by the older
server qualification, so the ZIP-import path receives pristine source files.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from engine import Engine
import server_settings


FORK_REVISION = '916d1ec666376ef44366c986befa3200deb93eb0'
UPSTREAM_REVISION = '3d3cb7b12617d98d63d117ea5d04a76385fa160a'


def check(condition, message):
    if not condition: raise AssertionError(message)


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        while chunk := source.read(1024*1024): digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root):
    root = Path(root)
    return {str(path.relative_to(root)):file_digest(path)
            for path in sorted(root.rglob('*')) if path.is_file()}


def archive_checkout(checkout, expected, target, invalid_script=False):
    revision = subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
    check(revision==expected, 'Source checkout must be pinned at '+expected+'; found '+revision)
    subprocess.run(['git','-C',str(checkout),'archive','--format=zip','--output='+str(target),'HEAD','World'],check=True)
    if invalid_script:
        with zipfile.ZipFile(target,'a') as archive:
            archive.writestr('World/Source/Scripts/DeliberateCompileFailure.cs',
                             'namespace Server { public class DeliberateCompileFailure { THIS IS INVALID CSHARP } }')


class VerifiedEngine(Engine):
    """Observe the live deployment while each real Mono compilation runs."""
    def __init__(self, work):
        super().__init__(work)
        self.expected_live = None
        self.compiler_calls = []

    def capture_live(self):
        if not self.world.exists(): return None
        return {'core':file_digest(self.world/'WorldLinux.exe'),
                'build':(self.world/'memento-build.json').read_bytes(),
                'saves':tree_digest(self.world/'Saves')}

    def assert_live_unchanged(self):
        check(self.capture_live()==self.expected_live,
              'A candidate modified the live installation before all script checks completed')

    def command(self, args, **kwargs):
        if args[0]=='mcs':
            self.assert_live_unchanged()
            self.compiler_calls.append(tuple(args))
        try:
            return super().command(args, **kwargs)
        finally:
            if args[0]=='mcs': self.assert_live_unchanged()


def checked_build(engine, expected_added):
    build = engine.state()['build']
    scripts = list((engine.world/'Source/Scripts').rglob('*.cs')) + list((engine.world/'Info/Scripts').rglob('*.cs'))
    check(build['source']=='zip', 'Offline builds must record ZIP provenance')
    check(build['archive_sha256']==engine.state()['server_source']['archive_sha256'],
          'Compiled source provenance must match the imported archive')
    check(build['scripts_checked']==len(scripts) and len(scripts)>1000,
          'The backend must compile every real game script before activation')
    check(build['settings_added']==expected_added, 'Unexpected settings migration: '+str(build['settings_added']))
    check((engine.world/'Source/Scripts/System/Misc/MementoAndroidControl.cs').is_file(),
          'The save/stop control bridge must be compiled with the game scripts')
    for name in ('memento-scripts-check.rsp','memento-scripts-check.dll'):
        check(not (engine.world/name).exists(), 'Temporary compiler verification files must not be deployed')
    print('Verified core and '+str(len(scripts))+' game scripts from archive '+build['archive_sha256'][:12]+'.')


def qualify(fork, upstream):
    if not shutil.which('mcs'): raise RuntimeError('Install mono-devel before running real Realm source qualification')
    with tempfile.TemporaryDirectory(prefix='realm-source-qualification-') as temporary:
        engine = VerifiedEngine(Path(temporary)/'work')
        try:
            initial = engine.work/'incoming/fork.zip'
            archive_checkout(fork,FORK_REVISION,initial)
            engine.import_server_zip({'file':initial.name})
            check(not engine.world.exists(), 'Import must stage source without activating a world')
            engine.compile_server({})
            checked_build(engine,[])

            settings_info,_,_ = server_settings.read(engine.world,engine.work/'backups/settings-last-change.json')
            server_settings.save(engine.work,engine.world,{
                'revision':settings_info['revision'],
                'changes':{'S_ServerName':'Retained Android "Realm"','S_ServerSaveMinutes':45.5,
                           'S_UnidentifiedItem_GuaranteedItemChecks':[0,35,65]}})
            custom = engine.world/'Info/Scripts/RetainedAndroidCustom.cs'
            custom.write_text('namespace Server.Misc { public static class RetainedAndroidCustom { '
                              'public const string Marker = "Retained custom script"; } }\n')
            custom_bytes = custom.read_bytes()
            sentinel = engine.world/'Saves/Android-qualification.txt'
            sentinel.write_text('Retained player world\n')
            saves = tree_digest(engine.world/'Saves')
            data_sentinel = engine.world/'Data/Android-qualification.txt'
            data_sentinel.write_text('Retained local data\n')
            shutil.rmtree(engine.world/'Backups',ignore_errors=True)
            (engine.world/'Backups').mkdir()
            engine.expected_live = engine.capture_live()

            update = engine.work/'incoming/upstream.zip'
            archive_checkout(upstream,UPSTREAM_REVISION,update)
            engine.import_server_zip({'file':update.name})
            engine.assert_live_unchanged()
            engine.compile_server({})
            checked_build(engine,['S_AllowTravelToSpecialPlaces'])
            info,_,_ = server_settings.read(engine.world,engine.work/'backups/settings-last-change.json')
            values = {field['name']:field['value'] for field in info['fields']}
            check(values['S_ServerName']=='Retained Android "Realm"', 'Existing Realm name was replaced')
            check(values['S_ServerSaveMinutes']==45.5, 'Existing numeric setting was replaced')
            check(values['S_UnidentifiedItem_GuaranteedItemChecks']==[0,35,65], 'Existing array setting was replaced')
            check(values['S_AllowTravelToSpecialPlaces'] is False, 'Missing upstream literal default was not added')
            check(custom.read_bytes()==custom_bytes, 'Existing custom Info script was replaced')
            check(tree_digest(engine.world/'Saves')==saves, 'Existing save records changed during source update')
            check(data_sentinel.read_text()=='Retained local data\n', 'Existing Data files were replaced')
            check(list((engine.world/'Backups').iterdir())==[], 'Empty Backups received source defaults')
            check(len(list((engine.work/'exports').glob('*.zip')))==1, 'Update must back up the previous world')
            print('Verified fork-to-upstream upgrade retained settings, custom scripts, save records and Data.')

            # A real Mono error in any candidate game script must keep the
            # already compiled deployment and its world records unchanged.
            engine.expected_live = engine.capture_live()
            invalid = engine.work/'incoming/invalid-scripts.zip'
            archive_checkout(upstream,UPSTREAM_REVISION,invalid,invalid_script=True)
            engine.import_server_zip({'file':invalid.name})
            try:
                engine.compile_server({})
            except RuntimeError as error:
                check('Command failed' in str(error), 'Expected a real Mono compiler rejection')
            else:
                raise AssertionError('Invalid game script was accepted')
            engine.assert_live_unchanged()
            check(len(engine.compiler_calls)==6, 'Expected core and complete script checks for all three candidates')
            check(all('-d:MONO' in args for args in engine.compiler_calls), 'Mono defines were omitted')
            print('Verified real game-script compilation failure preserved the installed core and world.')
        except BaseException:
            log = engine.work/'logs/build.log'
            if log.is_file(): print(log.read_text(errors='replace'),file=sys.stderr)
            raise
        finally:
            engine.pool.shutdown()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fork_checkout',type=Path)
    parser.add_argument('upstream_checkout',type=Path)
    args=parser.parse_args()
    qualify(args.fork_checkout.resolve(),args.upstream_checkout.resolve())
