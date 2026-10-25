from types import SimpleNamespace
from pathlib import Path
import pytest


def request(tmp_path, url='https://www.youtube.com/watch?v=private-id', credentials=None):
    return SimpleNamespace(url=url, output_dir=tmp_path / 'files', archive_path=tmp_path / 'archive', credentials=credentials)


@pytest.fixture
def fake(monkeypatch):
    import yt_dlp
    state = SimpleNamespace(options=None, cookies=None, info={'id':'sensitive-id', 'title':'PRIVATE TITLE', 'formats':[{'format_id':'private', 'height':1080, 'width':1920, 'fps':30}]}, error=None)
    class Fake:
        def __init__(self, options):
            from http.cookiejar import CookieJar
            state.options = options
            self.cookiejar = CookieJar()
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download, process):
            state.cookies = list(self.cookiejar)
            assert download is False and process is False
            if state.error: raise state.error
            return state.info
        def process_ie_result(self, info, download):
            assert info is state.info and download is True
            state.processed = True
            return info
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', Fake)
    return state


def test_safe_options_and_quality_discovery(tmp_path, fake):
    from fetchmunk_backend.video_engine import run_video
    events=[]
    result=run_video(request(tmp_path), events.append)
    assert result.error_code is None and result.downloaded == 1
    assert fake.options['format'] == 'bestvideo+bestaudio/best'
    assert fake.options['cachedir'] is False
    assert fake.options['noplaylist'] is True
    assert fake.options['ignoreerrors'] is False
    assert Path(fake.options['ffmpeg_location']).is_absolute()
    assert Path(fake.options['js_runtimes']['deno']['path']).is_absolute()
    assert 'PRIVATE' not in repr(events) and 'private-id' not in repr(events)
    assert any(e.kind == 'video.formats' and e.data['formats'][0]['height']==1080 for e in events)


def test_credentials_injected_before_discovery(tmp_path, fake):
    from fetchmunk_backend.video_engine import run_video
    credentials={'kind':'cookies','cookies':[{'name':'SID','value':'secret','domain':'.youtube.com','path':'/','secure':True,'expires':None}]}
    assert run_video(request(tmp_path, credentials=credentials), lambda e:None).error_code is None
    assert fake.cookies[0].value == 'secret'
    assert 'cookiefile' not in fake.options


def test_password_only_cda(tmp_path, fake):
    from fetchmunk_backend.video_engine import run_video
    credentials={'kind':'password','username':'private','password':'secret'}
    assert run_video(request(tmp_path, credentials=credentials), lambda e:None).error_code == 'access_denied'
    assert fake.options is None
    assert run_video(request(tmp_path, 'https://www.cda.pl/video/123', credentials), lambda e:None).error_code is None
    assert fake.options['username']=='private' and fake.options['password']=='secret'
    assert fake.options['allowed_extractors'] == ['CDA']


def test_drm_rejected_before_download(tmp_path, fake):
    from fetchmunk_backend.video_engine import run_video
    fake.info['has_drm']=True
    assert run_video(request(tmp_path), lambda e:None).error_code == 'drm_protected'
    assert not hasattr(fake, 'processed')


def test_unknown_error_never_leaks_or_guesses_expiry(tmp_path, fake, capsys):
    from fetchmunk_backend.video_engine import run_video
    fake.error=RuntimeError('expired password secret https://signed-url')
    events=[]
    result=run_video(request(tmp_path), events.append)
    assert result.error_code == 'engine_error'
    assert 'secret' not in repr(events)
    assert capsys.readouterr() == ('','')


def test_real_local_download(tmp_path):
    from fetchmunk_backend.video_engine import run_video
    from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
    from threading import Thread
    from functools import partial
    import wave
    media=tmp_path/'source.wav'
    with wave.open(str(media),'wb') as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(8000); out.writeframes(b'\0\0'*800)
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(tmp_path)))
    thread=Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        events=[]
        result=run_video(request(tmp_path, f'http://127.0.0.1:{server.server_port}/source.wav'),events.append)
        assert result.error_code is None and result.downloaded == 1
        output=list((tmp_path/'files').glob('*.wav'))
        assert len(output)==1 and output[0].stem.isdecimal()
        assert output[0].read_bytes()==media.read_bytes()
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_typed_error_wrapped_by_ytdlp(tmp_path, fake):
    from fetchmunk_backend.video_engine import run_video
    from yt_dlp.utils import DownloadError, UnsupportedError
    cause=UnsupportedError('https://private-url')
    fake.error=DownloadError('private details', exc_info=(type(cause), cause, None))
    assert run_video(request(tmp_path), lambda e:None).error_code=='unsupported_url'


def test_real_selection_and_ffmpeg_merge(tmp_path, monkeypatch):
    import subprocess
    import imageio_ffmpeg
    import yt_dlp
    from fetchmunk_backend.video_engine import run_video
    from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
    from threading import Thread
    from functools import partial

    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=size=64x64:rate=5:duration=0.4','-an','-c:v','libx264',str(tmp_path/'video.mp4')],check=True,capture_output=True)
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','anullsrc=r=8000:cl=mono','-t','0.4','-c:a','aac',str(tmp_path/'audio.m4a')],check=True,capture_output=True)
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(tmp_path)))
    thread=Thread(target=server.serve_forever,daemon=True); thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    class ControlledMetadata(yt_dlp.YoutubeDL):
        def extract_info(self, url, download, process):
            assert download is False and process is False
            return {'id':'private','title':'PRIVATE TITLE', 'extractor':'fixture','webpage_url':base, 'formats':[
                {'format_id':'audio','url':base+'/audio.m4a','ext':'m4a','vcodec':'none','acodec':'aac','abr':64},
                {'format_id':'low','url':base+'/unused.mp4','ext':'mp4','vcodec':'h264','acodec':'aac','height':32},
                {'format_id':'best','url':base+'/video.mp4','ext':'mp4','vcodec':'h264','acodec':'none','height':64,'width':64},
            ]}
    monkeypatch.setattr(yt_dlp,'YoutubeDL',ControlledMetadata)
    req=request(tmp_path,base)
    req.output_dir=tmp_path/'literal-$HOME % żółć'
    try:
        events=[]
        result=run_video(req,events.append)
        assert result.error_code is None and result.downloaded==1
        outputs=list(req.output_dir.glob('*.mp4'))
        assert len(outputs)==1 and outputs[0].stem.isdecimal()
        metadata=subprocess.run([ffmpeg,'-i',str(outputs[0]),'-f','null','-'],capture_output=True,text=True)
        assert 'Video:' in metadata.stderr and 'Audio:' in metadata.stderr
        assert not list(req.output_dir.glob('*.m4a'))
        assert 'PRIVATE' not in repr(events)
        skipped=run_video(req,lambda e:None)
        assert skipped.error_code is None and skipped.skipped == 1 and skipped.downloaded == 0
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_ffmpeg_override_is_ignored(tmp_path, fake, monkeypatch):
    from fetchmunk_backend.video_engine import run_video
    import imageio_ffmpeg
    monkeypatch.setenv('IMAGEIO_FFMPEG_EXE', '/tmp/untrusted-ffmpeg')
    assert run_video(request(tmp_path), lambda e:None).error_code is None
    selected=Path(fake.options['ffmpeg_location'])
    assert selected.is_file()
    assert selected.is_relative_to(Path(imageio_ffmpeg.__file__).resolve().parent)


@pytest.mark.parametrize('domain,domain_specified,expected', [
    ('youtube.com',False,None), ('.youtube.com',True,'SID=secret'),
    ('youtube.com',True,'SID=secret'),
])
def test_cookie_scope_on_actual_outgoing_requests(domain,domain_specified,expected):
    from fetchmunk_backend.browser_credentials import parse_cookies
    from fetchmunk_backend.video_engine import _inject_cookies
    from http.cookiejar import CookieJar
    from urllib.request import Request
    flag='TRUE' if domain_specified else 'FALSE'
    cookies=parse_cookies(f'{domain}\t{flag}\t/\tTRUE\t0\tSID\tsecret','youtube')
    ydl=SimpleNamespace(cookiejar=CookieJar())
    _inject_cookies(ydl,{'kind':'cookies','cookies':cookies},'youtube.com')
    subdomain=Request('https://other.youtube.com/')
    ydl.cookiejar.add_cookie_header(subdomain)
    assert subdomain.get_header('Cookie')==expected
    original=Request('https://youtube.com/')
    ydl.cookiejar.add_cookie_header(original)
    assert original.get_header('Cookie')=='SID=secret'
