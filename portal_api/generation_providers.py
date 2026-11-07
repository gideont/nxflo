"""Server-only provider credentials and Databricks chat routing."""
import os
import re
from urllib.parse import urlsplit
from .generation_errors import GenerationError


def secret(name):return os.environ.get(name,'').strip().strip('\"\'')


def databricks_settings():
    base=secret('DATABRICKS_BASE_URL').rstrip('/');key=secret('DATABRICKS_AI_KEY');model=secret('DATABRICKS_MODEL')
    url=urlsplit(base)
    if not key or not model or url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise GenerationError('Configure DATABRICKS_AI_KEY, DATABRICKS_BASE_URL and DATABRICKS_MODEL in the server .env file.')
    if not re.fullmatch(r'[a-zA-Z0-9_./:-]{1,200}',model):raise GenerationError('The configured Databricks model name is invalid.')
    if base.endswith(('/chat/completions','/invocations')):endpoint=base
    elif url.path in ('','/'):endpoint=base+'/serving-endpoints/chat/completions'
    else:endpoint=base+'/chat/completions'
    return {'url':endpoint,'key':key,'model':model}


def providers():
    try:settings=databricks_settings();databricks={'configured':True,'model':settings['model']}
    except (GenerationError,ValueError):databricks={'configured':False,'model':secret('DATABRICKS_MODEL')}
    return {'openrouter':{'configured':bool(secret('OPENROUTER_API_KEY'))},'databricks':databricks}


def ensure_provider(config,Error):
    provider=config.get('provider','openrouter')
    if provider=='databricks':
        try:
            settings=databricks_settings()
            if config.get('databricks_model') and config['databricks_model']!=settings['model']:raise GenerationError('Choose the Databricks model configured on this server.')
        except (GenerationError,ValueError) as error:raise Error(str(error),503)
    elif not secret('OPENROUTER_API_KEY'):raise Error('The OpenRouter key is not configured on the server.',503)


def databricks_chat(config,body):
    settings=databricks_settings()
    if config.get('databricks_model') and config['databricks_model']!=settings['model']:raise GenerationError('Choose the Databricks model configured on this server.')
    payload={key:body[key] for key in ('messages','max_tokens') if key in body}
    payload.update(model=settings['model'],stream=False)
    # Claude Haiku 5.5 does not support Chat Completions response_format.
    # Prompts request JSON; the worker validates the returned objects before advancing.
    if 'haiku' in settings['model']:payload['thinking']={'type':'disabled'}
    return settings['url'],{'Authorization':'Bearer '+settings['key']},payload
