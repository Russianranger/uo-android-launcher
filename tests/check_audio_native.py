"""Real ALSA format conversion/partial-write test against a clocked PCM sink."""
from pathlib import Path
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

library=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);sock=root/'audio.sock'
    config=root/'asound.conf'
    config.write_text(f'</usr/share/alsa/alsa.conf>\npcm_type.trasc {{ lib "{library}" }}\npcm.trasc {{ type trasc }}\npcm.!default {{ type plug slave {{ pcm "trasc" format S16_LE rate 48000 channels 2 }} }}\n')
    executable=root/'probe'
    subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror',str(Path(__file__).with_name('audio-native-probe.c')),'-lasound','-o',str(executable)],check=True)
    for fmt,count in (('s16',24000),('float',24000),('s16',37),('float',37)):
        server=socket.socket(socket.AF_UNIX);server.bind(str(sock));server.listen();server.settimeout(8)
        failures=[];received=bytearray();negotiated=[]
        def serve():
            try:
                connection,_=server.accept()
                with connection:
                    connection.settimeout(8)
                    def take(n):
                        data=bytearray()
                        while len(data)<n:
                            block=connection.recv(n-len(data))
                            if not block:raise EOFError()
                            data.extend(block)
                        return data
                    def reply(n):connection.sendall(struct.pack('<I',n))
                    header=struct.unpack('<5I',take(20));assert header[:4]==(0x50414c54,1,48000,2)
                    capacity=header[4];negotiated.append(capacity);assert capacity==1920
                    reply(0);written=played=0;started=False;last=time.monotonic();fraction=0
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
                            n=struct.unpack('<I',take(4))[0];data=take(n*4)
                            # Deliberately accept short writes, bounded by real free space.
                            accepted=min(n,128,capacity-(written-played));assert accepted>=0
                            received.extend(data[:accepted*4]);written+=accepted;reply(accepted)
                        else:raise AssertionError(command)
            except BaseException as error:failures.append(error)
        thread=threading.Thread(target=serve,daemon=True);thread.start()
        try:
            subprocess.run([str(executable),fmt,str(count)],check=True,timeout=15,env=dict(os.environ,ALSA_CONFIG_PATH=str(config),TRASC_AUDIO_SOCKET=str(sock)))
        finally:
            thread.join(9);server.close();sock.unlink(missing_ok=True)
        if failures:raise failures[0]
        assert not thread.is_alive()
        samples=struct.unpack('<'+'h'*(len(received)//2),received)
        assert len(samples)==count*2,len(samples)
        expected=[v for i in range(count) for v in ((i%401-200)*64,-(i%401-200)*64)]
        assert max(abs(a-b) for a,b in zip(samples,expected))<=1,'PCM changed, duplicated or dropped'
        print(f'{fmt}: {count} frames, exact stereo order, partial writes, 40 ms ring and natural drain passed')
