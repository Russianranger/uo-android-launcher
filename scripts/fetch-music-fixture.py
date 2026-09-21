"""Fetch only checksum-pinned DLLs from the public Memento ZIP using HTTP ranges.

No client archive or complete client assembly is shipped in the APK. The public
package link is published by Jascen/ultima-memento release 2.4.1. Its TazUO/FNA
DLLs match the user's uploaded 5.2.0 binaries exactly.
"""
import hashlib
from html.parser import HTMLParser
import io
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request
import zipfile

FILES = {
    'TazUO.dll':'b04066be1b1b475ca00e6982a980e2dd11b93abede00c79c68bde566bdcf947e',
    'ClassicUO.Assets.dll':'1dd53cf0eea718aefeda33fba105c9797b138188be22562b47548c310524100d',
    'ClassicUO.IO.dll':'334d1932f6fefe22731cccbbd812a6761d55ffa607ff0a4a291c2bc796c78483',
    'ClassicUO.Utility.dll':'209db31075fbe310bbe5f827ef62cf3419eef50b77b4be351d8387eda72f62b3',
    'FNA.dll':'399c91458ccbd08bcd8094bde39a1091f5edd545fd77a9b4579016e7ac5498c6',
}
URL='https://drive.usercontent.google.com/download?id=1ZyIFmwQ4d_wDhF0UtPgwMYEL0PWFwuvc&export=download'
FOLDER='Ultima-Memento/Client/TazUO-Launcher/TazUO/'
LIMIT=16*1024*1024

class DownloadForm(HTMLParser):
    def __init__(self):super().__init__();self.action=None;self.values={}
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='form':self.action=attrs.get('action')
        if tag=='input' and attrs.get('name'):self.values[attrs['name']]=attrs.get('value','')

def request(url, span, limit):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'Range':'bytes='+span}),timeout=60) as response:
        body=response.read(limit+1)
        if len(body)>limit:raise ValueError('Public fixture range exceeded its limit')
        return response.status,response.headers,body

class RemoteZip(io.RawIOBase):
    def __init__(self):
        self.url=URL;self.position=0
        status,headers,body=request(self.url,'-65536',128*1024)
        if status==200 and 'text/html' in headers.get('Content-Type',''):
            form=DownloadForm();form.feed(body.decode('utf-8'))
            if urllib.parse.urlsplit(form.action or '').netloc!='drive.usercontent.google.com':
                raise ValueError('Unexpected public download response')
            self.url=form.action+'?'+urllib.parse.urlencode(form.values)
            status,headers,body=request(self.url,'-65536',65536)
        match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',headers.get('Content-Range',''))
        if status!=206 or not match:raise ValueError('Public ZIP range download unavailable')
        first,last,self.size=map(int,match.groups())
        if last!=self.size-1 or last-first+1!=len(body):raise ValueError('Incomplete ZIP directory tail')
        self.tail=body
    def seekable(self):return True
    def readable(self):return True
    def tell(self):return self.position
    def seek(self,n,whence=0):
        self.position=n if whence==0 else self.position+n if whence==1 else self.size+n
        if self.position<0:raise ValueError('Negative ZIP position')
        return self.position
    def read(self,n=-1):
        start=self.position;n=min(n if n>=0 else self.size-start,self.size-start)
        if n<=0:return b''
        if n>LIMIT:raise ValueError('Excessive ZIP range')
        if start>=self.size-len(self.tail):data=self.tail[start-(self.size-len(self.tail)):start-(self.size-len(self.tail))+n]
        else:
            status,headers,data=request(self.url,f'{start}-{start+n-1}',n)
            if status!=206 or headers.get('Content-Range')!=f'bytes {start}-{start+n-1}/{self.size}':
                raise ValueError('Incorrect ZIP range response')
        if len(data)!=n:raise ValueError('Incomplete ZIP range')
        self.position+=n;return data

def fetch(destination):
    destination.mkdir(parents=True,exist_ok=True)
    missing=[name for name,sha in FILES.items() if not (destination/name).is_file() or hashlib.sha256((destination/name).read_bytes()).hexdigest()!=sha]
    if not missing:return
    with RemoteZip() as remote,zipfile.ZipFile(remote) as archive:
        for name in missing:
            member=archive.getinfo(FOLDER+name)
            if member.file_size>LIMIT or member.compress_size>LIMIT:raise ValueError('Oversized fixture DLL')
            data=archive.read(member)
            if hashlib.sha256(data).hexdigest()!=FILES[name]:raise ValueError('Public client changed: checksum mismatch for '+name)
            (destination/name).write_bytes(data)
            print('Verified public fixture:',name,flush=True)

if __name__=='__main__':fetch(Path(sys.argv[1] if len(sys.argv)>1 else 'runtime-work/music-fixture/original'))
