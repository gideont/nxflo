"""Approved public-source extraction: validated DNS, pinned sockets, bounded reads."""
import http.client
import ipaddress
import io
import re
import socket
import ssl
from urllib.parse import urlsplit,urljoin,parse_qs
from .generation_models import GenerationError


def public_addresses(host):
    try:addresses=list(dict.fromkeys(info[4][0] for info in socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)))
    except OSError:raise GenerationError('Reference hostname could not be resolved.')
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):raise GenerationError('Only public Internet reference addresses are allowed.')
    return addresses


def fetch_reference(url):
    for _ in range(5):
        try:
            parts=urlsplit(url);port=parts.port or (443 if parts.scheme=='https' else 80)
        except ValueError:raise GenerationError('Invalid reference URL.')
        if parts.scheme not in ('https','http') or not parts.hostname or parts.username or parts.password:raise GenerationError('Unsupported reference URL.')
        if port not in (80,443):raise GenerationError('References must use standard HTTP/HTTPS ports.')
        address=public_addresses(parts.hostname)[0]
        conn=http.client.HTTPSConnection(parts.hostname,port,timeout=20) if parts.scheme=='https' else http.client.HTTPConnection(parts.hostname,port,timeout=20)
        try:
            sock=socket.create_connection((address,port),timeout=20)
            conn.sock=ssl.create_default_context().wrap_socket(sock,server_hostname=parts.hostname) if parts.scheme=='https' else sock
            path=parts.path or '/'
            if parts.query:path+='?'+parts.query
            conn.request('GET',path,headers={'User-Agent':'NexusflowResearch/1.0','Accept-Encoding':'identity'})
            response=conn.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location:raise GenerationError('Reference redirect has no destination.')
                url=urljoin(url,location);continue
            if response.status!=200:raise GenerationError('Reference returned HTTP '+str(response.status)+'.')
            if response.getheader('Content-Encoding','identity').lower() not in ('identity',''):raise GenerationError('Compressed reference responses are not supported.')
            raw=response.read(8*1024*1024+1)
            if len(raw)>8*1024*1024:raise GenerationError('Reference exceeds 8 MB.')
            content_type=response.getheader('Content-Type','').lower()
            if 'pdf' in content_type or raw.startswith(b'%PDF'):
                from pypdf import PdfReader
                reader=PdfReader(io.BytesIO(raw))
                if len(reader.pages)>150:raise GenerationError('PDF exceeds 150 pages.')
                text='\n'.join(page.extract_text() or '' for page in reader.pages)
            else:
                if content_type and not any(kind in content_type for kind in ('text/','html','json','xml')):raise GenerationError('Reference is not text, HTML or PDF.')
                text=raw.decode('utf-8',errors='replace')
                if 'html' in content_type or '<html' in text[:1000].lower():
                    from bs4 import BeautifulSoup
                    soup=BeautifulSoup(text,'html.parser')
                    for node in soup(['script','style','nav','header','footer','form','noscript']):node.decompose()
                    text=soup.get_text('\n',strip=True)
            if not text.strip():raise GenerationError('Reference contains no extractable text.')
            if len(text)>300000:raise GenerationError('Reference exceeds 300,000 text characters; upload excerpts instead.')
            return text,url
        except GenerationError:raise
        except Exception:raise GenerationError('Reference could not be downloaded or extracted.')
        finally:conn.close()
    raise GenerationError('Reference has too many redirects.')


def transcript(url):
    from youtube_transcript_api import YouTubeTranscriptApi
    import requests
    class TimedSession(requests.Session):
        def request(self,*args,**kwargs):kwargs.setdefault('timeout',20);return super().request(*args,**kwargs)
    video=parse_qs(urlsplit(url).query).get('v',[''])[0]
    if not re.fullmatch(r'[\w-]{11}',video):raise GenerationError('Invalid YouTube video ID.')
    try:
        text=' '.join(item.text for item in YouTubeTranscriptApi(http_client=TimedSession()).fetch(video))
        if len(text)>300000:raise GenerationError('Transcript exceeds 300,000 characters; upload excerpts instead.')
        return text
    except GenerationError:raise
    except Exception:raise GenerationError('YouTube captions unavailable. Upload a transcript to include its content.')
