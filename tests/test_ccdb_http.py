import importlib.util,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import pytest

path=Path(__file__).parents[1]/'tools/ccdb_http_cache.py'
spec=importlib.util.spec_from_file_location('ccdb_http_cache',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path=='/alias':
                self.send_response(301);self.send_header('Location','/object');self.send_header('Valid-From','100');self.end_headers()
            elif self.path=='/object':
                self.send_response(303);self.send_header('Content-Location','alien:///requires-grid');self.send_header('Content-Location',f'http://127.0.0.1:{self.server.server_port}/download');self.end_headers()
            elif self.path=='/download':self.send_response(200);self.end_headers();self.wfile.write(b'root-test-object')
            else:self.send_response(404);self.end_headers()
        def log_message(self,*args):pass
    instance=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=instance.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{instance.server_port}'
    instance.shutdown();instance.server_close();thread.join()

def test_relative_alias_http_alternative_and_validity(server,tmp_path):
    path,headers=module.fetch_public_blob(server+'/alias',tmp_path)
    assert path.read_bytes()==b'root-test-object'
    assert ('Valid-From','100') in headers
    path2,headers2=module.fetch_public_blob(server+'/alias',tmp_path)
    assert path2==path and dict(headers2)['Valid-From']=='100'

def test_missing_condition_fails_before_reconstruction(server,tmp_path):
    with pytest.raises(ValueError,match='HTTP 404'):module.fetch_public_blob(server+'/missing',tmp_path)
