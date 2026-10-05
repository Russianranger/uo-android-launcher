import json
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from engine import Engine
import realm_sources
import engine as engine_module
from uo_content import REPOSITORY


def source_fixture(world):
    files = {
        'Source/Tools/compile-world-linux.sh':'mcs -d:MONO',
        'Source/System/icon.ico':'icon', 'Source/System/Core.cs':'core',
        'Source/Scripts/System/Misc/ServerList.cs':
            'public static readonly string Address = MySettings.S_Address;\n'
            'public static readonly bool AutoDetect = MySettings.S_AutoDetect;',
        'Source/Scripts/System/Misc/SocketOptions.cs':'new IPEndPoint( IPAddress.Any, MySettings.S_Port )',
        'Source/Scripts/Feature.cs':'new source',
        'Info/Scripts/Settings.cs':'retained settings',
        'Data/System/CFG/Assemblies.cfg':'System.dll\n#comment\nSystem.Core.dll',
        'Saves/Accounts/accounts.xml':'new defaults', 'Backups/old.txt':'source backup',
    }
    for name, content in files.items():
        path=world/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content)
    return world


def zip_source(root, target, prefix=''):
    with zipfile.ZipFile(target,'w') as archive:
        for file in root.rglob('*'):
            if file.is_file(): archive.write(file,prefix+str(file.relative_to(root)))


class RealmSourceTests(unittest.TestCase):
    def engine(self, root):
        engine=Engine(root/'work'); self.addCleanup(engine.pool.shutdown); return engine

    def fake_compiler(self, calls):
        def run(args, cwd=None, **kwargs):
            calls.append((args,cwd))
            for arg in args:
                if arg.startswith('-out:'): Path(arg[5:]).write_bytes(b'compiled')
        return run

    def test_fresh_default_and_legacy_selection_preserve_previous_repository(self):
        self.assertEqual(realm_sources.selection({})['repository'],realm_sources.UPSTREAM_REPOSITORY)
        previous={'repository':REPOSITORY,'ref':'stable','source':'fork'}
        self.assertEqual(realm_sources.selection({'ref':'main'},previous)['repository'],REPOSITORY)
        self.assertEqual(realm_sources.selection({},previous)['ref'],'stable')
        self.assertEqual(realm_sources.selection({'source':'upstream'},previous)['ref'],'main')
        custom=realm_sources.selection({'source':'custom','repository':'https://git.example.org/team/subgroup/world.git','ref':'release/v2'})
        self.assertEqual(custom['repository'],'https://git.example.org/team/subgroup/world.git')
        self.assertEqual(custom['ref'],'release/v2')
        with self.assertRaisesRegex(ValueError,'explicitly'):realm_sources.selection({}, {'source':'zip'})

    def test_additive_settings_migration_preserves_values_custom_code_and_brace_strings(self):
        old='namespace Server { public static class MySettings {\n public static bool Existing = true;\n public static string Name = "a } brace";\n public static double Custom = Helpers.GetValue();\n } }'
        new='namespace Server { public static class MySettings {\n public static bool Existing = false;\n public static bool S_AllowTravelToSpecialPlaces = false;\n public static string Name = "default";\n public static double Custom = 9.0;\n } }'
        updated,added=realm_sources.add_missing_settings(old,new)
        self.assertEqual(added,['S_AllowTravelToSpecialPlaces'])
        self.assertIn('Existing = true',updated);self.assertIn('Name = "a } brace"',updated)
        self.assertIn('Custom = Helpers.GetValue()',updated);self.assertIn('S_AllowTravelToSpecialPlaces = false;',updated)
        self.assertTrue(updated.endswith('} }'))
        self.assertEqual(realm_sources.add_missing_settings(updated,new),(updated,[]))
        with self.assertRaisesRegex(ValueError,'custom MySettings'):realm_sources.add_missing_settings(old.replace('class MySettings','class Unsupported'),new)

    def test_empty_save_and_backup_folders_remain_empty_across_compile(self):
        for missing in (False,True):
            with self.subTest(missing=missing),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);engine=self.engine(root);source_fixture(root/'fixture')
                zip_source(root/'fixture',engine.work/'incoming/server.zip');engine.import_server_zip({'file':'server.zip'})
                engine.world.mkdir()
                if not missing:(engine.world/'Saves').mkdir();(engine.world/'Backups').mkdir()
                calls=[]
                with patch('engine.shutil.which',return_value='/usr/bin/mcs'),patch.object(engine,'command',side_effect=self.fake_compiler(calls)):
                    engine.compile_server({})
                self.assertEqual(list((engine.world/'Saves').iterdir()),[])
                self.assertEqual(list((engine.world/'Backups').iterdir()),[])

    def test_data_files_survive_update_when_no_imported_client_can_relink_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);engine=self.engine(root);source_fixture(root/'fixture')
            zip_source(root/'fixture',engine.work/'incoming/server.zip');engine.import_server_zip({'file':'server.zip'})
            assets=engine.world/'Data/Files';assets.mkdir(parents=True);(assets/'tiledata.mul').write_bytes(b'kept assets')
            with patch('engine.shutil.which',return_value='/usr/bin/mcs'),patch.object(engine,'command',side_effect=self.fake_compiler([])):
                engine.compile_server({})
            self.assertEqual((engine.world/'Data/Files/tiledata.mul').read_bytes(),b'kept assets')

    def test_unsafe_repository_urls_and_refs_fail_without_commands(self):
        for value in ('file:///etc/passwd','ssh://git@github.com/owner/repo','ext::command',
                      'https://user:password@github.com/owner/repo','https://github.com/owner/repo?token=a',
                      'https://github.com/owner/repo#main','https://github.com/owner/../repo',
                      'https://github.com/owner/repo%2f..','https://github.com/owner/repo\n--upload-pack=evil',
                      'https://github.com.evil/owner//repo','https://github.com:bad/owner/repo'):
            with self.subTest(value=value),self.assertRaises(ValueError):realm_sources.repository_url(value)
        for value in ('--upload-pack=evil','../main','main//child','main/','main.lock','main;touch bad','main\nother'):
            with self.subTest(value=value),self.assertRaises(ValueError):realm_sources.checked_ref(value)
        with tempfile.TemporaryDirectory() as folder:
            engine=self.engine(Path(folder))
            with patch('engine.shutil.which',return_value='/usr/bin/mcs'),patch.object(engine,'command') as command:
                with self.assertRaises(ValueError):engine.pull_compile({'source':'custom','repository':'file:///etc/passwd'})
                command.assert_not_called()

    def test_offline_import_accepts_repo_wrappers_and_flat_world_before_mono(self):
        for prefix in ('ultima-memento-main/World/','release/server/World/',''):
            with self.subTest(prefix=prefix),tempfile.TemporaryDirectory() as folder:
                root=Path(folder); engine=self.engine(root); source_fixture(root/'fixture')
                archive=engine.work/'incoming/server.zip'; zip_source(root/'fixture',archive,prefix)
                with patch('engine.shutil.which',return_value=None),patch.object(engine,'command') as command:
                    result=engine.import_server_zip({'file':'server.zip'}); command.assert_not_called()
                    self.assertFalse(engine.world.exists())
                    self.assertEqual(result['server_source']['source'],'zip')
                    self.assertRegex(result['server_source']['archive_sha256'],r'^[a-f0-9]{64}$')
                    self.assertTrue((engine.server_source/'World/Source/System/Core.cs').is_file())
                    self.assertEqual(engine.state()['server_source']['source'],'zip')
                    with self.assertRaisesRegex(ValueError,'Mono'):engine.compile_server({})
                engine2=self.engine(root)
                self.assertEqual(engine2.state()['server_source'],result['server_source'])

    def test_import_ignores_embedded_repository_claim_and_build_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); engine=self.engine(root); fixture=source_fixture(root/'fixture')
            (fixture/'memento-build.json').write_text('{"repository":"https://github.com/evil/claimed.git"}')
            (fixture/'realm-source.json').write_text('{"source":"upstream"}')
            zip_source(fixture,engine.work/'incoming/server.zip','World/')
            result=engine.import_server_zip({'file':'server.zip'})
            self.assertNotIn('repository',result['server_source']);self.assertNotIn('revision',result['server_source'])

    def test_unsafe_or_ambiguous_import_preserves_live_world_and_prepared_source(self):
        for invalid in ('traversal','symlink','case','multiple','unsupported','network'):
            with self.subTest(invalid=invalid),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);engine=self.engine(root);engine.world.mkdir();(engine.world/'working').write_text('keep')
                engine.server_source.mkdir();(engine.server_source/'keep').write_text('source')
                fixture=source_fixture(root/'fixture');archive=engine.work/'incoming/server.zip'
                if invalid=='network':(fixture/'Source/Scripts/System/Misc/SocketOptions.cs').write_text('changed upstream')
                if invalid=='unsupported':(fixture/'Source/Tools/compile-world-linux.sh').unlink()
                zip_source(fixture,archive,'World/')
                with zipfile.ZipFile(archive,'a') as z:
                    if invalid=='traversal':z.writestr('../escape','bad')
                    elif invalid=='case':z.writestr('World/Source/System/CORE.cs','case')
                    elif invalid=='symlink':
                        item=zipfile.ZipInfo('link');item.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(item,'/etc/passwd')
                    elif invalid=='multiple':
                        for file in fixture.rglob('*'):
                            if file.is_file():z.write(file,'Other/'+str(file.relative_to(fixture)))
                with self.assertRaises(ValueError):engine.import_server_zip({'file':'server.zip'})
                self.assertEqual((engine.world/'working').read_text(),'keep')
                self.assertEqual((engine.server_source/'keep').read_text(),'source')

    def test_compile_preserves_current_world_settings_custom_scripts_data_and_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);engine=self.engine(root);source_fixture(root/'fixture')
            zip_source(root/'fixture',engine.work/'incoming/server.zip','World/')
            engine.import_server_zip({'file':'server.zip'})
            source_fixture(engine.world)
            for name,value in {'Saves/Accounts/accounts.xml':'private accounts','Info/Scripts/Settings.cs':'user settings',
                               'Info/Scripts/Custom.cs':'user script','Data/custom.dat':'local data','Backups/snapshot.txt':'snapshot'}.items():
                path=engine.world/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
            engine.client.mkdir(parents=True);(engine.client/'tiledata.mul').write_bytes(b'assets')
            (engine.client/'memento-client.json').write_text('{"assets":"."}')
            calls=[]
            with patch('engine.shutil.which',return_value='/usr/bin/mcs'),patch.object(engine,'command',side_effect=self.fake_compiler(calls)):
                result=engine.compile_server({})
            self.assertTrue((engine.world/'WorldLinux.exe').is_file())
            for name,value in {'Saves/Accounts/accounts.xml':'private accounts','Info/Scripts/Settings.cs':'user settings',
                               'Info/Scripts/Custom.cs':'user script','Data/custom.dat':'local data','Backups/snapshot.txt':'snapshot'}.items():
                self.assertEqual((engine.world/name).read_text(),value)
            self.assertEqual((engine.world/'Data/Files/tiledata.mul').read_bytes(),b'assets')
            self.assertIn('-d:MONO',calls[0][0]);self.assertIn('-d:MONO',calls[1][0])
            self.assertIn('IPAddress.Loopback, 2593',(engine.world/'Source/Scripts/System/Misc/SocketOptions.cs').read_text())
            self.assertTrue((engine.world/'Source/Scripts/System/Misc/MementoAndroidControl.cs').is_file())
            self.assertEqual(json.loads((engine.world/'memento-build.json').read_text())['source'],'zip')
            self.assertGreater(result['server_source']['imported_at'],0)
            self.assertEqual(len(list((engine.work/'exports').glob('*.zip'))),1)

    def test_script_or_asset_failure_does_not_activate_new_world(self):
        for failure in ('scripts','assets'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);engine=self.engine(root);source_fixture(root/'fixture')
                zip_source(root/'fixture',engine.work/'incoming/server.zip');engine.import_server_zip({'file':'server.zip'})
                engine.world.mkdir();(engine.world/'working').write_text('keep')
                calls=[]
                def run(args,**kwargs):
                    if '-t:library' in args and failure=='scripts': raise RuntimeError('scripts failed')
                    self.fake_compiler(calls)(args,**kwargs)
                with patch('engine.shutil.which',return_value='/usr/bin/mcs'),patch.object(engine,'command',side_effect=run),patch.object(engine,'link_assets',side_effect=RuntimeError('assets failed') if failure=='assets' else None):
                    with self.assertRaises(RuntimeError):engine.compile_server({})
                self.assertEqual((engine.world/'working').read_text(),'keep')
                self.assertEqual(len(list((engine.work/'exports').glob('*.zip'))),0)
                self.assertTrue((engine.server_source/'World/Info/Scripts/Settings.cs').is_file())

    def test_source_activation_failure_rolls_back_compiled_world(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);engine=self.engine(root);source_fixture(root/'fixture')
            zip_source(root/'fixture',engine.work/'incoming/server.zip');engine.import_server_zip({'file':'server.zip'})
            before=engine.state()['server_source']
            source_fixture(engine.world);(engine.world/'Saves/Accounts/accounts.xml').write_text('old accounts')
            prepared=engine.work/'source-staging';source_fixture(prepared/'World')
            metadata={'format':1,'source':'zip','archive_sha256':'b'*64}
            original_swap=engine_module.swap_directory
            def swap(staging,live):
                if live==engine.server_source:raise OSError('source activation failed')
                original_swap(staging,live)
            with patch('engine.shutil.which',return_value='/usr/bin/mcs'),patch.object(engine,'command',side_effect=self.fake_compiler([])),patch('engine.swap_directory',side_effect=swap):
                with self.assertRaisesRegex(OSError,'source activation'):engine._compile_server(prepared,metadata,activate_source=True)
            self.assertEqual((engine.world/'Saves/Accounts/accounts.xml').read_text(),'old accounts')
            self.assertEqual(engine.state()['server_source'],before)
            self.assertFalse((engine.world/'WorldLinux.exe').exists())

    def test_online_switch_uses_matching_origin_and_updates_provenance_after_compile(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);engine=self.engine(root);fixture=source_fixture(root/'fixture');calls=[];git_calls=[]
            def command(args,**kwargs):
                if args[0]=='git':
                    git_calls.append(args)
                    if 'clone' in args: (Path(args[-1])/'.git').mkdir(parents=True)
                    if 'archive' in args:
                        target=next(a[9:] for a in args if a.startswith('--output='));zip_source(fixture,Path(target),'World/')
                else:self.fake_compiler(calls)(args,**kwargs)
            selected_repository=['']
            def output(args,**kwargs):
                if 'config' in args:return selected_repository[0]+'\n'
                return 'a'*40+'\n'
            with patch('engine.shutil.which',return_value='/usr/bin/mcs'),patch.object(engine,'command',side_effect=command),patch('engine.subprocess.check_output',side_effect=output):
                for kind,repository in (('upstream',realm_sources.UPSTREAM_REPOSITORY),('fork',REPOSITORY),('custom','https://git.example.org/team/server.git'),('custom','https://git.example.org/team/Server.git')):
                    selected_repository[0]=repository
                    engine.pull_compile({'source':kind,'repository':repository,'ref':'main'})
                    self.assertEqual(engine.state()['build']['repository'],repository)
                    self.assertEqual(engine.state()['server_source']['source'],kind)
            clones=[args for args in git_calls if 'clone' in args]
            self.assertEqual(len({args[-1] for args in clones}),4)
            self.assertEqual([args[-2] for args in clones],[realm_sources.UPSTREAM_REPOSITORY,REPOSITORY,'https://git.example.org/team/server.git','https://git.example.org/team/Server.git'])

    def test_legacy_build_provenance_retained_and_offline_provenance_blocks_implicit_pull(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);engine=self.engine(root);engine.world.mkdir()
            (engine.world/'memento-build.json').write_text(json.dumps({'repository':REPOSITORY,'ref':'legacy','revision':'b'*40}))
            self.assertEqual(engine.selected_server_source()['source'],'fork')
            self.assertEqual(realm_sources.selection({},engine.selected_server_source())['repository'],REPOSITORY)
            engine.server_source.mkdir();(engine.server_source/'realm-source.json').write_text(json.dumps({'format':1,'source':'zip','archive_sha256':'a'*64}))
            with patch('engine.shutil.which',return_value='/usr/bin/mcs'),patch.object(engine,'command') as command:
                with self.assertRaisesRegex(ValueError,'explicitly'):engine.pull_compile({'ref':'main'})
                command.assert_not_called()

    def test_stopped_guard_and_missing_source(self):
        with tempfile.TemporaryDirectory() as folder:
            engine=self.engine(Path(folder))
            with patch('engine.shutil.which',return_value='/usr/bin/mcs'):
                with self.assertRaisesRegex(ValueError,'Import'):engine.compile_server({})
            with patch.object(engine,'running',return_value=True):
                for operation,args in ((engine.import_server_zip,{'file':'server.zip'}),(engine.compile_server,{})):
                    with self.assertRaisesRegex(ValueError,'stop'):operation(args)


if __name__=='__main__': unittest.main()
