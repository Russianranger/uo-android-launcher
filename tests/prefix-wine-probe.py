"""Reproduce the reported failure, then use the real Android supervisor repair.

Runs inside the exact retained ARM64 Wine/FEX image and the app's patched PRoot.
All files and registry values here are synthetic test data.
"""
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,'/check/backend')
import uo_client_runner as runner
import client_prefix

prefix=Path(os.environ['WINEPREFIX'])
runner.PREFIX=prefix
runner.LOGS=Path('/check/logs')
runner.SESSION=Path('/check/prefix-session');runner.SESSION.mkdir(exist_ok=True)
runner.CLIENT=Path('/check/prefix-client');runner.CLIENT.mkdir(exist_ok=True)
client=runner.CLIENT/'settings.json';client.write_text('{"private":"retained"}')
supervisor=runner.Supervisor({'mode':'desktop','renderer':'software','runtime_backend':runner.RUNTIME_ID,
                             'resolution':'1280x720','display_fps':30})
supervisor.env.update(WINEPREFIX=str(prefix),DISPLAY=os.environ['DISPLAY'])
key=r'HKCU\Software\MementoPrefixProbe'

def wine(*args,check=True):
    result=subprocess.run(runner.WINE+list(args),env=supervisor.env,cwd=runner.CLIENT,
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
    if check and result.returncode:
        raise AssertionError(result.stdout.decode(errors='replace'))
    return result

def stop():
    for flag in ('-k','-w'):
        subprocess.run(runner.WINESERVER+[flag],env=supervisor.env,check=True,timeout=20)

wine('reg','add',key,'/v','Kept','/d','retained','/f');stop()
sentinel=prefix/'drive_c/users/root/prefix-recovery-sentinel.txt'
sentinel.parent.mkdir(parents=True,exist_ok=True);sentinel.write_text('retained')
system=prefix/'system.reg';damaged=b'\0'*4096;system.write_bytes(damaged)
failed=wine('cmd','/d','/c','exit','0',check=False)
output=failed.stdout.decode(errors='replace')
Path('/check/logs/proot-prefix-reproduced.log').write_text(output)
assert failed.returncode!=0 and 'system.reg is not a valid registry file' in output,output
assert '32-bit wineserver' in output,output
stop()

# Match the stale ready marker from the user's failed attempt.
(prefix/'memento-prefix-ready').write_text(runner.PREFIX_REVISION)
supervisor.prepare_prefix()
assert supervisor.status['prefix_update']=='repair'
assert supervisor.status['prefix_registry']['actions']['system.reg']=='regenerate_with_wineboot'
assert next(prefix.glob('.memento-registry-recovery/*/system.reg')).read_bytes()==damaged
assert b'retained' in wine('reg','query',key,'/v','Kept').stdout
assert sentinel.read_text()=='retained' and client.read_text()=='{"private":"retained"}'
stop()

# A later interruption can restore the new durable registry checkpoint.
system.write_bytes(b'broken header\n')
supervisor.prepare_prefix()
assert supervisor.status['prefix_registry']['actions']['system.reg']=='restored_checkpoint'
assert all(item['state']=='valid' for item in client_prefix.inspect(prefix).values())
assert b'retained' in wine('reg','query',key,'/v','Kept').stdout
assert sentinel.read_text()=='retained' and client.read_text()=='{"private":"retained"}'
stop()
for thread in supervisor.threads:thread.join(timeout=3)
print('FEX_PREFIX_RECOVERY_OK reproduced win32 message; regenerated system hive; retained user registry, drive_c and client; checkpoint restore passed',flush=True)
