import json,os,queue,signal,subprocess,sys,threading,time,http.server
from pathlib import Path
import pytest

class Slow(http.server.BaseHTTPRequestHandler):
    entered=threading.Event();release=threading.Event()
    def do_GET(self):
        self.entered.set();self.release.wait(15)
        try:self.send_response(200);self.end_headers();self.wfile.write(b'data')
        except OSError:pass
    def log_message(self,*args):pass

@pytest.fixture
def slow_url():
    Slow.entered.clear();Slow.release.clear()
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Slow)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}/slow.png'
    Slow.release.set();server.shutdown();server.server_close()

class Client:
    def __init__(self,tmp_path):
        env={**os.environ,'PYTHONPATH':str(Path(__file__).parents[1]/'src')}
        self.p=subprocess.Popen([sys.executable,'-m','fetchmunk_backend'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,text=True)
        self.messages=queue.Queue()
        def read():
            for line in self.p.stdout:self.messages.put(json.loads(line))
        threading.Thread(target=read,daemon=True).start()
        assert self.messages.get(timeout=10)['type']=='hello'
        self.call('session.initialize',data_dir=str(tmp_path/'state'),default_destination=str(tmp_path/'files'))
    def call(self,method,**params):
        params.setdefault('operation_id',str(time.monotonic_ns()))
        self.p.stdin.write(json.dumps({'protocol':1,'type':'request','id':method,'method':method,'params':params})+'\n');self.p.stdin.flush()
        while True:
            msg=self.messages.get(timeout=10)
            if msg.get('type')=='response' and msg['id']==method:
                assert 'error' not in msg,msg
                return msg['result']
    def cleanup(self):
        if self.p.poll() is None:self.p.kill();self.p.wait()
        for stream in (self.p.stdin,self.p.stdout,self.p.stderr):stream.close()

@pytest.mark.parametrize('terminate',['eof','kill'])
def test_parent_loss_stops_transfer(tmp_path,slow_url,terminate):
    c=Client(tmp_path)
    try:
        c.call('jobs.create',url=slow_url,destination=str(tmp_path/'files'))
        assert Slow.entered.wait(10)
        children=subprocess.check_output(['pgrep','-P',str(c.p.pid)],text=True).split()
        assert children
        if terminate=='eof':c.p.stdin.close()
        else:c.p.kill()
        c.p.wait(timeout=10)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            statuses=[subprocess.run(['ps','-o','stat=','-p',pid],capture_output=True,text=True).stdout.strip() for pid in children]
            if all(not s or s.startswith('Z') for s in statuses):break
            time.sleep(.05)
        assert all(not s or s.startswith('Z') for s in statuses),statuses
    finally:c.cleanup()

def test_forced_stop_of_suspended_worker(tmp_path,slow_url):
    from fetchmunk_backend.supervisor import WorkerSupervisor
    from fetchmunk_backend.models import WorkerRequest
    events=queue.Queue();s=WorkerSupervisor(lambda r,e:events.put(e))
    s.start(WorkerRequest('j',1,slow_url,tmp_path/'out',tmp_path/'archive'))
    try:
        assert Slow.entered.wait(10)
        os.kill(s.process.pid,signal.SIGSTOP)
        s.stop('cancel',grace_seconds=.1);s.join(5)
        assert not s.running
    finally:
        if s.running:s.process.kill();s.join()

def test_slow_stdout_reader_cannot_leave_backend_running(tmp_path):
    env={**os.environ,'PYTHONPATH':str(Path(__file__).parents[1]/'src')}
    p=subprocess.Popen([sys.executable,'-m','fetchmunk_backend'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
    def flood():
        try:
            for i in range(10000):
                p.stdin.write((json.dumps({'protocol':1,'type':'request','id':'x'*2000,'method':'jobs.get','params':{}})+'\n').encode());p.stdin.flush()
        except (OSError,ValueError):pass
    threading.Thread(target=flood,daemon=True).start()
    try:p.wait(timeout=15)
    finally:
        if p.poll() is None:p.kill();p.wait()
        try:p.stdin.close()
        except BrokenPipeError:pass
        p.stdout.close();p.stderr.close()
