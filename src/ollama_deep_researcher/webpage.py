"""Project-owned public static-page reader, with explicit extraction limits."""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from bs4 import BeautifulSoup
from markdownify import markdownify


def validate_public_url(url: str) -> str:
    parsed = urlsplit(url)
    if (len(url) > 2048 or parsed.scheme != 'https' or not parsed.hostname
            or parsed.username or parsed.password or parsed.hostname.rstrip('.').lower() == 'localhost'):
        raise ValueError('Only public HTTPS source URLs without credentials are supported')
    host = parsed.hostname.rstrip('.')
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = [ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)]
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError('Non-public source destinations are not supported')
    return url


class PublicRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(request, timeout):
    return build_opener(PublicRedirects()).open(request, timeout=timeout)


def extract_html(html: str) -> dict:
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.get_text(' ', strip=True) if soup.title else ''
    for element in soup.select('script,style,noscript,nav,footer,aside,form,[role="navigation"],.sidebar,.cookie-banner,[hidden],[aria-hidden="true"]'):
        element.decompose()
    candidates = soup.select('article,main,div.body,[id*="content"],[class*="content"],[class*="article"]')
    def score(element):
        text = element.get_text(' ', strip=True)
        links = sum(len(link.get_text(' ', strip=True)) for link in element.find_all('a'))
        return len(text) - 2 * links
    viable = [node for node in candidates if node.get_text(strip=True)]
    body = max(viable, key=score) if viable else (soup.body or soup)
    # Avoid treating empty application shells as readable articles.
    content = markdownify(str(body), heading_style='ATX').strip() if body.get_text(strip=True) else ''
    return {'title': title, 'content': content, 'extraction': 'content-container' if viable else 'cleaned-page'}


def select_excerpt(content: str, query: str, max_chars: int) -> str:
    """Select original text windows with lexical overlap; not semantic retrieval."""
    if max_chars < 1:
        raise ValueError('Excerpt character limit must be positive')
    if len(content) <= max_chars:
        return content
    terms = set(re.findall(r'[a-zA-Z][a-zA-Z0-9_]{2,}', query.lower())) - {'the','and','for','with','does','what','how','this'}
    for run in re.findall(r'[\u4e00-\u9fff]+', query):
        terms.update(run[i:i+2] for i in range(len(run)-1))
    windows=[]
    for paragraph in re.split(r'\n\s*\n',content):
        for start in range(0,len(paragraph),900):
            piece=paragraph[start:start+900].strip()
            if piece: windows.append(piece)
    if not terms or not windows:
        return content[:max_chars]
    ranked=sorted(range(len(windows)), key=lambda i:(-sum(term in windows[i].lower() for term in terms),i))
    if not any(term in windows[ranked[0]].lower() for term in terms):
        return content[:max_chars]
    separator='\n\n[…]\n\n';selected={};remaining=max_chars
    for index in ranked:
        needed=len(windows[index])+(len(separator) if selected else 0)
        if needed<=remaining:
            selected[index]=windows[index];remaining-=needed
        elif not selected:
            selected[index]=windows[index][:remaining];break
    return separator.join(selected[index] for index in sorted(selected))


def read_webpage(url: str, query: str = '', max_chars: int = 4000, max_bytes: int = 1_000_000) -> dict:
    validate_public_url(url)
    request=Request(url,headers={'User-Agent':'LocalResearchAgent/0.2'})
    with open_url(request,timeout=20) as response:
        final_url=response.geturl()
        validate_public_url(final_url)
        content_type=(response.headers.get('Content-Type') or '').lower()
        if not any(kind in content_type for kind in ('text/html','application/xhtml+xml','text/plain')):
            raise ValueError('Unsupported source content type; use an HTML or plain-text page')
        data=response.read(max_bytes+1)
        if len(data)>max_bytes:
            raise ValueError('Source exceeds the download size limit')
        encoding=response.headers.get_content_charset() or 'utf-8'
        text=data.decode(encoding,errors='replace')
    result=extract_html(text) if 'html' in content_type else {'title':urlsplit(final_url).hostname,'content':text.strip(),'extraction':'plain-text'}
    full=result['content']
    if not full:
        return {'url':url,'final_url':final_url,'title':result['title'],'content':'','raw_content':'','truncated':False,'extraction':result['extraction']}
    excerpt=select_excerpt(full,query,max_chars)
    return {'url':url,'final_url':final_url,'title':result['title'] or urlsplit(final_url).hostname,
            'content':excerpt,'raw_content':excerpt,'truncated':len(full)>len(excerpt),
            'extracted_chars':len(full),'extraction':result['extraction']}
