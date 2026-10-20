"""Single-writer SQLite state. Caller serializes access with its service lock."""

import fcntl
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class StoreError(ValueError):
    pass


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    @classmethod
    def open(cls, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = open(data_dir / "backend.lock", "a+b")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise StoreError("already_running")
        db = sqlite3.connect(data_dir / "state.sqlite", check_same_thread=False)
        try:
            if db.execute("PRAGMA user_version").fetchone()[0] > 1:
                raise StoreError("schema_too_new")
            db.executescript("""CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, request TEXT NOT NULL, result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attempts (job_id TEXT, attempt INTEGER, data TEXT, PRIMARY KEY(job_id,attempt));
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
PRAGMA user_version=1;""")
            os.chmod(data_dir / "state.sqlite", 0o600)
            result = cls()
            result.db = db
            result.lock = lock
            result.data_dir = data_dir
            return result
        except Exception:
            db.close()
            lock.close()
            raise

    def apply_operation(self, operation_id, method, params, mutate):
        canonical = json.dumps([method, params], sort_keys=True, separators=(",", ":"))
        with self.db:
            row = self.db.execute(
                "SELECT request,result FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            if row:
                if row[0] != canonical:
                    raise StoreError("operation_conflict")
                return json.loads(row[1])
            result = mutate(self.db)
            self.db.execute(
                "INSERT INTO operations VALUES (?,?,?)",
                (operation_id, canonical, json.dumps(result)),
            )
            return result

    def save_job(self, job, db=None):
        target = db or self.db
        target.execute(
            "INSERT OR REPLACE INTO jobs VALUES (?,?)", (job["job_id"], json.dumps(job))
        )
        if db is None:
            target.commit()

    def get_job(self, job_id):
        row = self.db.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise StoreError("not_found")
        return json.loads(row[0])

    def all_jobs(self):
        return [
            json.loads(r[0])
            for r in self.db.execute("SELECT data FROM jobs ORDER BY rowid")
        ]

    def recover_interrupted(self):
        with self.db:
            for job in self.all_jobs():
                if job["state"] in {
                    "extracting",
                    "downloading",
                    "waiting",
                    "cancelling",
                }:
                    job.update(
                        state="interrupted",
                        revision=job["revision"] + 1,
                        updated_at=timestamp(),
                        current_file=None,
                    )
                    self.save_job(job, self.db)

    def close(self):
        self.db.close()
        self.lock.close()
