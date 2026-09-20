import json
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from uo_content import extract_zip, inspect_client, local_client_settings, swap_directory, renderer_settings
from engine import Engine


def client_fixture(root,arch=0x8664):
    exe=root/'Client/TazUO.exe';exe.parent.mkdir(parents=True)
    data=bytearray(256);data[:2]=b'MZ';struct.pack_into('<I',data,60,128);data[128:132]=b'PE\0\0';struct.pack_into('<H',data,132,arch);exe.write_bytes(data)
    exe.with_suffix('.dll').write_bytes(b'managed')
    exe.with_suffix('.runtimeconfig.json').write_text(json.dumps({'runtimeOptions':{'framework':{'name':'Microsoft.NETCore.App','version':'10.0.0'}}}))
    assets=root/'Game files';assets.mkdir()
    for name in ('tiledata.mul','map0.mul','cliloc.enu'):(assets/name).write_bytes(b'fixture')
    return exe


class ImportTests(unittest.TestCase):
    def test_complete_nested_x64_client_preserves_credentials_and_asset_path(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);exe=client_fixture(root)
            settings=exe.parent/'settings.json';settings.write_text(json.dumps({'username':'test','password':'retained','clientversion':'7.0.99.1','plugins':['custom.dll']}))
            info=inspect_client(root);self.assertEqual(info['architecture'],'x64');self.assertEqual(info['dotnet_version'],'10.0.0')
            local_client_settings(root,info)
            saved=json.loads(settings.read_text());self.assertEqual(saved['ip'],'127.0.0.1');self.assertEqual(saved['ultimaonlinedirectory'],'D:\\Game files');self.assertEqual(saved['clientversion'],'7.0.99.1');self.assertEqual(saved['password'],'retained');self.assertEqual(saved['plugins'],['custom.dll'])
            self.assertTrue(settings.with_suffix('.json.before-memento').exists())
            renderer_settings(root,info,'turnip');self.assertEqual(json.loads(settings.read_text())['force_driver'],3)
            renderer_settings(root,info,'virgl');self.assertEqual(json.loads(settings.read_text())['force_driver'],1)

    def test_existing_import_repairs_ignored_path_and_blank_version_without_reimport(self):
        for version in ('', ' ', None):
            with self.subTest(version=version),tempfile.TemporaryDirectory() as d:
                root=Path(d);exe=client_fixture(root)
                settings=exe.parent/'settings.json'
                original={'ultimaonline':'D:\\Game files', 'ultimaonlinedirectory':'C:\\old install',
                          'clientversion':version,'username':'private-user','password':'private-password','fps':50}
                settings.write_text(json.dumps(original))
                info=inspect_client(root);report=local_client_settings(root,info)
                saved=json.loads(settings.read_text())
                self.assertEqual(saved['ultimaonlinedirectory'],'D:\\Game files')
                self.assertNotIn('ultimaonline',saved)
                self.assertEqual(saved['clientversion'],'7.0.15.1')
                self.assertEqual(saved['password'],'private-password');self.assertEqual(saved['fps'],50)
                backup=settings.with_suffix('.json.before-memento')
                self.assertEqual(json.loads(backup.read_text()),original)
                local_client_settings(root,info)
                self.assertEqual(json.loads(backup.read_text()),original)
                self.assertEqual(report['version_source'],'Memento default')
                self.assertNotIn('private-',json.dumps(report))

    def test_assets_at_import_root_use_absolute_drive_and_missing_files_fail_before_write(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);exe=client_fixture(root)
            for item in (root/'Game files').iterdir():item.rename(root/item.name)
            info=inspect_client(root);self.assertEqual(info['assets'],'.')
            local_client_settings(root,info)
            settings=exe.parent/'settings.json';before=settings.read_bytes()
            self.assertEqual(json.loads(before)['ultimaonlinedirectory'],'D:\\')
            (root/'tiledata.mul').unlink()
            with self.assertRaisesRegex(ValueError,'missing: tiledata.mul'):local_client_settings(root,info)
            self.assertEqual(settings.read_bytes(),before)

    def test_asset_path_cannot_escape_import(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);client_fixture(root);info=inspect_client(root)
            info['assets']='../outside'
            with self.assertRaisesRegex(ValueError,'Unsafe file path'):local_client_settings(root,info)

    def test_x86_detected_and_missing_assets_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);client_fixture(root,0x14c);self.assertEqual(inspect_client(root)['architecture'],'x86')
            (root/'Game files/map0.mul').unlink()
            with self.assertRaisesRegex(ValueError,'map0.mul'):inspect_client(root)

    def test_traversal_case_collisions_and_symlinks_are_rejected_before_extraction(self):
        for mode in ('traversal','case','link'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);archive=root/'bad.zip';destination=root/'unpack'
                with zipfile.ZipFile(archive,'w') as z:
                    z.writestr('valid.txt','safe')
                    if mode=='traversal':z.writestr('../escape','bad')
                    elif mode=='case':z.writestr('VALID.txt','ambiguous')
                    else:
                        entry=zipfile.ZipInfo('link');entry.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(entry,'/etc/passwd')
                with self.assertRaises(ValueError):extract_zip(archive,destination)
                self.assertFalse((destination/'valid.txt').exists())

    def test_failed_client_import_does_not_replace_working_client(self):
        with tempfile.TemporaryDirectory() as d:
            engine=Engine(Path(d));engine.client.mkdir(parents=True);(engine.client/'working.txt').write_text('keep')
            archive=engine.work/'incoming/bad.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('readme.txt','incomplete')
            with self.assertRaisesRegex(ValueError,'No TazUO'):engine.import_client_zip({'file':'bad.zip'})
            self.assertEqual((engine.client/'working.txt').read_text(),'keep');engine.pool.shutdown()

    def test_directory_swap_rolls_back_failed_activation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);live=root/'live';live.mkdir();(live/'keep').write_text('yes')
            with self.assertRaises(FileNotFoundError):swap_directory(root/'missing',live)
            self.assertEqual((live/'keep').read_text(),'yes')


class WorldTests(unittest.TestCase):
    def test_server_asset_aliases_handle_windows_filename_case(self):
        with tempfile.TemporaryDirectory() as d:
            engine=Engine(Path(d));engine.world.mkdir();engine.client.mkdir(parents=True)
            (engine.client/'TILEDATA.MUL').write_bytes(b'asset')
            (engine.client/'memento-client.json').write_text(json.dumps({'assets':'.'}))
            engine.link_assets()
            self.assertEqual((engine.world/'Data/Files/tiledata.mul').read_bytes(),b'asset')
            self.assertTrue((engine.client/'TILEDATA.MUL').exists())
            engine.pool.shutdown()

    def test_backup_restore_excludes_assets_preserves_accounts_and_pre_restore_backup(self):
        with tempfile.TemporaryDirectory() as d:
            engine=Engine(Path(d));saves=engine.world/'Saves/Accounts';saves.mkdir(parents=True);(saves/'accounts.xml').write_text('original accounts')
            (engine.world/'Data/Files').mkdir(parents=True);(engine.world/'Data/Files/map0.mul').write_bytes(b'huge assets')
            (engine.world/'WorldLinux.exe').write_bytes(b'executable')
            backup=engine.backup_world({});archive=engine.work/backup['file']
            with zipfile.ZipFile(archive) as z:self.assertFalse(any('Files/map0' in n for n in z.namelist()))
            (saves/'accounts.xml').write_text('changed accounts')
            import shutil
            shutil.copy2(archive,engine.work/'incoming/restore.zip');result=engine.restore_world({'file':'restore.zip'})
            self.assertEqual((saves/'accounts.xml').read_text(),'original accounts');self.assertTrue((engine.world/'WorldLinux.exe').is_file())
            self.assertIn('Previous world backup',result['message']);self.assertEqual(len(list((engine.work/'exports').glob('*.zip'))),2);engine.pool.shutdown()

    def test_running_world_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            engine=Engine(Path(d))
            with patch.object(engine,'running',return_value=True):
                with self.assertRaisesRegex(ValueError,'stop'):engine.pull_compile({'ref':'main'})
                with self.assertRaisesRegex(ValueError,'stop'):engine.backup_world({})
                with self.assertRaisesRegex(ValueError,'stop'):engine.restore_world({'file':'backup.zip'})
            engine.pool.shutdown()


if __name__=='__main__':unittest.main()
