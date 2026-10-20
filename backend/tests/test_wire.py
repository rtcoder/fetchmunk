import importlib
import json
import pytest

def api():
    try: return importlib.import_module('fetchmunk_backend.wire')
    except ModuleNotFoundError: pytest.fail('wire transport missing')

def test_chunked_unicode_and_multiple_frames():
    w=api(); d=w.FrameDecoder()
    raw='{"protocol":1,"type":"request","x":"żółć\\n"}\n'.encode()
    out=[]
    for b in raw+raw: out+=d.feed(bytes([b]))
    assert len(out)==2 and out[0]['x']=='żółć\n'

def test_exact_limit_and_overflow():
    w=api(); prefix=b'{"protocol":1,"type":"request","x":"'; suffix=b'"}\n'
    raw=prefix+b'a'*(1048576-len(prefix)-len(suffix))+suffix
    assert len(w.FrameDecoder().feed(raw))==1
    with pytest.raises(w.ProtocolError): w.FrameDecoder().feed(raw[:-3]+b'a'+suffix)

@pytest.mark.parametrize('raw',[b'[]\n',b'bad\n',b'{"protocol":true,"type":"request"}\n',b'{"protocol":2,"type":"request"}\n',b'{"protocol":1}\n'])
def test_invalid_frames(raw):
    w=api()
    with pytest.raises(w.ProtocolError): w.FrameDecoder().feed(raw)

def test_eof_mid_frame():
    w=api(); d=w.FrameDecoder(); d.feed(b'{')
    with pytest.raises(w.ProtocolError): d.finish()

def test_encoder_rejects_nan():
    w=api()
    with pytest.raises(w.ProtocolError): w.encode_frame({'protocol':1,'type':'event','n':float('nan')})
