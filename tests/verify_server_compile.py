"""Compile the real Memento core and game scripts, including the shutdown bridge."""
from pathlib import Path
import shutil
import subprocess
import sys

source=Path(sys.argv[1]).resolve()/'World'
repo=Path(__file__).resolve().parents[1]
shutil.copy2(repo/'backend/MementoAndroidControl.cs',source/'Source/Scripts/System/Misc/MementoAndroidControl.cs')
subprocess.run(['mcs','-optimize+','-unsafe','-t:exe','-out:'+str(source/'WorldLinux.exe'),'-win32icon:../System/icon.ico',
                '-nowarn:219,414','-d:NEWTIMERS','-d:NEWPARENT','-d:MONO','-recurse:../System/*.cs','-main:Server.Core'],cwd=source/'Source/Tools',check=True)
references=[x.strip() for x in (source/'Data/System/CFG/Assemblies.cfg').read_text().splitlines() if x.strip() and not x.startswith('#')]
files=sorted((source/'Source/Scripts').rglob('*.cs'))+sorted((source/'Info/Scripts').rglob('*.cs'))
response=source/'verify-scripts.rsp'
response.write_text('\n'.join('"'+str(p)+'"' for p in files))
subprocess.run(['mcs','-t:library','-out:'+str(source/'verified-scripts.dll'),'-r:'+str(source/'WorldLinux.exe')]+['-r:'+x for x in references]+['@'+str(response)],cwd=source,check=True)
print('Compiled Memento core, '+str(len(files))+' game scripts, and the save/stop bridge.')
