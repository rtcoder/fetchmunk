from fetchmunk_backend.sources import normalize_source_url

def test_no_heuristic_stripping_or_host_substring_matching():
    for url in ['https://pl.example.com/a?x=1','https://youtube.com.evil.test/a']:
        assert normalize_source_url(url)==url

def test_explicit_alias_preserves_path_query_fragment():
    url='https://pl.example.com/a%2Fb?token=abc#part'
    assert normalize_source_url(url,{'pl.example.com':'example.com'})=='https://example.com/a%2Fb?token=abc#part'
    assert normalize_source_url('https://pl.example.com.evil.test/a',{'pl.example.com':'example.com'})=='https://pl.example.com.evil.test/a'
