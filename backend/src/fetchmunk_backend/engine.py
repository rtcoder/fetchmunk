"""Version-pinned adapter. Run inside a dedicated worker, never in the GUI."""

import collections
import contextlib
import os
import logging
from pathlib import Path
from .models import WorkerRequest, WorkerEvent, WorkerResult


def run_download(request: WorkerRequest, emit) -> WorkerResult:
    from gallery_dl import config, job, output, exception

    result = WorkerResult()
    config.clear()
    for key, value in {
        "base-directory": str(request.output_dir),
        "archive": str(request.archive_path),
        "postprocessors": [],
        "postprocess": False,
        "skip": True,
        "input": False,
        "retries": 2,
        "timeout": 20,
    }.items():
        config.set(("extractor",), key, value)
    config.set(("cache",), "file", ":memory:")
    config.set(("downloader",), "progress", 0.25)
    config.set(("downloader", "ytdl"), "enabled", False)
    try:
        request.output_dir.mkdir(parents=True, exist_ok=True)
        request.archive_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result.error_code = "disk_full" if exc.errno == 28 else "permission_denied"
        return result

    class Reporter(output.NullOutput):
        def start(self, path):
            emit(WorkerEvent("file.start", {"name": Path(path).name}))

        def success(self, path):
            result.downloaded += 1
            emit(WorkerEvent("file.success", {"downloaded": result.downloaded}))

        def skip(self, path):
            result.skipped += 1
            emit(WorkerEvent("file.skip", {"skipped": result.skipped}))

        def progress(self, total, done, speed):
            emit(
                WorkerEvent(
                    "file.progress",
                    {
                        "bytes_done": done,
                        "bytes_total": total or None,
                        "bytes_per_second": speed or None,
                    },
                )
            )

    reporter = Reporter()
    original_select = output.select
    output.select = lambda: reporter

    class DownloadJob(job.DownloadJob):
        def initialize(self, kwdict=None):
            super().initialize(kwdict)
            hooks = collections.defaultdict(list, self.hooks)
            hooks["error"].append(self.record_failure)
            self.hooks = hooks

        def record_failure(self, path):
            result.failed_files += 1
            emit(WorkerEvent("file.error", {"failed_files": result.failed_files}))

    class Errors(logging.Handler):
        def emit(self, record):
            # Inspect typed exceptions, never forward arbitrary messages/URLs.
            exc = record.exc_info[1] if record.exc_info else None
            if isinstance(exc, PermissionError):
                result.error_code = "permission_denied"
            elif isinstance(exc, OSError) and exc.errno == 28:
                result.error_code = "disk_full"

    handler = Errors()
    logger = logging.getLogger("gallery-dl")
    old_handlers, old_propagate = logger.handlers[:], logger.propagate
    logger.handlers, logger.propagate = [handler], False
    try:
        with (
            open(os.devnull, "w") as sink,
            contextlib.redirect_stdout(sink),
            contextlib.redirect_stderr(sink),
        ):
            task = DownloadJob(request.url)
            status = task.run()
        if status and not result.error_code:
            result.error_code = "engine_error"
    except exception.NoExtractorError:
        result.error_code = "unsupported_url"
    except PermissionError:
        result.error_code = "permission_denied"
    except OSError as exc:
        result.error_code = "disk_full" if exc.errno == 28 else "engine_error"
    except Exception:
        result.error_code = "engine_error"
    finally:
        output.select = original_select
        logger.handlers, logger.propagate = old_handlers, old_propagate
    return result
