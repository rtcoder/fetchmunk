"""Exercise the frozen worker against a real local HTTP server."""

import http.server, json, subprocess, tempfile, threading, sys
from pathlib import Path

MEDIA = b"\x89PNG\r\n\x1a\nfetchmunk"


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.end_headers()
        self.wfile.write(MEDIA)

    def log_message(self, *args):
        pass


def check(executable):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="fetchmunk space ż ") as tmp:
            p = subprocess.Popen(
                [str(executable), "--worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=tmp,
                env={"PATH": "/usr/bin:/bin"},
                text=True,
            )
            try:
                p.stdin.write(
                    json.dumps(
                        dict(
                            job_id="test",
                            attempt=1,
                            url=f"http://127.0.0.1:{server.server_port}/test.png",
                            output_dir=tmp,
                            archive_path=tmp + "/archive.sqlite",
                        )
                    )
                    + "\n"
                )
                p.stdin.flush()
                timer = threading.Timer(20, p.kill)
                timer.start()
                lines = [json.loads(line) for line in p.stdout]
                p.wait(timeout=5)
                timer.cancel()
                assert p.returncode == 0, p.stderr.read()
                assert lines[-1]["data"]["downloaded"] == 1, lines
                files = [p for p in Path(tmp).rglob("*") if p.is_file()]
                assert any(p.read_bytes() == MEDIA for p in files), (
                    lines,
                    [str(p) for p in files],
                )
            finally:
                if p.poll() is None:
                    p.kill()
                    p.wait()
                p.stdin.close()
                p.stdout.close()
                p.stderr.close()
    finally:
        server.shutdown()
        server.server_close()
    print(
        "PASS frozen worker: HTTP bytes, isolated PATH, Unicode/spaces cwd, clean exit"
    )


if __name__ == "__main__":
    check(Path(sys.argv[1]).resolve())
