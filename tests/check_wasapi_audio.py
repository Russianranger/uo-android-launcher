"""Exercise Windows audio through native ARM64 Wine and the real ALSA plugin.

The host sink implements the app's existing bounded protocol and playback
clock. Frequency/channel checks use only the fixture's synthetic tones.
This verifies transport/conversion, not Android speakers or gameplay sound.
"""
import array
import math
import os
from pathlib import Path
import socket
import struct
import subprocess
import threading
import time

root=Path('/check/audio');root.mkdir(exist_ok=True)
sock=root/'audio.sock';sock.unlink(missing_ok=True)
config=root/'asound.conf'
config.write_text('</usr/share/alsa/alsa.conf>\npcm_type.trasc { lib "/check/audio/libasound_module_pcm_trasc.so" }\npcm.trasc { type trasc }\npcm.!default { type plug slave { pcm "trasc" format S16_LE rate 48000 channels 2 } }\n')
server=socket.socket(socket.AF_UNIX);server.bind(str(sock));server.listen();server.settimeout(.2)
finished=threading.Event();errors=[];streams=[];workers=[]

def serve(connection):
    samples=bytearray();streams.append(samples)
    try:
        with connection:
            connection.settimeout(15)
            def take(n):
                data=bytearray()
                while len(data)<n:
                    block=connection.recv(n-len(data))
                    if not block:raise EOFError()
                    data.extend(block)
                return data
            def reply(n):connection.sendall(struct.pack('<I',n))
            header=struct.unpack('<5I',take(20));assert header[:4]==(0x50414c54,1,48000,2)
            capacity=header[4];assert 64<=capacity<=48000;reply(0)
            written=played=0;started=False;last=time.monotonic();fraction=0
            while True:
                try:command=struct.unpack('<I',take(4))[0]
                except EOFError:break
                now=time.monotonic()
                if started:
                    advance=(now-last)*48000+fraction;whole=int(advance);fraction=advance-whole
                    played=min(written,played+whole)
                last=now
                if command==1:started=True;reply(0)
                elif command in (2,5):written=played=0;started=False;fraction=0;reply(0)
                elif command==3:reply(played)
                elif command==4:
                    count=struct.unpack('<I',take(4))[0];assert 1<=count<=4096
                    data=take(count*4);accepted=min(count,capacity-(written-played));assert accepted>=0
                    samples.extend(data[:accepted*4]);written+=accepted;reply(accepted)
                else:raise AssertionError(command)
    except BaseException as error:errors.append(error)

def accept():
    while not finished.is_set():
        try:connection,_=server.accept()
        except socket.timeout:continue
        worker=threading.Thread(target=serve,args=(connection,),daemon=True);workers.append(worker);worker.start()

listener=threading.Thread(target=accept,daemon=True);listener.start()
try:
    env=dict(os.environ,ALSA_CONFIG_PATH=str(config),TRASC_AUDIO_SOCKET=str(sock),
             SDL_AUDIO_DRIVER='wasapi',SDL_AUDIODRIVER='wasapi',WINEDEBUG='-all,err+all,trace+loaddll')
    result=subprocess.run(['/opt/wine/bin/wine','/check/graphics/audio-probe.exe'],env=env,
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
    print(result.stdout.decode(errors='replace'),flush=True)
    assert result.returncode==0,result.returncode
finally:
    finished.set();listener.join(2)
    for worker in workers:worker.join(16)
    server.close();sock.unlink(missing_ok=True)
if errors:raise errors[0]
assert all(not worker.is_alive() for worker in workers)
assert streams,'Wine did not use the ALSA bridge'
pcm=array.array('h',max(streams,key=len))
assert len(pcm)>=48000*2,'Missing audio'
left=pcm[0::2];right=pcm[1::2]
signal=[i for i,x in enumerate(left) if abs(x)>100]
assert signal and signal[-1]-signal[0]>48000*3,'Audio truncated'
start=signal[0]+4800
for channel,frequency in ((left,440),(right,660)):
    window=channel[start:start+48000];assert len(window)==48000
    rms=math.sqrt(sum(x*x for x in window)/len(window))
    crossings=sum(a<=0<b for a,b in zip(window,window[1:]))
    assert 4000<rms<7000,(rms,'wrong level or clipping')
    assert abs(crossings-frequency)<=3,(crossings,frequency,'wrong playback rate or channel')
print('WINE_WASAPI_PCM_OK 440/660 Hz stereo, level and duration verified through ALSA bridge',flush=True)
