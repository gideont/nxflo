"""OpenRouter HTTP inside the disposable request process."""
import json
import requests
from .generation_errors import GenerationError,TransientGenerationError,RejectedGenerationError,RateLimitedGenerationError


def fetch_json(method,url,body,headers,provider='OpenRouter'):
    try:
        with requests.request(method,url,json=body,headers=headers,timeout=(15,120),stream=True,allow_redirects=False) as response:
            if not response.ok:
                error=RateLimitedGenerationError if response.status_code==429 else TransientGenerationError if response.status_code==408 or response.status_code>=500 else RejectedGenerationError if response.status_code in (400,401,402,403,404,405,413,415,422) else GenerationError
                raise error(provider+' returned HTTP '+str(response.status_code)+'. Check model availability, API key and credits.')
            data=bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                data.extend(chunk)
                if len(data)>16*1024*1024:raise GenerationError(provider+' response exceeds the 16 MB limit.')
            try:return json.loads(data)
            except (ValueError,UnicodeError):raise GenerationError(provider+' returned an unreadable response.')
    except requests.RequestException:raise TransientGenerationError(provider+' connection failed or stopped responding.')
