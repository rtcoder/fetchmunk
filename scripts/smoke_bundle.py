"""Verify the shipped coordinator, not the development Python environment."""

import argparse, http.server, json, queue, subprocess, tempfile, threading, time
from pathlib import Path

MEDIA = b"\x89PNG\r\n\x1a\nfetchmunk-bundle-smoke"


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.end_headers()
        self.wfile.write(MEDIA)

    def log_message(self, *args):
        pass


def check(app):
    exe = app / "Contents/Helpers/FetchmunkBackend.app/Contents/MacOS/fetchmunk-backend"
    if not exe.is_file():
        raise SystemExit(f"Missing bundled backend: {exe}")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="Fetchmunk smoke ż ") as tmp:
            start = time.monotonic()
            p = subprocess.Popen(
                [str(exe)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=tmp,
                env={"PATH": "/usr/bin:/bin"},
                text=True,
            )
            messages = queue.Queue()

            def reader():
                for line in p.stdout:
                    messages.put(json.loads(line))

            threading.Thread(target=reader, daemon=True).start()

            def call(method, **params):
                params.setdefault("operation_id", method)
                p.stdin.write(
                    json.dumps(
                        dict(
                            protocol=1,
                            type="request",
                            id=method,
                            method=method,
                            params=params,
                        )
                    )
                    + "\n"
                )
                p.stdin.flush()
                while True:
                    response = messages.get(timeout=15)
                    if response.get("type") == "response" and response["id"] == method:
                        assert "error" not in response, response
                        return response["result"]

            try:
                hello = messages.get(timeout=10)
                assert hello["type"] == "hello"
                handshake = time.monotonic() - start
                call(
                    "session.initialize",
                    data_dir=tmp + "/state",
                    default_destination=tmp + "/files",
                )
                params = dict(
                    url=f"http://127.0.0.1:{server.server_port}/sample.png",
                    destination=tmp + "/files",
                )
                created = call("jobs.create", **params)
                assert call("jobs.create", **params) == created, (
                    "Duplicate operation created a job"
                )
                deadline = time.monotonic() + 20
                while True:
                    job = call("jobs.get", job_id=created["job_id"])
                    if job["state"] in {"completed", "failed", "partial", "empty"}:
                        break
                    assert time.monotonic() < deadline, "Download timeout"
                    time.sleep(0.05)
                assert job["state"] == "completed" and job["downloaded"] == 1, job
                assert any(
                    f.read_bytes() == MEDIA
                    for f in Path(job["output_dir"]).rglob("*")
                    if f.is_file()
                )
                call("app.shutdown", reason="quit")
                p.wait(timeout=10)
                assert p.returncode == 0, p.stderr.read()
                print(
                    json.dumps(
                        {
                            "result": "PASS",
                            "handshake_seconds": round(handshake, 3),
                            "engine": hello["engine_version"],
                            "downloaded": job["downloaded"],
                            "isolation": "PATH=/usr/bin:/bin; temporary cwd; no user config",
                            "idempotency": "PASS",
                            "shutdown": "PASS",
                        },
                        indent=2,
                    )
                )
            finally:
                if p.poll() is None:
                    p.kill()
                    p.wait()
                for stream in (p.stdin, p.stdout, p.stderr):
                    stream.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True)
    args = parser.parse_args()
    check(Path(args.app).resolve())
