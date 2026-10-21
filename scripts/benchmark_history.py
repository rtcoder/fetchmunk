"""Controlled history benchmark. Uses temporary databases, never user state."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import tracemalloc

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend/src'))
from fetchmunk_backend.store import JobStore
from fetchmunk_backend.service import JobService


def record(i):
    return dict(job_id=f'{i:08d}',state='completed',attempt=1,revision=1,
                url=f'https://example.org/{i}.png',display_url=f'https://example.org/{i}.png',
                destination='/tmp/Fetchmunk',output_dir=f'/tmp/Fetchmunk/{i}',
                created_at='2026-01-01T00:00:00+00:00',updated_at='2026-01-01T00:00:00+00:00',
                downloaded=1,skipped=0,failed_files=0,current_file=None,error=None,auth_ref=None,wait_until=None)


def seed(path,count):
    """A schema1 fixture also exercises the real migration, backup and indexes."""
    path.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path/'state.sqlite')
    db.executescript('''CREATE TABLE jobs(id TEXT PRIMARY KEY,data TEXT NOT NULL);
CREATE TABLE operations(id TEXT PRIMARY KEY,request TEXT NOT NULL,result TEXT NOT NULL);
CREATE TABLE attempts(job_id TEXT,attempt INTEGER,data TEXT,PRIMARY KEY(job_id,attempt));
CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL); PRAGMA user_version=1;''')
    with db:
        db.executemany('INSERT INTO jobs VALUES (?,?)',((f'{i:08d}',json.dumps(record(i))) for i in range(count)))
    db.close()


class ControlledWorker:
    def __init__(self, callback):self.callback=callback;self.current=None
    def start(self, request):self.current=request
    def stop(self, reason):
        if self.current:
            current,self.current=self.current,None
            self.callback(current,dict(kind='exit',data={}))


def rss():
    return int(subprocess.check_output(['ps','-o','rss=','-p',str(os.getpid())],text=True))/1024


def run(count):
    with tempfile.TemporaryDirectory(prefix='Fetchmunk scale ') as tmp:
        path=Path(tmp);seed(path/'state',count)
        service=JobService(lambda e:None,supervisor_factory=ControlledWorker)
        def call(method,**params):
            response=service.handle(dict(id='benchmark',method=method,params=params))
            assert 'error' not in response,response
            return response['result']
        try:
            before=rss();start=time.perf_counter()
            call('session.initialize',data_dir=str(path/'state'),default_destination=str(path/'files'))
            init_ms=(time.perf_counter()-start)*1000
            assert call('jobs.summary')['total']==count
            plans={}
            for name,query in {
                'scheduler':"SELECT data FROM jobs WHERE state='queued' ORDER BY queue_order LIMIT 1",
                'all_page':"SELECT data FROM jobs WHERE (created_at,id)<('2026','999') ORDER BY created_at DESC,id DESC LIMIT 100",
                'history_page':"SELECT data FROM jobs WHERE bucket='history' AND (created_at,id)<('2026','999') ORDER BY created_at DESC,id DESC LIMIT 100",
            }.items():
                details=[r[3] for r in service.store.db.execute('EXPLAIN QUERY PLAN '+query)]
                assert all('TEMP B-TREE' not in d and 'SCAN jobs' not in d for d in details),details
                plans[name]=details
            tracemalloc.start();latencies=[];visited=0;cursor=None
            while True:
                start=time.perf_counter()
                p=call('jobs.snapshot',filter='history',**({'cursor':cursor} if cursor else {}))
                latencies.append((time.perf_counter()-start)*1000)
                visited+=len(p['jobs']);cursor=p['next_cursor']
                assert len(p['jobs'])<=100
                if cursor is None:break
            _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            assert visited==count
            jid=call('jobs.create',operation_id='scale',url='https://example.org/a.png',destination=str(path/'files'))['job_id']
            call('queue.set_enabled',operation_id='start',enabled=True)
            stop=threading.Event();read_errors=[]
            def read():
                try:
                    while not stop.is_set():call('jobs.snapshot',filter='history')
                except Exception as e:read_errors.append(str(e))
            reader=threading.Thread(target=read);reader.start()
            start=time.perf_counter()
            call('jobs.cancel',operation_id='cancel',job_id=jid)
            cancel_ms=(time.perf_counter()-start)*1000
            stop.set();reader.join()
            assert not read_errors,read_errors
            assert call('jobs.get',job_id=jid)['state']=='cancelled'
            return dict(records=count,migration_and_initialize_ms=round(init_ms,2),
                        page_median_ms=round(sorted(latencies)[len(latencies)//2],2),page_max_ms=round(max(latencies),2),
                        cancel_during_reads_ms=round(cancel_ms,2),rss_before_mib=round(before,2),rss_after_mib=round(rss(),2),
                        page_python_peak_mib=round(peak/1024/1024,2),visited=visited,query_plans=plans)
        finally:service.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--count',type=int);args=parser.parse_args()
    if args.count:print(json.dumps(run(args.count),indent=2))
    else:
        results=[]
        for count in (1000,100000):
            results.append(json.loads(subprocess.check_output([sys.executable,__file__,'--count',str(count)],text=True)))
        print(json.dumps(results,indent=2))
