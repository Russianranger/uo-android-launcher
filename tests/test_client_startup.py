import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import uo_client_runner as runner


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        for name in ('SESSION','PREFIX','CLIENT','LOGS'):
            path=root/name;path.mkdir()
            patcher=patch.object(runner,name,path);patcher.start();self.addCleanup(patcher.stop)
        self.request={'mode':'client','renderer':'software','resolution':'1280x720','display_fps':60,
                      'audio':False,'client':{'self_contained':True,'executable':'TazUO.exe','settings':'settings.json','assets':'.'}}
        (runner.CLIENT/'TazUO.exe').touch()
        (runner.CLIENT/'settings.json').write_text('{}')
        for name in ('tiledata.mul','map0.mul','cliloc.enu'):(runner.CLIENT/name).touch()

    def test_prefix_upgrade_repairs_once_and_failed_check_retries(self):
        marker=runner.PREFIX/'memento-prefix-ready';marker.touch() # v0.1.0 marker
        (runner.PREFIX/'system.reg').touch()
        kernel=runner.PREFIX/'drive_c/windows/system32/kernel32.dll'
        kernel.parent.mkdir(parents=True);kernel.touch()
        supervisor=runner.Supervisor(self.request);supervisor.run=Mock()
        supervisor.prepare_prefix()
        self.assertEqual(supervisor.run.call_args_list[0].args[0][-1],'-u')
        boot_env=supervisor.run.call_args_list[0].kwargs['env']
        self.assertIn('mscoree=',boot_env['WINEDLLOVERRIDES'].split(';'))
        self.assertIn('mscoree=b',supervisor.env['WINEDLLOVERRIDES'].split(';'))
        supervisor.run.reset_mock();supervisor.prepare_prefix()
        self.assertEqual(supervisor.run.call_args_list[0].args[0][-1],'-i')
        supervisor.run.side_effect=[None,RuntimeError('Wine check failed')]
        with self.assertRaisesRegex(RuntimeError,'Wine check failed'):supervisor.prepare_prefix()
        self.assertFalse(marker.exists(),'A failed prefix check must not mark setup ready')

    def test_setup_failure_keeps_exit_output_and_reports_log(self):
        supervisor=runner.Supervisor(self.request)
        with self.assertRaisesRegex(RuntimeError,'code 7.*client-dotnet.log'):
            supervisor.run([sys.executable,'-c','print("hostfxr failed", flush=True); raise SystemExit(7)'],
                           log='client-dotnet.log',timeout=5)
        for thread in supervisor.threads:thread.join(timeout=2)
        self.assertIn('hostfxr failed',(runner.LOGS/'client-dotnet.log').read_text())

    def test_early_clean_client_exit_is_visible_and_host_tracing_enabled(self):
        supervisor=runner.Supervisor(self.request)
        supervisor.root=runner.SESSION
        (supervisor.root/'Memento.Diagnostics.dll').touch()
        supervisor.run=Mock()
        display=Mock();display.poll.return_value=None
        game=Mock();game.poll.return_value=0;game.pid=123
        supervisor.spawn=Mock(side_effect=[display,game])
        (runner.SESSION/'display.sock').touch()
        with patch.object(runner.subprocess,'run'),patch.object(runner.client_presentation,'start',return_value={}),\
             patch.object(runner.client_presentation,'start_input',return_value={}):
            with self.assertRaisesRegex(RuntimeError,'closed during startup'):
                supervisor.start()
        self.assertEqual(supervisor.status['exit_code'],0)
        env=supervisor.spawn.call_args.kwargs['env']
        self.assertIn('mscoree=b',env['WINEDLLOVERRIDES'].split(';'))
        self.assertEqual(env['DOTNET_HOST_TRACE'],'1')
        self.assertEqual(env['DOTNET_HOST_TRACEFILE'],'Z:\\logs\\client-dotnet-host.log')
        self.assertTrue(env['DOTNET_STARTUP_HOOKS'].endswith('Memento.Diagnostics.dll'))
        self.assertEqual(env['MEMENTO_MANAGED_LOG'],'Z:\\logs\\client-managed.log')
        config=json.loads((runner.CLIENT/'settings.json').read_text())
        self.assertEqual(config['ultimaonlinedirectory'],'D:\\')
        self.assertEqual(config['clientversion'],'7.0.15.1')
        self.assertEqual(config['force_driver'],1)

    def test_missing_data_stops_before_display_or_wine_and_keeps_settings(self):
        (runner.CLIENT/'tiledata.mul').unlink()
        supervisor=runner.Supervisor(self.request);supervisor.spawn=Mock()
        with self.assertRaisesRegex(ValueError,'missing: tiledata.mul'):supervisor.start()
        supervisor.spawn.assert_not_called()
        self.assertEqual((runner.CLIENT/'settings.json').read_text(),'{}')

    def test_display_readiness_is_published_after_presentation_and_input(self):
        supervisor=runner.Supervisor(self.request);supervisor.run=Mock()
        display=Mock();display.poll.return_value=None
        supervisor.spawn=Mock(return_value=display)
        (runner.SESSION/'display.sock').touch()
        seen=[]
        def presentation(s):
            seen.append('presentation')
            self.assertFalse(s.status['display_ready'])
            return {'presentation_active':'native_surface'}
        def controls(s):
            seen.append('input')
            self.assertFalse(s.status['display_ready'])
            self.assertEqual(s.status['presentation_active'],'native_surface')
            return {'pointer_transport':'relative_xtest'}
        def prefix():
            self.assertEqual(seen,['presentation','input'])
            # The real method marks the display ready only after these helpers.
            runner.Supervisor.prepare_prefix(supervisor)
            self.assertTrue(supervisor.status['display_ready'])
            self.assertEqual(supervisor.status['pointer_transport'],'relative_xtest')
            raise RuntimeError('test finished before client spawn')
        supervisor.prepare_prefix=prefix
        with patch.object(runner.subprocess,'run'),patch.object(runner.client_presentation,'start',side_effect=presentation),\
             patch.object(runner.client_presentation,'start_input',side_effect=controls):
            with self.assertRaisesRegex(RuntimeError,'test finished'):supervisor.start()
        self.assertEqual(supervisor.spawn.call_count,1)

    def test_dotnet_preflight_enables_builtin_loader_without_losing_renderer_overrides(self):
        for renderer,dlls in (('turnip','d3d11,dxgi=b'),('software','d3d11,dxgi=b')):
            with self.subTest(renderer=renderer):
                supervisor=runner.Supervisor(dict(self.request,renderer=renderer))
                setup=supervisor.setup_environment()
                managed=supervisor.dotnet_environment('client-dotnet-check-host.log')
                self.assertIn('mscoree=',setup['WINEDLLOVERRIDES'].split(';'))
                self.assertIn('mscoree=b',managed['WINEDLLOVERRIDES'].split(';'))
                for env in (setup,managed):self.assertIn(dlls,env['WINEDLLOVERRIDES'].split(';'))
                self.assertEqual(managed['FNA3D_FORCE_DRIVER'],'Vulkan' if renderer=='turnip' else 'OpenGL')

    def test_layout_opt_out_and_invalid_resolution_preserve_profiles(self):
        profile=runner.CLIENT/'Data/Profiles/default.json';profile.parent.mkdir(parents=True)
        profile.write_text('{"game_window_size":{"X":900,"Y":600}}')
        supervisor=runner.Supervisor(self.request)
        supervisor.prepare_client_configuration()
        self.assertEqual(json.loads(profile.read_text())['game_window_size'],{'X':900,'Y':600})
        before=(runner.CLIENT/'settings.json').read_bytes()
        supervisor.request.update(gump_space=True,resolution='800x600')
        with self.assertRaisesRegex(ValueError,'requires a 1280x720'):supervisor.prepare_client_configuration()
        self.assertEqual((runner.CLIENT/'settings.json').read_bytes(),before)

    def test_requested_layout_and_binary_report_are_in_support_diagnostics(self):
        supervisor=runner.Supervisor(dict(self.request,gump_space=True,renderer='turnip'))
        supervisor.prepare_client_configuration()
        report=json.loads((runner.LOGS/'client-config.json').read_text())
        self.assertEqual(report['layout']['world_viewport'],[1098,720])
        self.assertEqual(report['layout']['window'],[1280,720])
        self.assertEqual(report['graphics_driver'],'Vulkan')

    def test_main_keeps_failure_in_status_after_cleanup(self):
        (runner.SESSION/'request.json').write_text(json.dumps(self.request))
        with patch.object(runner.Supervisor,'start',side_effect=RuntimeError('CoreCLR startup failed')),\
             patch.object(runner.subprocess,'run'):
            with self.assertRaisesRegex(RuntimeError,'CoreCLR startup failed'):runner.main()
        for path in (runner.SESSION/'status.json',runner.LOGS/'client-state.json'):
            state=json.loads(path.read_text())
            self.assertEqual(state['phase'],'error');self.assertEqual(state['error'],'CoreCLR startup failed')
            self.assertFalse(state['display_ready'])


if __name__=='__main__':unittest.main()
