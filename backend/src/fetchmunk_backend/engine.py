"""Version-pinned adapter. Run inside a dedicated worker, never in the GUI."""

import collections
import contextlib
import os
import logging
from pathlib import Path
from .models import WorkerRequest, WorkerEvent, WorkerResult


def run_download(request: WorkerRequest, emit) -> WorkerResult:
    from dataclasses import replace
    from .sources import normalize_source_url
    request = replace(request, url=normalize_source_url(request.url))
    from .browser_credentials import service_for_url
    if request.engine == "yt-dlp" or service_for_url(request.url):
        from .video_engine import run_video
        service = service_for_url(request.url)
        if service and request.credential_path:
            from .credentials import Vault, VaultError
            try:
                vault = Vault(Path(request.credential_path))
                credentials = vault.resolve(service)
                if vault.last_reset:
                    return WorkerResult(error_code="credential_lost")
            except VaultError as error:
                return WorkerResult(error_code=error.code)
            request = replace(request, credentials=credentials)
        return run_video(request, emit)
    from gallery_dl import config, job, output, exception, util

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
    original_expand = util.expand_path
    literal_paths = {str(request.output_dir), str(request.archive_path)}
    util.expand_path = lambda path: path if path in literal_paths else original_expand(path)
    original_select = output.select
    output.select = lambda: reporter

    def classify_error(exc):
        if isinstance(exc, (exception.AuthenticationError, exception.AuthRequired)):
            return "auth_required"
        if isinstance(exc, exception.AuthorizationError):
            return "access_denied"
        if isinstance(exc, exception.HttpError):
            return "access_denied" if exc.status == 403 else "network_error"
        if isinstance(exc, exception.NoExtractorError):
            return "unsupported_url"
        if isinstance(exc, PermissionError):
            return "permission_denied"
        if isinstance(exc, OSError) and exc.errno == 28:
            return "disk_full"
        return None

    class DownloadJob(job.DownloadJob):
        def dispatch(self, messages):
            # Job.run consumes extractor exceptions before returning a bitmask.
            # Capture the actual type here, including jobs queued by extractors.
            try:
                return super().dispatch(messages)
            except Exception as exc:
                code = classify_error(exc)
                if code:
                    result.error_code = code
                raise

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
            code = classify_error(exc)
            if code:
                result.error_code = code

    handler = Errors()
    # Extractor loggers are named by category, not under "gallery-dl".
    # This adapter runs in a dedicated worker; sink all root output locally.
    logger = logging.getLogger()
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
    except Exception as exc:
        result.error_code = classify_error(exc) or "engine_error"
    finally:
        util.expand_path = original_expand
        output.select = original_select
        logger.handlers, logger.propagate = old_handlers, old_propagate
    return result
