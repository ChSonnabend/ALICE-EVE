#!/usr/bin/env python3
"""Local CCDB backend using the server's official HTTP blob alternatives.

The public server advertises both AliEn and HTTP Content-Location values.
We select HTTP(S), retain object/validity headers and cache immutable blobs.
The backend binds only to loopback and is scoped to this reconstruction.
"""
import argparse,hashlib,json,os,threading,urllib.error,urllib.parse,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def fetch_public_blob(url,cache):
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256(url.encode()).hexdigest();blob=cache/(key+'.root');info=cache/(key+'.json')
    if blob.exists() and info.exists():return blob,json.loads(info.read_text())['headers']
    opener=urllib.request.build_opener(NoRedirect);headers=None;current=url
    for attempt in range(8):
        try:response=opener.open(urllib.request.Request(current,headers={'User-Agent':'ALICE-event-renderer-CCDB/1'}),timeout=30)
        except urllib.error.HTTPError as error:response=error
        if response.code==200:
            if headers is None:headers=list(response.headers.items())
            temporary=blob.with_suffix('.part-'+str(threading.get_ident()))
            try:
                with response,temporary.open('wb') as stream:
                    while chunk:=response.read(1024*1024):stream.write(chunk)
                with temporary.open('rb') as stream:
                    if stream.read(4)!=b'root':raise ValueError('CCDB HTTP response is not a ROOT object: '+url)
                temporary.replace(blob)
                info.write_text(json.dumps(dict(url=url,download_url=current,headers=headers),indent=2))
                return blob,headers
            finally:temporary.unlink(missing_ok=True)
        if response.code not in (301,302,303,307,308):
            response.close();raise ValueError(f'CCDB returned HTTP {response.code}: {url}')
        if headers is None:headers=list(response.headers.items())
        locations=response.headers.get_all('Content-Location',[])+response.headers.get_all('Location',[])
        alternatives=[urllib.parse.urljoin(current,location) for location in locations
                      if urllib.parse.urljoin(current,location).startswith(('http://','https://'))]
        response.close()
        if not alternatives:raise ValueError('CCDB did not advertise an HTTP download location: '+url)
        current=alternatives[0]
    raise ValueError('Too many CCDB HTTP redirects: '+url)

def serve(backend,cache,port_file):
    lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                # ROOT and CCDB downloads are serialized to prevent races in
                # cache metadata. The reconstruction still processes in parallel.
                with lock:blob,headers=fetch_public_blob(backend.rstrip('/')+self.path,cache)
                self.send_response(200)
                for name,value in headers:
                    if name.lower() not in ('location','content-location','content-length','transfer-encoding','connection','date','server'):
                        self.send_header(name,value)
                self.send_header('Content-Length',str(blob.stat().st_size));self.end_headers()
                with blob.open('rb') as stream:
                    while chunk:=stream.read(1024*1024):self.wfile.write(chunk)
            except (OSError,ValueError,urllib.error.URLError) as error:
                self.send_error(502,str(error));print('CCDB cache error:',error,flush=True)
        def do_HEAD(self):
            try:
                with lock:blob,headers=fetch_public_blob(backend.rstrip('/')+self.path,cache)
                self.send_response(200)
                for name,value in headers:
                    if name.lower() not in ('location','content-location','content-length','transfer-encoding','connection','date','server'):
                        self.send_header(name,value)
                self.send_header('Content-Length',str(blob.stat().st_size));self.end_headers()
            except (OSError,ValueError,urllib.error.URLError) as error:self.send_error(502,str(error))
        def log_message(self,format,*args):print(format%args,flush=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    target=Path(port_file);temporary=target.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(url=f'http://127.0.0.1:{server.server_port}')))
    temporary.replace(target)
    server.serve_forever()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--backend',required=True);p.add_argument('--cache',required=True);p.add_argument('--port-file',required=True);a=p.parse_args();serve(a.backend,a.cache,a.port_file)
