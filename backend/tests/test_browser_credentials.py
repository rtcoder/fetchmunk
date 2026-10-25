import pytest
from fetchmunk_backend.browser_credentials import parse_cookies, service_for_url, BrowserError, browser_capabilities

def test_cookie_scope_and_http_only():
    raw="# Netscape HTTP Cookie File\n#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t2147483647\tSID\tsecret\n.evil.com\tTRUE\t/\tFALSE\t0\tother\tprivate\n"
    cookies=parse_cookies(raw,"youtube")
    assert len(cookies)==1 and cookies[0]["name"]=="SID"
    assert cookies[0]["domain"]==".youtube.com"

def test_scope_uses_host_boundary():
    assert service_for_url("https://www.youtube.com/watch?v=a")=="youtube"
    assert service_for_url("https://youtube.com.evil.test/") is None
    assert service_for_url("https://www.cda.pl/video/abc")=="cda"
    assert service_for_url("https://youtu.be/abc")=="youtube"

@pytest.mark.parametrize("raw",["garbage", "# Netscape HTTP Cookie File\n.evil.com\tTRUE\t/\tFALSE\t0\tx\ty", "x"*524289])
def test_rejects_invalid_or_unrelated_cookies(raw):
    with pytest.raises(BrowserError): parse_cookies(raw,"youtube")

def test_windows_chromium_is_not_advertised_as_importable():
    caps=browser_capabilities("win32")
    assert next(x for x in caps if x["id"]=="chrome")["status"]=="unsupported_encryption"


def test_netscape_cookie_domain_flags_survive_scope():
    raw='youtube.com\tFALSE\t/\tTRUE\t0\tHOST\tsecret\n.youtube.com\tTRUE\t/\tTRUE\t0\tDOMAIN\tsecret\n'
    cookies=parse_cookies(raw,'youtube')
    assert cookies[0]['domain_specified'] is False
    assert cookies[1]['domain_specified'] is True


def test_browser_cookie_domain_flags_survive_import(monkeypatch):
    from http.cookiejar import Cookie, CookieJar
    from fetchmunk_backend.browser_credentials import BrowserConnector
    import yt_dlp.cookies
    jar=CookieJar()
    jar.set_cookie(Cookie(0,'SID','secret',None,False,'youtube.com',False,False,'/',True,True,None,True,None,None,{'HttpOnly':None},False))
    monkeypatch.setattr(yt_dlp.cookies,'extract_cookies_from_browser',lambda *args,**kwargs:jar)
    cookies=BrowserConnector().import_cookies('youtube','firefox')
    assert cookies[0]['domain_specified'] is False
    assert cookies[0]['http_only'] is True


@pytest.mark.parametrize('changes', [
    {'path':None}, {'path':42}, {'path':'relative'}, {'expires':'123'},
    {'expires':True}, {'expires':float('nan')}, {'expires':float('inf')},
    {'expires':10**1000}, {'path':'/bad\npath'},
    {'secure':'TRUE'}, {'domain_specified':'FALSE'},
])
def test_scoped_cookie_rejects_malformed_metadata(changes):
    from fetchmunk_backend.browser_credentials import scoped_cookies
    cookie=dict(name='SID',value='secret',domain='youtube.com',path='/',secure=True,expires=None,domain_specified=False)
    cookie.update(changes)
    with pytest.raises(BrowserError) as error:
        scoped_cookies([cookie],'youtube')
    assert error.value.code=='invalid_cookies'
