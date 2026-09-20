#!/usr/bin/env python3
"""Export 0.1.0 diagnostics or copy it to the separate recovery app using ADB.

No root required: both preview APKs are debuggable. The source app is never
uninstalled or cleared. Run `migrate` only after saving/stopping its realm.
"""
import argparse
import gzip
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ORIGINAL='io.github.russianranger.uomemento'
RECOVERY=ORIGINAL+'.recovery'


def archive_args(relative):
    # Closed X11/input processes can leave socket files behind. They are not
    # portable state; the launcher recreates these directories on its next run.
    excludes=['--exclude=files/tmp','--exclude=files/work/run'] if relative=='files' else []
    return ['tar']+excludes+['-cf','-',relative]


class Adb:
    def __init__(self,executable='adb',serial=None):
        self.base=[executable]+(['-s',serial] if serial else [])

    def call(self,*args):
        result=subprocess.run(self.base+list(args),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace').strip() or 'ADB command failed')
        return result.stdout

    def archive_command(self,package,relative):
        return self.base+['exec-out','run-as',package]+archive_args(relative)

    def restore_command(self):
        return self.base+['shell','-T','run-as',RECOVERY,'tar','-xf','-']

    def require_fresh_recovery(self):
        self.call('shell','run-as',RECOVERY,'pwd')
        self.call('shell','run-as',RECOVERY,'sh','-c',
                  "'test ! -e files/rootfs && test ! -e files/work/server && test ! -e files/work/client/current'")


def capture(adb,relative,destination):
    """Stream only from the original app; never unpack Android paths on the PC."""
    destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError('Choose a new backup filename; existing backups are never overwritten')
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix=destination.name+'-',suffix='.partial',dir=destination.parent)
    os.close(fd)
    try:
        with tempfile.TemporaryFile() as errors:
            with subprocess.Popen(adb.archive_command(ORIGINAL,relative),stdout=subprocess.PIPE,stderr=errors) as process:
                try:
                    with gzip.open(temporary,'wb',compresslevel=1) as out:
                        shutil.copyfileobj(process.stdout,out,1024*1024)
                except BaseException:
                    process.kill();raise
                finally:process.stdout.close()
                if process.wait()!=0:
                    errors.seek(0);raise RuntimeError(errors.read().decode(errors='replace') or 'Android archive failed')
        with open(temporary,'rb') as stream:os.fsync(stream.fileno())
        # Do not replace an existing backup even if it appeared during transfer.
        with destination.open('xb') as target,open(temporary,'rb') as source:
            try:shutil.copyfileobj(source,target,1024*1024);target.flush();os.fsync(target.fileno())
            except BaseException:target.close();destination.unlink(missing_ok=True);raise
        digest=hashlib.sha256()
        with destination.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        print('Saved:',destination)
        print('SHA-256:',digest.hexdigest())
        return destination
    finally:Path(temporary).unlink(missing_ok=True)


def restore(adb,archive):
    # Reading the entire gzip once checks corruption before changing the target.
    with gzip.open(archive,'rb') as source:
        while source.read(1024*1024):pass
    with tempfile.TemporaryFile() as errors:
        with subprocess.Popen(adb.restore_command(),stdin=subprocess.PIPE,stdout=errors,stderr=errors) as process:
            try:
                with gzip.open(archive,'rb') as source:shutil.copyfileobj(source,process.stdin,1024*1024)
                process.stdin.close()
            except BaseException:
                process.kill();raise
            if process.wait()!=0:
                errors.seek(0);raise RuntimeError(errors.read().decode(errors='replace') or 'Recovery copy failed')


def migrate(adb,backup):
    # Refuse a configured destination before stopping either app or writing data.
    adb.require_fresh_recovery()
    if Path(backup).exists():raise FileExistsError('Choose a new backup filename')
    print('Save & close the realm runtime and stop the client in the ORIGINAL app first.')
    print('Both apps will be closed. The original app and its files will remain installed.')
    if input('Type SAVED to copy the installation: ').strip()!='SAVED':
        raise RuntimeError('Copy cancelled; neither app was changed')
    adb.call('shell','am','force-stop',ORIGINAL)
    adb.call('shell','am','force-stop',RECOVERY)
    archive=capture(adb,'files',backup)
    restore(adb,archive)
    print('Copy complete. Open UO Memento Recovery. Keep the original app and backup until verified.')
    print('Run only one app at a time; both use the same local server ports.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb',default='adb',help='Path to Android platform-tools adb')
    parser.add_argument('--serial',help='ADB device serial when multiple devices are connected')
    commands=parser.add_subparsers(dest='action',required=True)
    logs=commands.add_parser('logs',help='Export existing 0.1.0 runtime/client logs without its UI')
    logs.add_argument('--output',default='uo-memento-old-logs.tar.gz')
    copy=commands.add_parser('migrate',help='Back up and copy all app files to a fresh recovery app')
    copy.add_argument('--backup',default='uo-memento-installation-backup.tar.gz')
    args=parser.parse_args();adb=Adb(args.adb,args.serial)
    try:
        if args.action=='logs':capture(adb,'files/work/logs',args.output)
        else:migrate(adb,args.backup)
    except (OSError,RuntimeError,EOFError,subprocess.SubprocessError) as error:
        parser.exit(1,str(error)+'\nThe original app has not been uninstalled or cleared.\n')


if __name__=='__main__':main()
