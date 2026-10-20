"""Persistent coordinator. All state transitions are serialized under one lock."""
import json,os,queue,sys,threading,time,uuid
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
from . import __version__
from .models import WorkerRequest
from .store import JobStore,StoreError,timestamp
from .snapshots import SnapshotStore,SnapshotError
from .supervisor import WorkerSupervisor
from .wire import FrameDecoder,ProtocolError,encode_frame

ACTIVE={'extracting','downloading','waiting','cancelling'}
RETRY={'failed','partial','cancelled','interrupted','needs_auth'}

class JobService:
    def __init__(self,emit,supervisor_factory=WorkerSupervisor):
        self.emit=emit;self.lock=threading.RLock();self.store=None;self.closed=False
        self.session_id=str(uuid.uuid4());self.seq=0;self.queue_enabled=True
        self.destination=None;self.active=None;self.stopping=False;self.last_progress=0
        self.supervisor=supervisor_factory(self.on_worker);self.snapshots=SnapshotStore()
    def event(self,name,data):
        self.seq+=1
        self.emit({'protocol':1,'type':'event','session_id':self.session_id,'seq':self.seq,'event':name,'data':data})
    def changed(self,job):
        job['revision']+=1;job['updated_at']=timestamp()
        self.store.save_job(job)
        self.event('job.changed',{'job_id':job['job_id'],'revision':job['revision']})
    def handle(self,request):
        with self.lock:
            response={'protocol':1,'type':'response','id':request.get('id')}
            try:
                method=request.get('method');params=request.get('params',{})
                if not isinstance(method,str) or not isinstance(params,dict):raise StoreError('invalid_params')
                if method=='session.initialize':
                    if self.store:raise StoreError('invalid_state')
                    data=self.absolute_path(params.get('data_dir'));self.destination=self.absolute_path(params.get('default_destination'))
                    self.store=JobStore.open(data);self.queue_enabled=not bool(self.store.all_jobs())
                    self.store.recover_interrupted()
                    result={'schema_version':1,'queue_enabled':self.queue_enabled}
                elif not self.store or self.closed or self.stopping:raise StoreError('invalid_state')
                elif method=='jobs.get':result=self.store.get_job(params.get('job_id'))
                elif method=='jobs.snapshot':
                    limit=params.get('limit',100)
                    result=self.snapshots.page(params['cursor'],limit) if params.get('cursor') else self.snapshots.create(self.store.all_jobs(),self.seq,limit)
                elif method.startswith('auth.'):raise StoreError('dependency_unsupported')
                elif method=='app.shutdown':
                    self.stopping=True;self.queue_enabled=False
                    result={'accepted':True}
                elif method in {'jobs.create','jobs.cancel','jobs.retry','queue.set_enabled'}:
                    op=params.get('operation_id')
                    if not isinstance(op,str) or not 1<=len(op)<=128:raise StoreError('invalid_params')
                    # side effects are applied after commit; cached result has no duplicate side effects
                    effects=[]
                    result=self.store.apply_operation(op,method,params,lambda db:self.mutate(method,params,db,effects))
                    for kind,value in effects:
                        if kind=='job':self.event('job.changed',{'job_id':value['job_id'],'revision':value['revision']})
                        elif kind=='cancel':self.supervisor.stop('cancel')
                        elif kind=='queue':self.queue_enabled=value;self.event('queue.changed',{'queue_enabled':value})
                else:raise StoreError('unknown_method')
                response['result']=result
            except (StoreError,SnapshotError) as exc:
                code=str(exc);response['error']={'code':code,'message_key':'error.'+code,'retryable':False}
            except (ValueError,TypeError,KeyError):
                response['error']={'code':'invalid_params','message_key':'error.invalid_params','retryable':False}
            except OSError as exc:
                code='disk_full' if exc.errno==28 else 'permission_denied'
                response['error']={'code':code,'message_key':'error.'+code,'retryable':True}
            self.pump()
            return response
    @staticmethod
    def absolute_path(value):
        if not isinstance(value,str) or not value or len(value)>4096 or '\0' in value:raise StoreError('invalid_params')
        p=Path(value)
        if not p.is_absolute():raise StoreError('invalid_params')
        return p
    def mutate(self,method,p,db,effects):
        if method=='queue.set_enabled':
            if type(p.get('enabled')) is not bool:raise StoreError('invalid_params')
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('queue_enabled',json.dumps(p['enabled'])))
            effects.append(('queue',p['enabled']));return {'queue_enabled':p['enabled']}
        if method=='jobs.create':
            url=p.get('url')
            try:
                parsed=urlsplit(url)
                valid=isinstance(url,str) and len(url)<=16384 and parsed.scheme in {'http','https'} and bool(parsed.hostname) and not parsed.username and not parsed.password and not any(c.isspace() for c in url)
            except (ValueError,TypeError):valid=False
            if not valid:raise StoreError('invalid_url')
            dest=self.absolute_path(p.get('destination'));jid=str(uuid.uuid4());out=dest/('Fetchmunk-'+jid[:12])
            while out.exists():jid=str(uuid.uuid4());out=dest/('Fetchmunk-'+jid[:12])
            now=timestamp()
            job={'job_id':jid,'revision':1,'attempt':1,'state':'queued','url':url,
                 'display_url':urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'','')),
                 'destination':str(dest),'output_dir':str(out),'created_at':now,'updated_at':now,
                 'auth_ref':None,'downloaded':0,'skipped':0,'failed_files':0,'current_file':None,
                 'wait_until':None,'error':None}
            self.store.save_job(job,db);effects.append(('job',job))
            return {'job_id':jid,'revision':1}
        job=self.store.get_job(p.get('job_id'))
        if method=='jobs.cancel':
            if job['state'] not in ACTIVE|{'queued','needs_auth'}:return job
            job['state']='cancelling' if job['job_id']==self.active else 'cancelled'
            if job['state']=='cancelling':effects.append(('cancel',None))
        else:
            if job['state'] not in RETRY:raise StoreError('invalid_state')
            db.execute('INSERT OR REPLACE INTO attempts VALUES (?,?,?)',(job['job_id'],job['attempt'],json.dumps(job)))
            job.update(attempt=job['attempt']+1,state='queued',downloaded=0,skipped=0,failed_files=0,current_file=None,error=None,wait_until=None)
        job['revision']+=1;job['updated_at']=timestamp();self.store.save_job(job,db)
        effects.insert(0,('job',job));return job
    def pump(self):
        if not self.store or self.active or not self.queue_enabled or self.stopping or self.closed:return
        for job in self.store.all_jobs():
            if job['state']!='queued':continue
            self.active=job['job_id'];job['state']='extracting';self.changed(job)
            try:
                archive=self.store.data_dir/'archives'/f"{job['job_id']}.sqlite"
                self.supervisor.start(WorkerRequest(job['job_id'],job['attempt'],job['url'],Path(job['output_dir']),archive))
            except Exception:
                self.active=None;job.update(state='failed',error=self.error('engine_error'));self.changed(job)
                continue
            break
    @staticmethod
    def error(code):
        return {'code':code,'message_key':'error.'+code,'retryable':code not in {'unsupported_url','dependency_unsupported'},
                'action':'authenticate' if code in {'auth_required','auth_expired'} else 'check_destination' if code in {'disk_full','permission_denied'} else 'retry'}
    def on_worker(self,request,event):
        with self.lock:
            if self.closed or not self.store:return
            job=self.store.get_job(request.job_id)
            if job['attempt']!=request.attempt or job['state'] not in ACTIVE:return
            kind=event.get('kind');data=event.get('data',{})
            if kind in {'result','exit'}:
                if job['state']=='cancelling':job['state']='cancelled'
                elif self.stopping:job['state']='interrupted'
                else:
                    for key in ('downloaded','skipped','failed_files'):
                        if key in data:job[key]=data[key]
                    code=data.get('error_code') or ('engine_error' if kind=='exit' else None)
                    job['error']=self.error(code) if code else None
                    total=job['downloaded']+job['skipped']
                    job['state']='needs_auth' if code in {'auth_required','auth_expired'} else ('partial' if total else 'failed') if code else ('completed' if total else 'empty')
                job['current_file']=None;self.active=None;self.changed(job);self.pump();return
            if job['state']=='cancelling':return
            if kind=='file.start':job.update(state='downloading',current_file={'name':data['name'],'bytes_done':0,'bytes_total':None,'bytes_per_second':None})
            elif kind=='file.progress':
                if job['current_file']:job['current_file'].update(data)
                if time.monotonic()-self.last_progress<0.25:return
                self.last_progress=time.monotonic()
            elif kind in {'file.success','file.skip','file.error'}:
                for key in ('downloaded','skipped','failed_files'):
                    if key in data:job[key]=data[key]
            else:return
            self.changed(job)
    def close(self):
        with self.lock:
            if self.closed:return
            self.stopping=True;self.queue_enabled=False
        self.supervisor.stop('quit')
        if hasattr(self.supervisor,'join'):self.supervisor.join(6)
        with self.lock:
            if self.store:
                self.store.recover_interrupted();self.store.close()
            self.closed=True


def serve():
    incoming=queue.Queue(maxsize=128);outgoing=queue.Queue(maxsize=128);failed=threading.Event()
    def emit(message):
        if failed.is_set():return
        try:outgoing.put(encode_frame(message),timeout=5)
        except queue.Full:
            failed.set()
            try:incoming.put_nowait(None)
            except queue.Full:pass
    service=JobService(emit)
    from gallery_dl.version import __version__ as engine_version
    def writer():
        import select
        fd=sys.stdout.fileno();os.set_blocking(fd,False)
        while True:
            data=outgoing.get()
            if data is None:return
            deadline=time.monotonic()+5
            try:
                while data:
                    remaining=deadline-time.monotonic()
                    if remaining<=0 or not select.select([],[fd],[],remaining)[1]:raise TimeoutError()
                    try:n=os.write(fd,data)
                    except BlockingIOError:continue
                    data=data[n:]
            except (OSError,TimeoutError):
                failed.set()
                try:incoming.put_nowait(None)
                except queue.Full:pass
                return
    def reader():
        decoder=FrameDecoder()
        try:
            while chunk:=os.read(sys.stdin.fileno(),65536):
                for frame in decoder.feed(chunk):incoming.put(frame)
            decoder.finish()
        except (OSError,ProtocolError):pass
        finally:incoming.put(None)
    w=threading.Thread(target=writer,daemon=True);w.start()
    threading.Thread(target=reader,daemon=True).start()
    emit({'protocol':1,'type':'hello','session_id':service.session_id,'backend_version':__version__,'engine_version':engine_version,'capabilities':['jobs']})
    try:
        while not failed.is_set():
            req=incoming.get()
            if req is None:break
            if req.get('type')!='request' or not isinstance(req.get('id'),str):break
            emit(service.handle(req))
            if service.stopping:break
    finally:
        service.close()
        if not failed.is_set():
            outgoing.put(None,timeout=5);w.join(5)
