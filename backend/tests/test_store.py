import importlib, json, sqlite3
import pytest


def api():
    try:
        return importlib.import_module("fetchmunk_backend.store")
    except ModuleNotFoundError:
        pytest.fail("persistent store missing")


def test_operation_survives_restart_and_conflicts(tmp_path):
    s = api()
    store = s.JobStore.open(tmp_path)

    def mutate(db):
        db.execute(
            "INSERT INTO jobs(id,data) VALUES (?,?)",
            ("j", json.dumps({"job_id": "j", "state": "queued"})),
        )
        return {"job_id": "j"}

    assert store.apply_operation("op", "create", {"x": 1}, mutate) == {"job_id": "j"}
    store.close()
    store = s.JobStore.open(tmp_path)
    assert store.apply_operation(
        "op", "create", {"x": 1}, lambda db: pytest.fail("duplicate mutation")
    ) == {"job_id": "j"}
    with pytest.raises(s.StoreError, match="operation_conflict"):
        store.apply_operation("op", "create", {"x": 2}, mutate)
    store.close()


def test_transaction_rollback_and_exclusive_lock(tmp_path):
    s = api()
    store = s.JobStore.open(tmp_path)
    with pytest.raises(s.StoreError, match="already_running"):
        s.JobStore.open(tmp_path)

    def broken(db):
        db.execute("INSERT INTO jobs(id,data) VALUES ('bad','{}')")
        raise ValueError("failure")

    with pytest.raises(ValueError):
        store.apply_operation("op", "x", {}, broken)
    assert store.all_jobs() == []
    store.close()


def test_recovery_and_newer_schema(tmp_path):
    s = api()
    store = s.JobStore.open(tmp_path)
    store.save_job({"job_id": "j", "state": "downloading", "revision": 2, "attempt": 1})
    store.recover_interrupted()
    assert store.get_job("j")["state"] == "interrupted"
    store.db.execute("PRAGMA user_version=99")
    store.close()
    with pytest.raises(s.StoreError, match="schema_too_new"):
        s.JobStore.open(tmp_path)
