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
        identity=patch.object(runner.client_runtime,'inspect',return_value={'runtime':runner.RUNTIME_ID})
        identity.start();self.addCleanup(identity.stop)
        root=Path(self.temp.name)
        for name in ('SESSION','PREFIX','CLIENT','LOGS'):
            path=root/name;path.mkdir()
            patcher=patch.object(runner,name,path);patcher.start();self.addCleanup(patcher.stop)
        self.request={'runtime_backend':runner.RUNTIME_ID,'mode':'client','renderer':'software','resolution':'1280x720','display_fps':60,
                      'audio':False,'client':{'self_contained':True,'executable':'TazUO.exe','settings':'settings.json','assets':'.'}}
        for name in ('system.reg','userdef.reg','user.reg'):
            (runner.PREFIX/name).write_text('WINE REGISTRY Version 2\n\n#arch=win64\n\n[Software]\n')
        (runner.CLIENT/'TazUO.exe').touch()
        (runner.CLIENT/'settings.json').write_text('{}')
        for name in ('tiledata.mul','map0.mul','cliloc.enu'):(runner.CLIENT/name).touch()

    def test_fex_removes_old_translator_and_jit_overrides(self):
        with patch.dict(runner.os.environ,{'BOX64_DYNAREC_CALLRET':'2',
                         'FEX_TSOENABLED':'0','DOTNET_EnableWriteXorExecute':'0',
                         'COMPlus_TieredCompilation':'0'}):
            for renderer in ('turnip','virgl','software'):
                supervisor=runner.Supervisor(dict(self.request,renderer=renderer))
                game=supervisor.client_environment()
                for env in (game,supervisor.setup_environment(),supervisor.dotnet_environment('check.log')):
                    self.assertFalse(any(key.startswith(('BOX64_','FEX_','COMPlus_')) for key in env))
                    self.assertNotIn('DOTNET_EnableWriteXorExecute',env)
                    self.assertNotIn('DOTNET_TieredCompilation',env)
                self.assertEqual(runner.WINE,['/opt/wine/bin/wine'])
                report=json.loads((runner.LOGS/'client-compatibility.json').read_text())
                self.assertEqual(report['runtime_backend'],'fex-arm64ec-1')

    def test_legacy_preferences_cannot_enable_fex_experiments(self):
        request=dict(self.request,client_memory_compatibility=True,managed_diagnostics=True,
                     render_trace=True,sdl_graphics_fixes=True)
        request.pop('runtime_backend')
        supervisor=runner.Supervisor(request)
        self.assertFalse(supervisor.status['managed_diagnostics'])
        supervisor.prepare_client_configuration()
        self.assertFalse(supervisor.status['render_trace']['active'])
        self.assertFalse(supervisor.request['sdl_graphics_fixes'])
        self.assertNotIn('DOTNET_STARTUP_HOOKS',supervisor.client_environment())

    def test_render_trace_only_preloads_helper_for_a_verified_patch(self):
        supervisor=runner.Supervisor(self.request)
        supervisor.root=runner.SESSION
        self.assertNotIn('DOTNET_STARTUP_HOOKS',supervisor.client_environment())
        supervisor.status['render_trace']={'active':True}
        env=supervisor.client_environment()
        self.assertEqual(env['MEMENTO_RENDER_TRACE'],'1')
        self.assertIn('render-progress.bin',env['MEMENTO_RENDER_PROGRESS'])
        self.assertEqual((runner.SESSION/'render-progress.bin').stat().st_size,1056)
        self.assertIn('Memento.RenderTrace.dll',env['DOTNET_STARTUP_HOOKS'])
        self.assertNotIn('DOTNET_STARTUP_HOOKS',supervisor.setup_environment())
        supervisor.status['managed_diagnostics']=True
        (supervisor.root/'Memento.Diagnostics.dll').touch()
        self.assertIn(';',supervisor.client_environment()['DOTNET_STARTUP_HOOKS'])
        with patch.object(runner,'prepare_render_progress',side_effect=OSError('Read-only session')):
            failed_observer=supervisor.client_environment()
        self.assertNotIn('MEMENTO_RENDER_PROGRESS',failed_observer)
        self.assertEqual(failed_observer['MEMENTO_RENDER_TRACE'],'1')

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

    def test_setup_kill_does_not_relabel_old_game_crash_as_current(self):
        for name in ('client-wine.log','client-managed.log','client-dotnet-host.log','client-compatibility.json','client-health.log'):
            (runner.LOGS/name).write_text('previous game crash')
        supervisor=runner.Supervisor(dict(self.request,client_memory_compatibility=True))
        display=Mock();display.poll.return_value=None
        killed=Mock();killed.poll.return_value=-9;killed.returncode=-9
        supervisor.spawn=Mock(side_effect=[display,killed])
        (runner.SESSION/'display.sock').touch()
        real_run=supervisor.run
        def run(args,**kwargs):
            if 'wineboot' in args:return real_run(args,**kwargs)
        supervisor.run=Mock(side_effect=run)
        with patch.object(runner.subprocess,'run'),patch.object(runner.client_presentation,'start',return_value={}),\
             patch.object(runner.client_presentation,'start_input',return_value={}):
            with self.assertRaisesRegex(RuntimeError,'SIGKILL.*before the client started'):
                supervisor.start()
        state=json.loads((runner.LOGS/'client-state.json').read_text())
        self.assertFalse(state['client_started'])
        self.assertEqual(state['setup_exit_code'],-9)
        self.assertEqual(state['setup_log'],'client-prefix.log')
        self.assertTrue(state['attempt_started_utc'].endswith('Z'))
        self.assertEqual(supervisor.spawn.call_count,2) # display and wineboot, no game
        for name in ('client-wine.log','client-managed.log','client-dotnet-host.log','client-compatibility.json','client-health.log'):
            self.assertFalse((runner.LOGS/name).exists())
            from log_retention import history
            self.assertEqual(history(runner.LOGS/name,1).read_text(),'previous game crash')

    def test_managed_hook_is_explicit_opt_in_and_game_only(self):
        with patch.dict(runner.os.environ,{'DOTNET_STARTUP_HOOKS':'inherited.dll','MEMENTO_MANAGED_LOG':'inherited.log'}):
            for option in (None, False, True):
                request=dict(self.request)
                if option is not None:request['managed_diagnostics']=option
                supervisor=runner.Supervisor(request)
                supervisor.root=runner.SESSION
                hook=supervisor.root/'Memento.Diagnostics.dll'
                hook.unlink(missing_ok=True)
                if option is True:
                    with self.assertRaisesRegex(RuntimeError,'diagnostics component is missing'):supervisor.client_environment()
                    hook.touch()
                env=supervisor.client_environment()
                if option is True:
                    self.assertTrue(env['DOTNET_STARTUP_HOOKS'].endswith('Memento.Diagnostics.dll'))
                    self.assertEqual(env['MEMENTO_MANAGED_LOG'],'Z:\\logs\\client-managed.log')
                else:
                    self.assertNotIn('DOTNET_STARTUP_HOOKS',env)
                    self.assertNotIn('MEMENTO_MANAGED_LOG',env)
                for baseline in (supervisor.env,supervisor.setup_environment(),supervisor.dotnet_environment('check.log')):
                    self.assertNotIn('DOTNET_STARTUP_HOOKS',baseline)
                report=json.loads((runner.LOGS/'client-compatibility.json').read_text())
                self.assertEqual(report['managed_diagnostics'],option is True)
        desktop=runner.Supervisor(dict(self.request,mode='desktop',managed_diagnostics=True))
        self.assertFalse(desktop.status['managed_diagnostics'])
        with self.assertRaisesRegex(ValueError,'Invalid managed diagnostics'):
            runner.Supervisor(dict(self.request,managed_diagnostics='false'))

    def test_native_crash_tail_survives_verbose_log_rotation(self):
        supervisor=runner.Supervisor(self.request)
        with self.assertRaisesRegex(RuntimeError,'code 2'):
            supervisor.run([sys.executable,'-c',
                'import sys; sys.stdout.write("x"*(9*1024*1024)); print("\\nFatal error.\\n0xC0000005",flush=True); sys.exit(2)'],
                log='client-wine.log',timeout=10)
        for thread in supervisor.threads:thread.join(timeout=2)
        current=runner.LOGS/'client-wine.log'
        self.assertIn('0xC0000005',current.read_text())
        self.assertLessEqual(current.stat().st_size,8*1024*1024)
        self.assertTrue((runner.LOGS/'client-wine.previous.log').is_file())

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
        self.assertTrue(supervisor.status['client_started'])
        env=supervisor.spawn.call_args.kwargs['env']
        self.assertIn('mscoree=b',env['WINEDLLOVERRIDES'].split(';'))
        self.assertEqual(env['DOTNET_HOST_TRACE'],'1')
        self.assertEqual(env['DOTNET_HOST_TRACEFILE'],'Z:\\logs\\client-dotnet-host.log')
        self.assertNotIn('DOTNET_STARTUP_HOOKS',env)
        self.assertNotIn('MEMENTO_MANAGED_LOG',env)
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
