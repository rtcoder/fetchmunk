"""Persistent coordinator. All state transitions are serialized under one lock."""

import json, os, queue, sqlite3, sys, threading, time, uuid
from pathlib import Path
from urllib.parse import urlunsplit
from . import __version__
from .models import WorkerRequest
from .store import JobStore, StoreError, timestamp
from .url_validation import validate_url
from .snapshots import SnapshotStore, SnapshotError
from .supervisor import WorkerSupervisor
from .credentials import Vault, VaultError
from .browser_credentials import BrowserConnector, BrowserError, service_for_url, parse_cookies, scoped_cookies
from .wire import FrameDecoder, ProtocolError, encode_frame

ACTIVE = {"extracting", "downloading", "waiting", "cancelling"}
RETRY = {"failed", "partial", "cancelled", "interrupted", "needs_auth"}


class JobService:
    def __init__(self, emit, supervisor_factory=WorkerSupervisor):
        self.emit = emit
        self.lock = threading.RLock()
        self.store = None
        self.vault = None
        self.closed = False
        self.session_id = str(uuid.uuid4())
        self.seq = 0
        self.queue_enabled = True
        self.destination = None
        self.active = None
        self.stopping = False
        self.last_progress = 0
        self.supervisor = supervisor_factory(self.on_worker)
        self.snapshots = SnapshotStore()

    def event(self, name, data):
        self.seq += 1
        self.emit(
            {
                "protocol": 1,
                "type": "event",
                "session_id": self.session_id,
                "seq": self.seq,
                "event": name,
                "data": data,
            }
        )

    def changed(self, job):
        job["revision"] += 1
        job["updated_at"] = timestamp()
        self.store.save_job(job)
        self.snapshots.maintain(self.store)
        self.event(
            "job.changed", {"job_id": job["job_id"], "revision": job["revision"]}
        )

    def handle(self, request):
        method = request.get("method")
        if isinstance(method, str) and method.startswith("auth."):
            return self.handle_auth_request(request)
        with self.lock:
            response = {"protocol": 1, "type": "response", "id": request.get("id")}
            try:
                method = request.get("method")
                params = request.get("params", {})
                if not isinstance(method, str) or not isinstance(params, dict):
                    raise StoreError("invalid_params")
                if method == "session.initialize":
                    if self.store:
                        raise StoreError("invalid_state")
                    data = self.absolute_path(params.get("data_dir"))
                    self.destination = self.absolute_path(
                        params.get("default_destination")
                    )
                    self.store = JobStore.open(data)
                    self.vault = Vault(data / "credentials.json", write_allowed=lambda: not self.stopping and not self.closed)
                    self.queue_enabled = not self.store.has_jobs()
                    self.store.recover_interrupted()
                    result = {"schema_version": 2, "queue_enabled": self.queue_enabled}
                elif not self.store or self.closed or self.stopping:
                    raise StoreError("invalid_state")
                elif method == "jobs.get":
                    result = self.store.get_job(params.get("job_id"))
                elif method == "jobs.summary":
                    result = self.store.summary()
                    result["current_job"] = self.store.get_job(self.active) if self.active else None
                    result["queue_enabled"] = self.queue_enabled
                    result["at_seq"] = self.seq
                elif method == "jobs.snapshot":
                    limit = params.get("limit", 100)
                    result = (
                        self.snapshots.page(params["cursor"], limit, params.get("filter"),
                                            **({"query": params["query"]} if "query" in params else {}))
                        if params.get("cursor")
                        else self.snapshots.create(
                            self.store, self.seq, limit, params.get("filter", "all"), params.get("anchor"),
                            params.get("query", "")
                        )
                    )
                elif method == "sources.inspect":
                    from .sources import inspect_source
                    result = inspect_source(params.get("url"))
                elif method == "app.shutdown":
                    self.stopping = True
                    self.queue_enabled = False
                    result = {"accepted": True}
                elif method in {
                    "jobs.create",
                    "jobs.create_many",
                    "jobs.cancel",
                    "jobs.retry",
                    "queue.set_enabled",
                }:
                    op = params.get("operation_id")
                    if not isinstance(op, str) or not 1 <= len(op) <= 128:
                        raise StoreError("invalid_params")
                    # side effects are applied after commit; cached result has no duplicate side effects
                    effects = []
                    result = self.store.apply_operation(
                        op,
                        method,
                        params,
                        lambda db: self.mutate(method, params, db, effects),
                    )
                    for kind, value in effects:
                        if kind == "job":
                            self.event(
                                "job.changed",
                                {
                                    "job_id": value["job_id"],
                                    "revision": value["revision"],
                                },
                            )
                        elif kind == "cancel":
                            self.supervisor.stop("cancel")
                        elif kind == "queue":
                            self.queue_enabled = value
                            self.event("queue.changed", {"queue_enabled": value})
                else:
                    raise StoreError("unknown_method")
                response["result"] = result
            except (StoreError, SnapshotError, VaultError, BrowserError) as exc:
                code = str(exc)
                response["error"] = {
                    "code": code,
                    "message_key": "error." + code,
                    "retryable": False,
                }
            except (ValueError, TypeError, KeyError):
                response["error"] = {
                    "code": "invalid_params",
                    "message_key": "error.invalid_params",
                    "retryable": False,
                }
            except sqlite3.DatabaseError as exc:
                code = "disk_full" if getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL else "database_error"
                response["error"] = {"code": code, "message_key": "error."+code, "retryable": False}
            except OSError as exc:
                code = "disk_full" if exc.errno == 28 else "permission_denied"
                response["error"] = {
                    "code": code,
                    "message_key": "error." + code,
                    "retryable": True,
                }
            try:
                self.pump()
                if self.store:
                    self.snapshots.maintain(self.store)
            except (sqlite3.DatabaseError, OSError) as exc:
                self.pause_for_storage_error(exc)
            return response

    def pause_for_storage_error(self, exc):
        # A create may already be committed: keep its successful response/idempotency.
        active, self.active = self.active, None
        self.queue_enabled = False
        code = "disk_full" if getattr(exc, "errno", None) == 28 or getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL else "database_error"
        if self.store:
            try:
                self.store.db.rollback()
                if active:
                    job = self.store.get_job(active)
                    if job["state"] in ACTIVE:
                        job.update(state="interrupted",revision=job["revision"]+1,updated_at=timestamp(),current_file=None)
                        self.store.save_job(job)
                        self.event("job.changed", {"job_id":active,"revision":job["revision"]})
            except (sqlite3.DatabaseError, OSError):
                self.store.db.rollback()
        if active:
            self.supervisor.stop("storage_error")
        self.event("queue.changed", {"queue_enabled":False,"error":{"code":code}})

    @staticmethod
    def absolute_path(value):
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 4096
            or "\0" in value
        ):
            raise StoreError("invalid_params")
        p = Path(value)
        if not p.is_absolute():
            raise StoreError("invalid_params")
        return p

    def mutate(self, method, p, db, effects):
        if method == "queue.set_enabled":
            if type(p.get("enabled")) is not bool:
                raise StoreError("invalid_params")
            db.execute(
                "INSERT OR REPLACE INTO settings VALUES (?,?)",
                ("queue_enabled", json.dumps(p["enabled"])),
            )
            effects.append(("queue", p["enabled"]))
            return {"queue_enabled": p["enabled"]}
        if method in {"jobs.create", "jobs.create_many"}:
            urls = p.get("urls") if method == "jobs.create_many" else [p.get("url")]
            if not isinstance(urls, list) or not 1 <= len(urls) <= 100:
                raise StoreError("invalid_params")
            parsed_urls = [(url, validate_url(url)) for url in urls]
            if method == "jobs.create_many" and sum(len(url.encode("utf-8")) for url in urls) > 524288:
                raise StoreError("invalid_params")
            dest = self.absolute_path(p.get("destination"))
            unique = dict(parsed_urls)
            jobs = [self.create_job(url, parsed, dest, db, effects) for url, parsed in unique.items()]
            if method == "jobs.create":
                return jobs[0]
            return {"jobs": jobs, "created_count": len(jobs), "duplicate_count": len(urls) - len(jobs)}
        job = self.store.get_job(p.get("job_id"))
        if method == "jobs.cancel":
            if job["state"] not in ACTIVE | {"queued", "needs_auth"}:
                return job
            job["state"] = "cancelling" if job["job_id"] == self.active else "cancelled"
            if job["state"] == "cancelling":
                effects.append(("cancel", None))
        else:
            if job["state"] not in RETRY:
                raise StoreError("invalid_state")
            db.execute(
                "INSERT OR REPLACE INTO attempts VALUES (?,?,?)",
                (job["job_id"], job["attempt"], json.dumps(job)),
            )
            job.update(
                attempt=job["attempt"] + 1,
                state="queued",
                downloaded=0,
                skipped=0,
                failed_files=0,
                current_file=None,
                error=None,
                wait_until=None,
            )
        job["revision"] += 1
        job["updated_at"] = timestamp()
        self.store.save_job(job, db)
        effects.insert(0, ("job", job))
        return job

    def create_job(self, url, parsed, dest, db, effects):
        jid = str(uuid.uuid4())
        out = dest / ("Fetchmunk-" + jid[:12])
        while out.exists():
            jid = str(uuid.uuid4())
            out = dest / ("Fetchmunk-" + jid[:12])
        now = timestamp()
        job = {
            "job_id": jid,
            "revision": 1,
            "attempt": 1,
            "state": "queued",
            "url": url,
            "display_url": urlunsplit(
                (parsed.scheme, parsed.netloc, parsed.path, "", "")
            ),
            "destination": str(dest),
            "output_dir": str(out),
            "created_at": now,
            "updated_at": now,
            "auth_ref": None,
            "downloaded": 0,
            "skipped": 0,
            "failed_files": 0,
            "current_file": None,
            "wait_until": None,
            "error": None,
        }
        self.store.save_job(job, db)
        effects.append(("job", job))
        return {"job_id": jid, "revision": 1}

    @staticmethod
    def error_response(request, code):
        return {"protocol": 1, "type": "response", "id": request.get("id"),
                "error": {"code": code, "message_key": "error." + code, "retryable": False}}

    def handle_auth_request(self, request):
        # Native consent and browser readers may block indefinitely. Never hold
        # the coordinator lock while running them, nor touch SQLite from here.
        try:
            with self.lock:
                if not self.store or self.closed or self.stopping:
                    raise StoreError("invalid_state")
                params = request.get("params", {})
                if not isinstance(params, dict):
                    raise StoreError("invalid_params")
            result = self.handle_auth(request["method"], params)
            return {"protocol": 1, "type": "response", "id": request.get("id"), "result": result}
        except (StoreError, VaultError, BrowserError) as error:
            return self.error_response(request, str(error))
        except (TypeError, ValueError, KeyError):
            return self.error_response(request, "invalid_params")
        except Exception:
            return self.error_response(request, "credential_unavailable")

    def handle_auth(self, method, params):
        # Deliberately outside apply_operation: its journal must never see secrets.
        if self.closed or self.stopping:
            raise StoreError("invalid_state")
        if method == "auth.list":
            return {"profiles": self.vault.list_profiles(), "reset": self.vault.last_reset}
        if method == "auth.browsers":
            return {"browsers": BrowserConnector().capabilities()}
        if method == "auth.delete":
            self.vault.delete(params.get("id")); return {"deleted": True}
        service = params.get("service")
        if service not in {"youtube", "cda"}: raise StoreError("invalid_credentials")
        if method == "auth.save":
            kind, secret = params.get("kind"), params.get("secret")
            if kind == "cookies":
                if not isinstance(secret, dict): raise StoreError("invalid_credentials")
                secret = {"cookies": scoped_cookies(secret.get("cookies", []), service)}
        elif method == "auth.import_text":
            kind, secret = "cookies", {"cookies": parse_cookies(params.get("text"), service)}
        elif method == "auth.import_browser":
            if params.get("consent") is not True: raise StoreError("consent_required")
            kind = "cookies"
            secret = {"cookies": BrowserConnector().import_cookies(service, params.get("browser"), params.get("profile"))}
        else: raise StoreError("unknown_method")
        if len(json.dumps(secret).encode("utf-8")) > 262144: raise StoreError("credentials_too_large")
        if self.closed or self.stopping:
            raise StoreError("invalid_state")
        return self.vault.save(params.get("id"), service, params.get("label"), kind, secret)

    def pump(self):
        if (
            not self.store
            or self.active
            or not self.queue_enabled
            or self.stopping
            or self.closed
        ):
            return
        while (job := self.store.next_queued()) is not None:
            self.active = job["job_id"]
            job["state"] = "extracting"
            self.changed(job)
            try:
                archive = self.store.data_dir / "archives" / f"{job['job_id']}.sqlite"
                service = service_for_url(job["url"])
                credential_path = None
                if self.vault and service and any(p["service"] == service for p in self.vault.list_profiles()):
                    credential_path = str(self.vault.path)
                self.supervisor.start(
                    WorkerRequest(
                        job["job_id"],
                        job["attempt"],
                        job["url"],
                        Path(job["output_dir"]),
                        archive,
                        credential_path=credential_path,
                    )
                )
            except (VaultError, BrowserError) as exc:
                self.active = None
                job.update(state="needs_auth", error=self.error(exc.code))
                self.changed(job)
                continue
            except Exception:
                self.active = None
                job.update(state="failed", error=self.error("engine_error"))
                self.changed(job)
                continue
            break

    @staticmethod
    def error(code):
        return {
            "code": code,
            "message_key": "error." + code,
            "retryable": code not in {"unsupported_url", "dependency_unsupported"},
            "action": "authenticate"
            if code in {"auth_required", "auth_expired", "credential_lost", "credential_locked", "credential_unavailable"}
            else "check_destination"
            if code in {"disk_full", "permission_denied"}
            else "retry",
        }

    def on_worker(self, request, event):
        try:
            self._on_worker(request, event)
        except (sqlite3.DatabaseError, OSError) as exc:
            with self.lock:
                self.pause_for_storage_error(exc)

    def _on_worker(self, request, event):
        with self.lock:
            if self.closed or not self.store or self.active != request.job_id:
                return
            job = self.store.get_job(request.job_id)
            if job["attempt"] != request.attempt or job["state"] not in ACTIVE:
                return
            kind = event.get("kind")
            data = event.get("data", {})
            if kind in {"result", "exit"}:
                if job["state"] == "cancelling":
                    job["state"] = "cancelled"
                elif self.stopping:
                    job["state"] = "interrupted"
                else:
                    for key in ("downloaded", "skipped", "failed_files"):
                        if key in data:
                            job[key] = data[key]
                    code = data.get("error_code") or (
                        "engine_error" if kind == "exit" else None
                    )
                    if code == "credential_lost" and self.vault:
                        self.vault.last_reset = True
                    job["error"] = self.error(code) if code else None
                    total = job["downloaded"] + job["skipped"]
                    job["state"] = (
                        "needs_auth"
                        if code in {"auth_required", "auth_expired", "credential_lost", "credential_locked", "credential_unavailable"}
                        else ("partial" if total else "failed")
                        if code
                        else ("completed" if total else "empty")
                    )
                job["current_file"] = None
                self.active = None
                self.changed(job)
                self.pump()
                return
            if job["state"] == "cancelling":
                return
            if kind == "file.start":
                job.update(
                    state="downloading",
                    current_file={
                        "name": data["name"],
                        "bytes_done": 0,
                        "bytes_total": None,
                        "bytes_per_second": None,
                    },
                )
            elif kind == "file.progress":
                if job["current_file"]:
                    job["current_file"].update(data)
                if time.monotonic() - self.last_progress < 0.25:
                    return
                self.last_progress = time.monotonic()
            elif kind in {"file.success", "file.skip", "file.error"}:
                for key in ("downloaded", "skipped", "failed_files"):
                    if key in data:
                        job[key] = data[key]
            else:
                return
            self.changed(job)

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.stopping = True
            self.queue_enabled = False
        self.supervisor.stop("quit")
        if hasattr(self.supervisor, "join"):
            self.supervisor.join(6)
        with self.lock:
            self.snapshots.close()
            try:
                if self.store:
                    self.store.recover_interrupted()
            finally:
                if self.store:
                    self.store.close()
                self.closed = True



class AuthDispatcher:
    """One daemon consumer with a single occupied slot; excess auth is rejected."""
    def __init__(self, service, emit):
        self.service = service
        self.emit = emit
        self.requests = queue.Queue(maxsize=1)
        self.slot = threading.BoundedSemaphore(1)
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="fetchmunk-auth")
        self.thread.start()

    def submit(self, request):
        if self.stopped.is_set():
            self.emit(self.service.error_response(request, "invalid_state"))
        elif not self.slot.acquire(blocking=False):
            self.emit(self.service.error_response(request, "auth_busy"))
        else:
            self.requests.put_nowait(request)

    def _run(self):
        while not self.stopped.is_set():
            try:
                request = self.requests.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if not self.stopped.is_set():
                    response = self.service.handle(request)
                    if not self.stopped.is_set():
                        self.emit(response)
            finally:
                self.slot.release()

    def close(self):
        # Never join a thread waiting for native consent. Vault's lifecycle
        # guard rejects delayed writes once JobService starts shutting down.
        self.stopped.set()


def serve():
    incoming = queue.Queue(maxsize=128)
    outgoing = queue.Queue(maxsize=128)
    failed = threading.Event()

    def emit(message):
        if failed.is_set():
            return
        try:
            outgoing.put(encode_frame(message), timeout=5)
        except queue.Full:
            failed.set()
            try:
                incoming.put_nowait(None)
            except queue.Full:
                pass

    service = JobService(emit)
    from gallery_dl.version import __version__ as engine_version

    def writer():
        import select

        fd = sys.stdout.fileno()
        os.set_blocking(fd, False)
        while True:
            data = outgoing.get()
            if data is None:
                return
            deadline = time.monotonic() + 5
            try:
                while data:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not select.select([], [fd], [], remaining)[1]:
                        raise TimeoutError()
                    try:
                        n = os.write(fd, data)
                    except BlockingIOError:
                        continue
                    data = data[n:]
            except (OSError, TimeoutError):
                failed.set()
                try:
                    incoming.put_nowait(None)
                except queue.Full:
                    pass
                return

    def reader():
        decoder = FrameDecoder()
        try:
            while chunk := os.read(sys.stdin.fileno(), 65536):
                for frame in decoder.feed(chunk):
                    incoming.put(frame)
            decoder.finish()
        except (OSError, ProtocolError):
            pass
        finally:
            incoming.put(None)

    w = threading.Thread(target=writer, daemon=True)
    w.start()
    threading.Thread(target=reader, daemon=True).start()
    emit(
        {
            "protocol": 1,
            "type": "hello",
            "session_id": service.session_id,
            "backend_version": __version__,
            "engine_version": engine_version,
            "capabilities": ["jobs", "paged_jobs", "history_search", "batch_jobs", "source_inspection", "credentials", "video_downloads"],
        }
    )
    auth = AuthDispatcher(service, emit)
    try:
        while not failed.is_set():
            req = incoming.get()
            if req is None:
                break
            if req.get("type") != "request" or not isinstance(req.get("id"), str):
                break
            method = req.get("method")
            if isinstance(method, str) and method.startswith("auth."):
                auth.submit(req)
            else:
                emit(service.handle(req))
            if service.stopping:
                break
    finally:
        auth.close()
        service.close()
        if not failed.is_set():
            outgoing.put(None, timeout=5)
            w.join(5)
