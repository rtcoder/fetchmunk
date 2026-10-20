import json,os,subprocess,sys,threading
from dataclasses import asdict
from pathlib import Path

class WorkerSupervisor:
    def __init__(self,callback):
        self.callback=callback;self.process=None;self.thread=None
    @property
    def running(self):return self.process is not None and self.process.poll() is None
    def start(self,request):
        if self.running:raise RuntimeError('worker already running')
        command=[sys.executable,'--worker'] if getattr(sys,'frozen',False) else [sys.executable,'-m','fetchmunk_backend','--worker']
        env={k:v for k,v in os.environ.items() if not k.startswith('PYTHON')}
        if not getattr(sys,'frozen',False):env['PYTHONPATH']=str(Path(__file__).resolve().parents[1])
        p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env)
        self.process=p
        payload=asdict(request);payload['output_dir']=str(request.output_dir);payload['archive_path']=str(request.archive_path)
        p.stdin.write((json.dumps(payload)+'\n').encode());p.stdin.flush()
        def read():
            result=None
            try:
                while True:
                    line=p.stdout.readline(1048577)
                    if not line:break
                    if len(line)>1048576:raise ValueError('worker frame overflow')
                    event=json.loads(line)
                    if event['kind']=='result':result=event
                    else:self.callback(request,event)
                p.wait(timeout=5)
            except Exception:
                if p.poll() is None:p.kill();p.wait()
            finally:
                p.stdin.close();p.stdout.close()
                if p.returncode!=0:result=None
                self.callback(request,result or {'kind':'exit','data':{}})
        self.thread=threading.Thread(target=read,daemon=True);self.thread.start()
    def stop(self,reason,grace_seconds=5.0):
        p=self.process
        if not p or p.poll() is not None:return
        def terminate():
            try:
                p.terminate();p.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:p.kill();p.wait()
            except ProcessLookupError:pass
        threading.Thread(target=terminate,daemon=True).start()
    def join(self,seconds=6):
        if self.thread and self.thread is not threading.current_thread():self.thread.join(seconds)
