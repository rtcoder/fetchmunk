"""Single-writer SQLite state. The service serializes mutations."""

import fcntl
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ACTIVE = ('extracting', 'downloading', 'waiting', 'cancelling')
PENDING = (*ACTIVE, 'queued', 'needs_auth')
FAILED = ('failed', 'partial', 'interrupted', 'needs_auth')


class StoreError(ValueError):
    pass


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def validate_legacy(db):
    # Stream validation before any schema change. Never include private row data in errors.
    states = set(PENDING) | {'completed','partial','empty','failed','cancelled','interrupted'}
    strings = ('job_id','state','url','display_url','destination','output_dir','created_at','updated_at')
    for jid, raw in db.execute('SELECT id,data FROM jobs'):
        try:
            job = json.loads(raw)
            valid = (isinstance(job,dict) and all(isinstance(job.get(k),str) for k in strings)
                     and job['job_id']==jid and job['state'] in states
                     and all(type(job.get(k)) is int and job[k]>=1 for k in ('revision','attempt'))
                     and all(type(job.get(k)) is int and job[k]>=0 for k in ('downloaded','skipped','failed_files')))
            if not valid:raise ValueError()
            current = job.get('current_file')
            if current is not None:
                if not isinstance(current,dict) or not isinstance(current.get('name'),str):raise ValueError()
                if type(current.get('bytes_done')) is not int or current['bytes_done']<0:raise ValueError()
                for key in ('bytes_total','bytes_per_second'):
                    if current.get(key) is not None and (type(current[key]) not in (int,float) or current[key]<0):raise ValueError()
            error = job.get('error')
            if error is not None and (not isinstance(error,dict) or not isinstance(error.get('code'),str)
                                      or not isinstance(error.get('action'),str) or type(error.get('retryable')) is not bool):raise ValueError()
        except (ValueError,TypeError,KeyError):
            raise sqlite3.DatabaseError('invalid legacy job record') from None


def migrate(db, data_dir, version):
    if version == 0:
        db.executescript('''CREATE TABLE jobs(id TEXT PRIMARY KEY,data TEXT NOT NULL);
CREATE TABLE operations(id TEXT PRIMARY KEY,request TEXT NOT NULL,result TEXT NOT NULL);
CREATE TABLE attempts(job_id TEXT,attempt INTEGER,data TEXT,PRIMARY KEY(job_id,attempt));
CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
PRAGMA user_version=1;''')
    elif version == 1:
        # Publish only a complete backup. A failed attempt cannot replace a good copy.
        fd, name = tempfile.mkstemp(prefix='migration-', suffix='.sqlite', dir=data_dir)
        os.close(fd)
        try:
            backup = sqlite3.connect(name)
            try:
                db.backup(backup)
            finally:
                backup.close()
            os.replace(name, data_dir / 'state-before-v2.sqlite')
        finally:
            if os.path.exists(name):
                os.unlink(name)
    if version <= 1:
        db.execute('BEGIN IMMEDIATE')
        try:
            validate_legacy(db)
            for statement in (
                'ALTER TABLE jobs ADD COLUMN state TEXT',
                'ALTER TABLE jobs ADD COLUMN created_at TEXT',
                'ALTER TABLE jobs ADD COLUMN queue_order INTEGER',
                'ALTER TABLE jobs ADD COLUMN bucket TEXT',
                "UPDATE jobs SET state=json_extract(data,'$.state'), created_at=coalesce(json_extract(data,'$.created_at'),''), queue_order=rowid",
                "UPDATE jobs SET bucket=CASE WHEN state IN ('queued','needs_auth','extracting','downloading','waiting','cancelling') THEN 'active' ELSE 'history' END",
                'CREATE INDEX jobs_created ON jobs(created_at DESC,id DESC)',
                'CREATE INDEX jobs_bucket_created ON jobs(bucket,created_at DESC,id DESC)',
                'CREATE INDEX jobs_state_queue ON jobs(state,queue_order)',
                'CREATE TABLE queue_sequence(value INTEGER NOT NULL)',
                'INSERT INTO queue_sequence SELECT coalesce(max(queue_order),0) FROM jobs',
                'CREATE TABLE state_counts(state TEXT PRIMARY KEY,n INTEGER NOT NULL)',
                'INSERT INTO state_counts SELECT state,count(*) FROM jobs GROUP BY state',
                '''CREATE TRIGGER jobs_insert AFTER INSERT ON jobs BEGIN
INSERT INTO state_counts VALUES(new.state,1) ON CONFLICT(state) DO UPDATE SET n=n+1; END''',
                '''CREATE TRIGGER jobs_update AFTER UPDATE OF state ON jobs WHEN old.state!=new.state BEGIN
UPDATE state_counts SET n=n-1 WHERE state=old.state;
INSERT INTO state_counts VALUES(new.state,1) ON CONFLICT(state) DO UPDATE SET n=n+1; END''',
                '''CREATE TRIGGER jobs_delete AFTER DELETE ON jobs BEGIN
UPDATE state_counts SET n=n-1 WHERE state=old.state; END''',
                'PRAGMA user_version=2',
            ):
                db.execute(statement)
            db.commit()
        except Exception:
            db.rollback()
            raise


class JobStore:
    @classmethod
    def open(cls, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = open(data_dir / 'backend.lock', 'a+b')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise StoreError('already_running')
        db = sqlite3.connect(data_dir / 'state.sqlite', check_same_thread=False)
        try:
            os.chmod(data_dir / 'state.sqlite', 0o600)
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 2:
                raise StoreError('schema_too_new')
            migrate(db, data_dir, version)
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA cache_size=-2048')
            result = cls()
            result.db, result.lock, result.data_dir = db, lock, data_dir
            return result
        except Exception:
            db.close()
            lock.close()
            raise

    def apply_operation(self, operation_id, method, params, mutate):
        canonical = json.dumps([method, params], sort_keys=True, separators=(',', ':'))
        with self.db:
            row = self.db.execute('SELECT request,result FROM operations WHERE id=?', (operation_id,)).fetchone()
            if row:
                if row[0] != canonical:
                    raise StoreError('operation_conflict')
                return json.loads(row[1])
            result = mutate(self.db)
            self.db.execute('INSERT INTO operations VALUES (?,?,?)', (operation_id, canonical, json.dumps(result)))
            return result

    def save_job(self, job, db=None):
        target = db or self.db
        old = target.execute('SELECT state,queue_order FROM jobs WHERE id=?', (job['job_id'],)).fetchone()
        if old is None or (job['state'] == 'queued' and old[0] != 'queued'):
            order = target.execute('UPDATE queue_sequence SET value=value+1 RETURNING value').fetchone()[0]
        else:
            order = old[1]
        target.execute('''INSERT INTO jobs(id,data,state,created_at,queue_order,bucket) VALUES (?,?,?,?,?,?)
ON CONFLICT(id) DO UPDATE SET data=excluded.data,state=excluded.state,created_at=excluded.created_at,queue_order=excluded.queue_order,bucket=excluded.bucket''',
                       (job['job_id'], json.dumps(job), job['state'], job.get('created_at',''), order,
                        'active' if job['state'] in PENDING else 'history'))
        if db is None:
            target.commit()

    def get_job(self, job_id):
        row = self.db.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            raise StoreError('not_found')
        return json.loads(row[0])

    def has_jobs(self):
        return self.db.execute('SELECT EXISTS(SELECT 1 FROM jobs)').fetchone()[0] != 0

    def next_queued(self):
        row = self.db.execute("SELECT data FROM jobs WHERE state='queued' ORDER BY queue_order LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None

    def summary(self):
        counts = dict(self.db.execute('SELECT state,n FROM state_counts'))
        total, active = sum(counts.values()), sum(counts.get(s,0) for s in PENDING)
        return dict(total=total, active=active, history=total-active, completed=counts.get('completed',0),
                    failed=sum(counts.get(s,0) for s in FAILED), cancelled=counts.get('cancelled',0))

    def all_jobs(self):
        """Diagnostic/test helper; interactive operations must use indexed reads."""
        return [json.loads(r[0]) for r in self.db.execute('SELECT data FROM jobs ORDER BY queue_order')]

    def recover_interrupted(self):
        while True:
            rows = self.db.execute("SELECT data FROM jobs WHERE state IN ('extracting','downloading','waiting','cancelling') LIMIT 100").fetchall()
            if not rows:
                break
            with self.db:
                for row in rows:
                    job = json.loads(row[0])
                    job.update(state='interrupted', revision=job['revision']+1, updated_at=timestamp(), current_file=None)
                    self.save_job(job, self.db)

    def close(self):
        self.db.close()
        self.lock.close()
