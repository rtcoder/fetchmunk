import json
import sqlite3
import pytest
from fetchmunk_backend.store import JobStore


def job(id, state='completed', attempt=1):
    return dict(job_id=id, state=state, attempt=attempt, revision=1, created_at='2026-01-01T00:00:00+00:00')


def legacy(path, invalid=False):
    db=sqlite3.connect(path/'state.sqlite')
    db.executescript('CREATE TABLE jobs(id TEXT PRIMARY KEY,data TEXT NOT NULL); CREATE TABLE operations(id TEXT PRIMARY KEY,request TEXT,result TEXT); CREATE TABLE attempts(job_id TEXT,attempt INTEGER,data TEXT,PRIMARY KEY(job_id,attempt)); CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT); PRAGMA user_version=1;')
    db.execute('INSERT INTO jobs VALUES (?,?)',('a','bad JSON' if invalid else json.dumps(job('a','queued'))))
    db.execute("INSERT INTO operations VALUES ('op','request','result')")
    db.execute("INSERT INTO attempts VALUES ('a',1,'old attempt')")
    db.commit();db.close()


def test_migration_preserves_data_and_private_backup(tmp_path):
    legacy(tmp_path)
    s=JobStore.open(tmp_path)
    try:
        assert s.db.execute('PRAGMA user_version').fetchone()[0]==2
        assert s.get_job('a')==job('a','queued')
        assert s.db.execute('SELECT result FROM operations').fetchone()[0]=='result'
        assert s.db.execute('SELECT data FROM attempts').fetchone()[0]=='old attempt'
        backup=tmp_path/'state-before-v2.sqlite'
        assert backup.stat().st_mode & 0o777 == 0o600
        db=sqlite3.connect(backup)
        assert db.execute('PRAGMA user_version').fetchone()[0]==1
        db.close()
    finally:s.close()


def test_bad_migration_rolls_back_schema(tmp_path):
    legacy(tmp_path,invalid=True)
    with pytest.raises(sqlite3.DatabaseError):JobStore.open(tmp_path)
    db=sqlite3.connect(tmp_path/'state.sqlite')
    assert db.execute('PRAGMA user_version').fetchone()[0]==1
    assert [x[1] for x in db.execute('PRAGMA table_info(jobs)')]==['id','data']
    assert db.execute('SELECT data FROM jobs').fetchone()[0]=='bad JSON'
    db.close()


def test_fifo_survives_updates_and_retry_goes_to_tail(tmp_path):
    s=JobStore.open(tmp_path)
    try:
        a,b=job('a','queued'),job('b','queued')
        s.save_job(a);s.save_job(b);a['revision']=2;s.save_job(a)
        assert s.next_queued()['job_id']=='a'
        a['state']='cancelled';s.save_job(a)
        a.update(state='queued',attempt=2);s.save_job(a)
        assert s.next_queued()['job_id']=='b'
        b['state']='completed';s.save_job(b)
        assert s.summary()==dict(total=2,active=1,history=1,completed=1)
        with pytest.raises(ValueError):
            with s.db:
                s.save_job(job('c','queued'),s.db)
                raise ValueError('rollback')
        assert s.summary()['total']==2
    finally:s.close()


def test_large_store_reopens_and_recovery_only_reads_active(tmp_path,monkeypatch):
    s=JobStore.open(tmp_path)
    with s.db:
        for i in range(1001):s.save_job(job(str(i)),s.db)
        s.save_job(job('active','downloading'),s.db)
    s.close();s=JobStore.open(tmp_path)
    try:
        monkeypatch.setattr(s,'all_jobs',lambda:pytest.fail('full history read'))
        s.recover_interrupted()
        assert s.get_job('active')['state']=='interrupted'
        assert s.summary()['total']==1002
        assert s.has_jobs()
        assert s.next_queued() is None
    finally:s.close()


def test_backup_failure_does_not_start_migration(tmp_path):
    legacy(tmp_path)
    (tmp_path/'state-before-v2.sqlite').mkdir()
    with pytest.raises(OSError):JobStore.open(tmp_path)
    db=sqlite3.connect(tmp_path/'state.sqlite')
    assert db.execute('PRAGMA user_version').fetchone()[0]==1
    assert [x[1] for x in db.execute('PRAGMA table_info(jobs)')]==['id','data']
    db.close()
