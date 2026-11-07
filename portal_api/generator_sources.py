"""Extract reference links from intake text without fetching any remote content."""
from html import unescape
import re
from urllib.parse import urlsplit, urlunsplit, parse_qs

LINKS=re.compile(r'https?://[^\s<>"\'`]+|\b(?:www\.|youtube\.com/|youtu\.be/)[^\s<>"\'`]+|\b10\.\d{4,9}/[^\s<>"\'`]+',re.I)
VIDEO=re.compile(r'^[A-Za-z0-9_-]{11}$')


def clean_link(raw):
    value=unescape(raw).rstrip('.,;:!?，。；：！？*')
    for left,right in (('(',')'),('[',']'),('{','}')):
        extra=value.count(right)-value.count(left)
        if extra>0:
            trailing=len(value)-len(value.rstrip(right))
            if trailing: value=value[:-min(extra,trailing)]
    if value.lower().startswith(('www.','youtube.com/','youtu.be/')): value='https://'+value
    elif re.match(r'^10\.\d{4,9}/',value): value='https://doi.org/'+value
    try:
        parts=urlsplit(value)
        if parts.scheme.lower() not in ('http','https') or not parts.hostname or parts.username or parts.password: return None
        host=parts.hostname.lower(); port=parts.port
        netloc=('['+host+']' if ':' in host else host)+(':'+str(port) if port else '')
        value=urlunsplit((parts.scheme.lower(),netloc,parts.path or '/',parts.query,parts.fragment))
        video=None
        if host in ('youtu.be','www.youtu.be'): video=parts.path.strip('/').split('/')[0]
        elif host in ('youtube.com','www.youtube.com','m.youtube.com','music.youtube.com','youtube-nocookie.com','www.youtube-nocookie.com'):
            path=parts.path.strip('/').split('/')
            if path[0]=='watch': video=parse_qs(parts.query).get('v',[''])[0]
            elif len(path)>1 and path[0] in ('shorts','live','embed'): video=path[1]
        if video and VIDEO.fullmatch(video): return 'youtube','https://www.youtube.com/watch?v='+video
        return 'references',value
    except (ValueError,IndexError): return None


def extract_sources(topic,manual_youtube=''):
    sources={'youtube':[],'references':[]}; seen=set()
    for text in (topic,manual_youtube):
        for match in LINKS.finditer(text):
            result=clean_link(match.group())
            if result and result[1] not in seen:
                seen.add(result[1]);sources[result[0]].append(result[1])
    return sources
