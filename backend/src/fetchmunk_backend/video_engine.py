"""Pinned yt-dlp adapter for a dedicated worker; never persist authentication."""

import contextlib
import hashlib
from http.cookiejar import Cookie, DefaultCookiePolicy
import logging
import math
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

from .models import WorkerEvent, WorkerRequest, WorkerResult


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1e16 else None


def _error_code(exc):
    from yt_dlp.networking.exceptions import HTTPError, TransportError
    from yt_dlp.utils import DownloadError, ExtractorError, GeoRestrictedError, UnsupportedError

    seen = set()
    while isinstance(exc, BaseException) and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, UnsupportedError):
            return 'unsupported_url'
        if isinstance(exc, GeoRestrictedError):
            return 'access_denied'
        if isinstance(exc, HTTPError):
            return {401: 'auth_required', 403: 'access_denied'}.get(exc.status, 'network_error')
        if isinstance(exc, TransportError):
            return 'network_error'
        if isinstance(exc, (PermissionError, FileExistsError, NotADirectoryError)):
            return 'permission_denied'
        if isinstance(exc, OSError) and exc.errno == 28:
            return 'disk_full'
        # yt-dlp wraps typed failures. Never classify arbitrary message text,
        # including authentication/expiry hints embedded in extractor messages.
        if isinstance(exc, (DownloadError, ExtractorError)):
            wrapped = getattr(exc, 'exc_info', None)
            exc = getattr(exc, 'cause', None) or (wrapped[1] if wrapped else None)
        else:
            break
    return 'engine_error'


def _ffmpeg_binary():
    import imageio_ffmpeg

    bundle = getattr(sys, '_MEIPASS', None)
    root = Path(bundle) / 'imageio_ffmpeg' if bundle else Path(imageio_ffmpeg.__file__).parent
    binaries = sorted(path for path in (root / 'binaries').glob('ffmpeg-*') if path.is_file())
    if len(binaries) != 1:
        raise FileNotFoundError('Bundled FFmpeg missing or ambiguous')
    # Never consult IMAGEIO_FFMPEG_EXE, PATH, or a user-installed runtime.
    return str(binaries[0].resolve())


def _deno_binary():
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle:
        path = Path(bundle) / 'deno-bin' / ('deno.exe' if os.name == 'nt' else 'deno')
        if path.is_file():
            return str(path.resolve())
        raise FileNotFoundError('Bundled JavaScript runtime missing')
    import deno
    return str(Path(deno.find_deno_bin()).resolve())


def _host_is(host, root):
    return host == root or host.endswith('.' + root)


def _inject_cookies(ydl, credentials, host):
    from .browser_credentials import scoped_cookies, service_for_url

    service = service_for_url('https://' + host)
    if service is None:
        return
    # Python's default Netscape policy permits host-only cookies on subdomains.
    # Preserve the imported flag and enforce it on every outgoing request.
    ydl.cookiejar.set_policy(DefaultCookiePolicy(
        strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain,
    ))
    for item in scoped_cookies(credentials.get('cookies', []), service):
        domain = item['domain']
        expires = item.get('expires')
        ydl.cookiejar.set_cookie(Cookie(
            version=0, name=item['name'], value=item['value'], port=None,
            port_specified=False, domain=domain, domain_specified=item['domain_specified'],
            domain_initial_dot=domain.startswith('.'), path=item.get('path', '/'),
            path_specified=True, secure=bool(item.get('secure', False)),
            expires=int(expires) if expires is not None and expires > 0 else None,
            discard=not expires or expires <= 0, comment=None, comment_url=None,
            rest={'HttpOnly': None} if item['http_only'] else {}, rfc2109=False,
        ))


def run_video(request: WorkerRequest, emit) -> WorkerResult:
    import yt_dlp
    from yt_dlp import globals as yt_globals
    result = WorkerResult()
    credentials = getattr(request, 'credentials', None)
    host = (urlsplit(request.url).hostname or '').lower()
    if credentials and credentials.get('kind') == 'password' and not _host_is(host, 'cda.pl'):
        result.error_code = 'access_denied'
        return result

    class QuietLogger:
        def debug(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): pass
        def warning(self, *args, **kwargs): pass
        def error(self, *args, **kwargs): pass

    def progress(data):
        if data.get('status') == 'downloading':
            emit(WorkerEvent('file.progress', {
                'bytes_done': _number(data.get('downloaded_bytes')) or 0,
                'bytes_total': _number(data.get('total_bytes')) or _number(data.get('total_bytes_estimate')),
                'bytes_per_second': _number(data.get('speed')),
            }))

    # The public yt-dlp API does not load CLI config files. Its plugin loader is
    # process-global, however; disable discovery before constructing YoutubeDL.
    old_plugin_dirs = yt_globals.plugin_dirs.value
    yt_globals.plugin_dirs.value = []
    logger = logging.getLogger()
    old_handlers = logger.handlers[:]
    logger.handlers = [logging.NullHandler()]
    try:
        with open(os.devnull, 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            request.output_dir.mkdir(parents=True, exist_ok=True)
            filename = str(int(hashlib.sha256(request.url.encode()).hexdigest()[:24], 16))
            options = {
                'format': 'bestvideo+bestaudio/best',
                'outtmpl': filename + '.%(ext)s',
                'cachedir': False, 'noplaylist': True, 'ignoreerrors': False,
                'quiet': True, 'no_warnings': True, 'noprogress': True,
                'logger': QuietLogger(), 'progress_hooks': [progress],
                'retries': 2, 'fragment_retries': 2, 'extractor_retries': 2,
                'socket_timeout': 20, 'overwrites': False,
                'allow_unplayable_formats': False, 'usenetrc': False,
                'remote_components': [], 'color': 'never',
                'ffmpeg_location': _ffmpeg_binary(),
                'js_runtimes': {'deno': {'path': _deno_binary()}},
            }
            if credentials and credentials.get('kind') == 'password':
                options.update(username=credentials['username'], password=credentials['password'], allowed_extractors=['CDA'])

            class Downloader(yt_dlp.YoutubeDL):
                def get_output_path(self, dir_type='', filename=None):
                    # Keep destination literal: upstream expands $HOME and ~.
                    return str(request.output_dir / (filename or ''))

            with Downloader(options) as ydl:
                if credentials and credentials.get('kind') == 'cookies':
                    _inject_cookies(ydl, credentials, host)
                info = ydl.extract_info(request.url, download=False, process=False)
                if not isinstance(info, dict):
                    raise ValueError('No video metadata')
                if info.get('_type', 'video') != 'video':
                    result.error_code = 'unsupported_url'
                    return result
                formats = info.get('formats') or []
                if info.get('has_drm') is True or formats and all(f.get('has_drm') is True for f in formats):
                    result.error_code = 'drm_protected'
                    return result
                emit(WorkerEvent('video.formats', {'formats': [
                    {key: _number(fmt.get(key)) for key in ('height', 'width', 'fps', 'tbr')}
                    for fmt in formats[:256] if fmt.get('has_drm') is not True
                ]}))
                emit(WorkerEvent('file.start', {'name': filename}))
                completed = ydl.process_ie_result(info, download=True)
                if not isinstance(completed, dict):
                    raise ValueError('No completed video')
                downloads = completed.get('requested_downloads', [])
                if downloads and all(item.get('__real_download') is False for item in downloads):
                    result.skipped = 1
                    emit(WorkerEvent('file.skip', {'skipped': 1}))
                else:
                    result.downloaded = 1
                    emit(WorkerEvent('file.success', {'downloaded': 1}))
    except Exception as exc:
        result.error_code = _error_code(exc)
    finally:
        yt_globals.plugin_dirs.value = old_plugin_dirs
        logger.handlers = old_handlers
    return result
