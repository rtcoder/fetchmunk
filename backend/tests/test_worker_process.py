import json, os, subprocess, sys
from pathlib import Path


def test_worker_exits_cleanly_with_parent_pipe_open(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    p = subprocess.Popen(
        [sys.executable, "-m", "fetchmunk_backend", "--worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        p.stdin.write(
            json.dumps(
                dict(
                    job_id="j",
                    attempt=1,
                    url="https://example.org/unsupported",
                    output_dir=str(tmp_path),
                    archive_path=str(tmp_path / "archive"),
                )
            )
            + "\n"
        )
        p.stdin.flush()
        assert json.loads(p.stdout.readline())["kind"] == "result"
        p.wait(timeout=10)
        assert p.returncode == 0, p.stderr.read()
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
        p.stdin.close()
        p.stdout.close()
        p.stderr.close()
