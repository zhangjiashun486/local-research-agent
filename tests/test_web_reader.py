from email.message import Message
import pytest
from ollama_deep_researcher import webpage


def test_custom_article_container_is_found_and_boilerplate_removed():
    article='The actual article discusses Python type annotations. '*15
    html=f'<html><title>Example</title><body><nav>{"Menu login "*200}</nav><div class="post-content">{article}</div><footer>Copyright</footer><script>tracker()</script></body></html>'
    result=webpage.extract_html(html)
    assert article.strip() in result['content']
    assert 'Menu login' not in result['content'] and 'tracker' not in result['content']
    assert result['title']=='Example'


def test_topic_excerpt_finds_relevant_paragraph_after_long_unrelated_intro():
    body='\n\n'.join(['Travel hotels beaches '+str(i)+' x'*50 for i in range(30)])+'\n\nPython runtime does not enforce type annotations.\n\nMore details about annotations.'
    excerpt=webpage.select_excerpt(body,'Python runtime type annotations',500)
    assert len(excerpt)<=500
    assert 'Python runtime does not enforce type annotations.' in excerpt
    assert excerpt in body or all(part in body for part in excerpt.split('\n\n[…]\n\n'))


@pytest.mark.parametrize('html',['<body><script>renderArticle()</script><div id="root"></div></body>','<body><nav>Links only</nav></body>'])
def test_empty_or_js_only_pages_are_not_successful_documents(html):
    assert not webpage.extract_html(html)['content'].strip()


@pytest.mark.parametrize('url',['http://example.com','https://127.0.0.1/x','https://[::1]/x','https://localhost/x','https://user:secret@example.com/x','file:///secret'])
def test_unsafe_urls_rejected_before_request(url):
    with pytest.raises(ValueError): webpage.validate_public_url(url)


def test_dns_private_destination_rejected(monkeypatch):
    monkeypatch.setattr(webpage.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('192.168.1.2',443))])
    with pytest.raises(ValueError): webpage.validate_public_url('https://example.com/x')


def response(data, content_type='text/html; charset=utf-8'):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        headers=Message()
        def read(self,n):return data[:n]
        def geturl(self):return 'https://example.com/article'
    Response.headers['Content-Type']=content_type
    return Response()


def test_oversized_and_pdf_responses_fail_explicitly(monkeypatch):
    monkeypatch.setattr(webpage,'validate_public_url',lambda url:url)
    monkeypatch.setattr(webpage,'open_url',lambda *a,**k:response(b'x'*200))
    with pytest.raises(ValueError,match='size'):webpage.read_webpage('https://example.com/article',max_bytes=100)
    monkeypatch.setattr(webpage,'open_url',lambda *a,**k:response(b'%PDF data','application/pdf'))
    with pytest.raises(ValueError,match='content type'):webpage.read_webpage('https://example.com/article')


def test_plain_text_is_bounded_and_keeps_actual_url(monkeypatch):
    monkeypatch.setattr(webpage,'validate_public_url',lambda url:url)
    monkeypatch.setattr(webpage,'open_url',lambda *a,**k:response(b'Python annotation text. '*500,'text/plain'))
    result=webpage.read_webpage('https://example.com/article',max_chars=300)
    assert len(result['content'])<=300
    assert result['url']=='https://example.com/article'
    assert result['truncated'] is True


def test_redirect_to_local_network_is_rejected():
    from urllib.request import Request
    with pytest.raises(ValueError):
        webpage.PublicRedirects().redirect_request(Request('https://example.com'),None,302,'Found',{},'https://127.0.0.1/private')
