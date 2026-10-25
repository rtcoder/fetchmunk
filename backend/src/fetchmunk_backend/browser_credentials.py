"""Explicit browser/file cookie import. Never called during discovery/startup."""
import contextlib
import io
import math
import sys
import time
from urllib.parse import urlsplit

class BrowserError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

DOMAINS = {'youtube': ('youtube.com',), 'cda': ('cda.pl',)}

def service_for_url(url):
    host = (urlsplit(url).hostname or '').lower()
    for service, domains in DOMAINS.items():
        if any(host == d or host.endswith('.' + d) for d in domains):
            return service
    return 'youtube' if host == 'youtu.be' else None

def allowed_domain(domain, service):
    return isinstance(domain,str) and any(domain.lstrip('.').lower() == d or domain.lstrip('.').lower().endswith('.'+d) for d in DOMAINS.get(service,()))

def scoped_cookies(cookies, service):
    if service not in DOMAINS:
        raise BrowserError('invalid_credentials')
    if not isinstance(cookies, list):
        raise BrowserError('invalid_cookies')
    result = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            raise BrowserError('invalid_cookies')
        if not allowed_domain(cookie.get('domain'), service):
            continue
        name, value = cookie.get('name'), cookie.get('value')
        path, secure = cookie.get('path', '/'), cookie.get('secure', False)
        expires = cookie.get('expires')
        domain_specified = cookie.get('domain_specified', cookie['domain'].startswith('.'))
        http_only = cookie.get('http_only', False)
        if (not isinstance(name, str) or not name or not isinstance(value, str)
                or not isinstance(path, str) or not path.startswith('/')
                or type(secure) is not bool or type(domain_specified) is not bool
                or type(http_only) is not bool):
            raise BrowserError('invalid_cookies')
        if any(ch in name + value + path + cookie['domain'] for ch in '\r\n\0'):
            raise BrowserError('invalid_cookies')
        if expires is not None and (
                type(expires) not in (int, float) or expires < 0 or expires > 1e16
                or not math.isfinite(expires)):
            raise BrowserError('invalid_cookies')
        if expires and expires < time.time():
            continue
        result.append(dict(
            name=name, value=value, domain=cookie['domain'], path=path,
            secure=secure, expires=expires or None,
            domain_specified=domain_specified, http_only=http_only,
        ))
    if not result:
        raise BrowserError('cookies_missing')
    return result

def parse_cookies(text, service):
    if not isinstance(text,str) or len(text.encode('utf-8')) > 524288: raise BrowserError('invalid_cookies')
    rows=[]
    try:
        for line in text.splitlines():
            http_only = line.startswith('#HttpOnly_')
            if http_only: line=line[len('#HttpOnly_'):]
            elif not line or line.startswith('#'): continue
            domain,subdomains,path,secure,expires,name,value=line.split('\t',6)
            if subdomains not in ('TRUE','FALSE') or secure not in ('TRUE','FALSE') or not path.startswith('/'): raise ValueError()
            rows.append(dict(domain=domain,path=path,secure=secure=='TRUE',expires=int(expires) or None,name=name,value=value,domain_specified=subdomains=='TRUE',http_only=http_only))
    except (ValueError,TypeError): raise BrowserError('invalid_cookies') from None
    return scoped_cookies(rows,service)

def browser_capabilities(platform=None):
    platform=platform or sys.platform
    names=['firefox','chrome','edge','brave'] + (['safari'] if platform=='darwin' else [])
    return [{'id':n,'status':'unsupported_encryption' if platform=='win32' and n!='firefox' else 'requires_consent'} for n in names]

class QuietLogger:
    def debug(self,*a,**k): pass
    def info(self,*a,**k): pass
    def warning(self,*a,**k): pass
    def error(self,*a,**k): pass

class BrowserConnector:
    """Platform-selected policies; decryption stays in upstream yt-dlp."""
    def capabilities(self): return browser_capabilities()
    def import_cookies(self,service,browser,profile=None):
        caps={x['id']:x['status'] for x in self.capabilities()}
        if browser not in caps: raise BrowserError('browser_unsupported')
        if caps[browser]=='unsupported_encryption': raise BrowserError('browser_encryption_unsupported')
        if profile is not None and (not isinstance(profile,str) or len(profile)>4096 or '\0' in profile): raise BrowserError('invalid_credentials')
        from yt_dlp.cookies import extract_cookies_from_browser
        try:
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                jar=extract_cookies_from_browser(browser,profile=profile or None,logger=QuietLogger())
            records=[dict(name=c.name,value=c.value,domain=c.domain,path=c.path,secure=c.secure,expires=c.expires,domain_specified=c.domain_specified,http_only=c.has_nonstandard_attr('HttpOnly')) for c in jar]
            return scoped_cookies(records,service)
        except BrowserError: raise
        except PermissionError: raise BrowserError('browser_permission_denied') from None
        except Exception: raise BrowserError('browser_import_failed') from None
