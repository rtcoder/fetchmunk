import json
import os
import sys
import threading
from dataclasses import asdict
from pathlib import Path
from fetchmunk_backend.models import WorkerRequest


def worker():
    from fetchmunk_backend.engine import run_download

    channel = sys.stdout

    def send(value):
        channel.write(json.dumps(value, ensure_ascii=False) + "\n")
        channel.flush()

    raw = sys.stdin.buffer.readline(1048577)
    data = json.loads(raw)
    request = WorkerRequest(
        **{
            **data,
            "output_dir": Path(data["output_dir"]),
            "archive_path": Path(data["archive_path"]),
        }
    )

    # The parent keeps stdin open. EOF must stop even a blocked extractor.
    def watch_parent():
        os.read(sys.stdin.fileno(), 1)
        os._exit(2)

    threading.Thread(target=watch_parent, daemon=True).start()
    result = run_download(
        request, lambda event: send({"kind": event.kind, "data": event.data})
    )
    send({"kind": "result", "data": asdict(result)})


def main():
    if "--worker" in sys.argv:
        worker()
    else:
        from fetchmunk_backend.service import serve

        serve()


if __name__ == "__main__":
    main()
