"""Owner-only document settings, durable generation jobs, and private downloads."""
import base64
from datetime import date
import io
import math
import json
import os
from pathlib import Path
import re
import uuid
import time
from flask import jsonify, request, send_file
from . import db
from urllib.parse import urlsplit
from .generator_revisions import prepare_revision, history_entry

TOPIC_LIMIT = 2_000_000

BASE = '/bms_integration_hub/api/admin/generator'
DEFAULTS = dict(provider='openrouter',databricks_model='',company='Nexusflow Inc.', website='https://www.nxflo.com', prepared_team='research',
    teams=[{'id':'research','name':'Research Team at Nexusflow Inc.','email':'research@nxflo.com'}],
    feedback='', change_summary='', revision_parent='', title='', topic='', report_type='Research report', document_intent='content_preserving_rewrite', logo='', pages=12,
    length_mode='content', toc=True, charts=True, images=True, graphics=True, color='#315e55', accent='#b97a44',
    credits='Nexusflow', release_date='', version='1.0', version_override=False, questions='', youtube='', web_search=True, web_budget_usd=0.30,
    summary_model='openai/gpt-6-luna', draft_model='openai/gpt-6-luna',
    polish_model='openai/gpt-6-luna', summary_service='flex', draft_service='flex', polish_service='flex', advanced_models=False, review_passes=3, cost_pages=12, documents=[], illustrations=[])


def validate(data, Error):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise Error('Invalid generator settings')
    result = {**DEFAULTS, **data}
    from .generation_intent import MODES
    if not isinstance(result['document_intent'],str) or result['document_intent'] not in MODES:raise Error('Choose a valid document intent')
    if result['provider'] not in ('openrouter','databricks'):raise Error('Choose Databricks or OpenRouter')
    if not isinstance(result['databricks_model'],str) or len(result['databricks_model'])>200 or result['databricks_model'] and not re.fullmatch(r'[a-zA-Z0-9_./:-]{1,200}',result['databricks_model']):raise Error('Invalid Databricks model')
    for key in ('company', 'title', 'topic', 'report_type', 'credits', 'version', 'questions', 'youtube', 'release_date', 'length_mode', 'summary_model', 'draft_model', 'polish_model', 'color', 'accent', 'website', 'prepared_team', 'feedback', 'change_summary', 'revision_parent'):
        if not isinstance(result[key], str) or len(result[key]) > (TOPIC_LIMIT if key=='topic' else 12000 if key in ('questions','feedback') else 1000 if key in ('website','change_summary') else 4000 if key=='youtube' else 200):
            if key=='topic' and isinstance(result[key],str): raise Error('Topic & brief exceeds 2,000,000 characters. Shorten it before saving; the browser retains your full pasted text.')
            raise Error('Invalid ' + key.replace('_', ' '))
        if key!='topic': result[key] = result[key].strip()
    if result['website']:
        try:
            website=urlsplit(result['website'])
            if website.scheme not in ('http','https') or not website.hostname or website.username or website.password or any(ch.isspace() for ch in result['website']):raise ValueError()
            website.port
        except ValueError:raise Error('Enter a valid HTTP or HTTPS company website')
    if not isinstance(result['teams'],list) or len(result['teams'])>20:raise Error('Save at most 20 team contacts')
    teams=[];ids=set()
    for team in result['teams']:
        if not isinstance(team,dict) or set(team)!={'id','name','email'} or any(not isinstance(team[key],str) for key in team):raise Error('Invalid team contact')
        item={key:value.strip() for key,value in team.items()}
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',item['id']) or item['id'] in ids or not item['name'] or len(item['name'])>200:raise Error('Each team needs a unique ID and a name of up to 200 characters')
        if item['id']=='research' and not item['email']:item['email']='research@nxflo.com'
        if not item['email']:raise Error('Each saved team needs a contact email address')
        if item['email'] and (len(item['email'])>254 or not re.fullmatch(r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?\.[a-zA-Z]{2,63}",item['email'])):raise Error('Enter a valid team email address')
        ids.add(item['id']);teams.append(item)
    result['teams']=teams
    if result['prepared_team'] and result['prepared_team'] not in ids:raise Error('Choose a saved team or omit the prepared-by team')
    if result['revision_parent'] and not re.fullmatch(r'[a-f0-9]{32}',result['revision_parent']):raise Error('Invalid original document ID')
    for key in ('summary_model','draft_model','polish_model'):
        if result[key]=='': result[key]=DEFAULTS[key]
        if result[key].endswith(':batch'):raise Error('Batch models have been removed. Choose a synchronous model or Databricks.')
    if type(result['web_budget_usd']) not in (int,float) or not math.isfinite(result['web_budget_usd']) or not 0<=result['web_budget_usd']<=0.30:raise Error('Web research limit must be between US$0 and US$0.30')
    if type(result['advanced_models']) is not bool: raise Error('Invalid advanced model setting')
    if not result['advanced_models']:
        for role in ('draft','polish'):
            result[role+'_model']=result['summary_model']
            result[role+'_service']=result['summary_service']
    for key in ('summary_service','draft_service','polish_service'):
        if result[key] not in ('default','flex'): raise Error('Invalid processing mode')
        if result[key]=='flex' and result[key.replace('_service','_model')]!='openai/gpt-6-luna': raise Error('Flex is available for GPT-6 Luna; select default processing for other models')
    for key in ('toc', 'charts', 'images', 'graphics', 'web_search', 'version_override'):
        if type(result[key]) is not bool: raise Error('Invalid option')
    if type(result['pages']) is not int or not 1 <= result['pages'] <= 60: raise Error('Choose 1–60 target pages')
    if type(result['review_passes']) is not int or result['review_passes'] not in (1,2,3,4): raise Error('Choose 1–4 review passes')
    if type(result['cost_pages']) is not int or not 1 <= result['cost_pages'] <= 60: raise Error('Choose 1–60 planning pages')
    if result['length_mode'] not in ('content','target'): raise Error('Invalid length mode')
    for key in ('color','accent'):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', result[key]): raise Error('Use a hex theme color')
    for key in ('summary_model','draft_model','polish_model'):
        if not result[key]: result[key]=DEFAULTS[key]
        if not re.fullmatch(r'[a-zA-Z0-9_./:-]{3,160}', result[key]): raise Error('Enter a valid OpenRouter model ID')
    if result['release_date']:
        try: date.fromisoformat(result['release_date'])
        except ValueError: raise Error('Invalid release date')
    for url in result['youtube'].splitlines():
        if url and not re.fullmatch(r'https://(?:www\.)?(?:youtube\.com/watch\?v=[\w-]{11}(?:&[^\s]*)?|youtu\.be/[\w-]{11}(?:\?[^\s]*)?)',url):
            raise Error('Use YouTube watch or youtu.be links, one per line')
    if len(result['youtube'].splitlines()) > 10: raise Error('Use at most 10 YouTube links')
    def image(value):
        if not isinstance(value,str) or len(value)>2800000: raise Error('Image too large (2 MB maximum)')
        if not value: return ''
        if not re.fullmatch(r'data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+',value): raise Error('Use a PNG, JPEG or WebP image')
        try:
            from PIL import Image
            with Image.open(io.BytesIO(base64.b64decode(value.split(',',1)[1],validate=True))) as im:
                if im.width*im.height>16000000: raise ValueError()
                im.thumbnail((1400,1400)); output=io.BytesIO(); pixels=im.convert('RGBA'); pixels.save(output,format='PNG')
                mime='png'
                if len(output.getvalue())>2*1024*1024:
                    output=io.BytesIO(); pixels.save(output,format='WEBP',quality=88); mime='webp'
            return 'data:image/'+mime+';base64,'+base64.b64encode(output.getvalue()).decode()
        except Exception: raise Error('Image could not be read')
    result['logo']=image(result['logo'])
    if not isinstance(result['illustrations'],list) or len(result['illustrations'])>4: raise Error('Use at most four illustrations')
    result['illustrations']=[image(i) for i in result['illustrations']]
    if not isinstance(result['documents'],list) or len(result['documents'])>10: raise Error('Use at most ten documents')
    for doc in result['documents']:
        if not isinstance(doc,dict) or set(doc) not in ({'name','text'},{'name','text','role'}) or doc.get('role','author') not in ('author','reference') or not isinstance(doc['name'],str) or len(doc['name'])>200 or not isinstance(doc['text'],str) or len(doc['text'])>80000:
            raise Error('Invalid extracted document')
    if sum(len(d['text']) for d in result['documents'])>240000: raise Error('Combined document text exceeds 240,000 characters')
    if result['provider']=='databricks':result['web_search']=False
    return result


def register_generator(app, conn, login_required, Error):
    with app.app_context():
        conn().executescript('''CREATE TABLE IF NOT EXISTS generator_settings (id INTEGER PRIMARY KEY CHECK(id=1), config TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS generator_jobs (id TEXT PRIMARY KEY, config TEXT NOT NULL, status TEXT NOT NULL,
        step TEXT NOT NULL, state TEXT NOT NULL DEFAULT '{}', events TEXT NOT NULL DEFAULT '[]', error TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, published_at TEXT, previewed_at TEXT, parent_id TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS generator_single_active ON generator_jobs((1)) WHERE status IN ('queued','running');
        CREATE TABLE IF NOT EXISTS generator_calls(job_id TEXT NOT NULL,call_key TEXT NOT NULL,status TEXT NOT NULL,stage TEXT NOT NULL,remote_id TEXT,result TEXT,cost REAL NOT NULL DEFAULT 0,PRIMARY KEY(job_id,call_key));
        CREATE TABLE IF NOT EXISTS generator_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);''')
        call_columns={row['name'] for row in conn().execute('PRAGMA table_info(generator_calls)')}
        for name,definition in (('cost_known','INTEGER NOT NULL DEFAULT 0'),('billing',"TEXT NOT NULL DEFAULT '{}'"),('reserved_cost','REAL NOT NULL DEFAULT 0'),('budget_scope',"TEXT NOT NULL DEFAULT ''")):
            if name not in call_columns:conn().execute('ALTER TABLE generator_calls ADD COLUMN '+name+' '+definition)
        columns={row['name'] for row in conn().execute('PRAGMA table_info(generator_jobs)')}
        for name,definition in (('next_run_at','REAL NOT NULL DEFAULT 0'),('message',"TEXT NOT NULL DEFAULT ''"),('wait_state',"TEXT NOT NULL DEFAULT '{}'"),('recovery',"TEXT NOT NULL DEFAULT '{}'"),('work_progress',"TEXT NOT NULL DEFAULT '{}'")):
            if name not in columns: conn().execute('ALTER TABLE generator_jobs ADD COLUMN '+name+' '+definition)

        from .generator_library import migrate
        migrate(conn())

    def job_or_404(job_id):
        row=conn().execute('SELECT * FROM generator_jobs WHERE id=?',(job_id,)).fetchone()
        if row is None: raise Error('Document not found',404)
        return row

    def worker_online():
        row=conn().execute("SELECT value FROM generator_meta WHERE key='heartbeat'").fetchone()
        return bool(row and time.time()-float(row['value'])<180)

    @app.get(BASE)
    @login_required(owner=True)
    def settings():
        from .generation_recovery import recovery_info
        from .generation_providers import providers
        from .generator_library import library
        row=conn().execute('SELECT * FROM generator_settings WHERE id=1').fetchone()
        jobs=conn().execute('SELECT id,status,step,created_at,published_at,error,config,parent_id,next_run_at,recovery FROM generator_jobs ORDER BY created_at DESC LIMIT 50').fetchall()
        saved={**DEFAULTS,**{'summary_service':'default','draft_service':'default','polish_service':'default'},**json.loads(row['config'])} if row else dict(DEFAULTS)
        if not saved['company'] or saved['company']=='Nexusflow':saved['company']='Nexusflow Inc.'
        for role in ('summary','draft','polish'):saved[role+'_model']=saved[role+'_model'].removesuffix(':batch')
        return jsonify(config=saved, revision=row['revision'] if row else 0,
            documents=library(conn()), defaults=DEFAULTS,providers=providers(), worker_online=worker_online(), configured=bool(os.environ.get('OPENROUTER_API_KEY','').strip()), jobs=[dict(id=j['id'],status=j['status'],step=j['step'],created_at=j['created_at'],published_at=j['published_at'],error=j['error'],title=json.loads(j['config'])['title'],version=json.loads(j['config'])['version'],parent_id=j['parent_id'],can_resume=recovery_info(conn(),j)['can_resume'] if j['status'] in ('failed','cancelled') else False) for j in jobs])

    @app.get(BASE+'/pricing')
    @login_required(owner=True)
    def model_pricing():
        from .generator_pricing import read_prices
        prices=read_prices(request.args.get('refresh')=='1')
        prices['models']={key:value for key,value in prices['models'].items() if not key.endswith(':batch')}
        return jsonify(prices)

    @app.put(BASE)
    @login_required(owner=True)
    def save():
        body=request.get_json(silent=True)
        if not isinstance(body,dict): raise Error('Invalid request')
        config=validate(body.get('config'),Error)
        with db.transaction(conn()):
            row=conn().execute('SELECT revision FROM generator_settings WHERE id=1').fetchone()
            revision=row['revision'] if row else 0
            if body.get('revision')!=revision: raise Error('Settings changed in another tab. Reload before saving.',409)
            conn().execute('INSERT INTO generator_settings VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config,revision=excluded.revision',(json.dumps(config,ensure_ascii=False),revision+1))
        return jsonify(revision=revision+1)

    @app.post(BASE+'/extract')
    @login_required(owner=True)
    def extract():
        file=request.files.get('file')
        if not file: raise Error('Choose a document')
        raw=file.read(8*1024*1024+1)
        if len(raw)>8*1024*1024: raise Error('Document must be under 8 MB')
        name=(file.filename or '')[:200]
        try:
            suffix=Path(name).suffix.lower()
            if suffix=='.pdf':
                from pypdf import PdfReader
                reader=PdfReader(io.BytesIO(raw))
                if len(reader.pages)>150: raise Error('PDF exceeds 150 pages')
                text='\n'.join((p.extract_text() or '') for p in reader.pages)
            elif suffix=='.docx':
                from docx import Document
                import zipfile
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    if sum(i.file_size for i in archive.infolist())>30*1024*1024: raise Error('Expanded document is too large')
                document=Document(io.BytesIO(raw))
                text='\n'.join([p.text for p in document.paragraphs]+[' | '.join(c.text for c in r.cells) for t in document.tables for r in t.rows])
            elif suffix in ('.txt','.md','.csv'): text=raw.decode('utf-8-sig')
            else: raise Error('Supported files: PDF, DOCX, TXT, Markdown and CSV')
        except Error: raise
        except Exception: raise Error('Document could not be extracted. Scanned PDFs need OCR first.')
        if not text.strip(): raise Error('No readable text found. Scanned PDFs need OCR first.')
        if len(text)>80000: raise Error('Document text exceeds 80,000 characters. Split it into smaller sources.')
        return jsonify(name=name,text=text)

    @app.post(BASE+'/autofill')
    @login_required(owner=True)
    def fill_metadata():
        body=request.get_json(silent=True)
        if not isinstance(body,dict): raise Error('Invalid request')
        config=validate(body.get('config'),Error)
        if not config['topic'].strip(): raise Error('Add a topic or brief so AI knows what the document is about')
        from .generator_autofill import autofill
        from .generation_providers import secret
        return jsonify(updates=autofill(config,Error),provider=config['provider'],model=secret('DATABRICKS_MODEL') if config['provider']=='databricks' else 'openai/gpt-6-luna',service_tier='default' if config['provider']=='databricks' else 'flex')

    @app.post(BASE+'/jobs')
    @login_required(owner=True)
    def start():
        body=request.get_json(silent=True)
        if not isinstance(body,dict): raise Error('Invalid request')
        config=validate(body.get('config'),Error)
        if not config['topic'].strip(): raise Error('Add a topic or brief before generating')
        from .generation_providers import ensure_provider,secret
        ensure_provider(config,Error)
        if config['provider']=='databricks':config['databricks_model']=secret('DATABRICKS_MODEL')
        if body.get('parent_id') is not None and not isinstance(body['parent_id'],str):raise Error('Invalid parent version')
        parent=body.get('parent_id') or config['revision_parent'] or None
        if body.get('parent_id') and config['revision_parent'] and body['parent_id']!=config['revision_parent']:raise Error('Conflicting original document selections')
        if parent is not None:
            if not isinstance(parent,str) or len(parent)>64: raise Error('Invalid parent version')
            job_or_404(parent)
        job_id=uuid.uuid4().hex;created_at=db.now()
        with db.transaction(conn()):
            if conn().execute("SELECT 1 FROM generator_jobs WHERE status IN ('queued','running')").fetchone(): raise Error('A document is already generating. Wait for it to finish.',409)
            from .generator_library import backfill
            backfill(conn())
            history=prepare_revision(conn(),parent,config,Error) if parent else []
            if not parent and not config['version_override']:config['version']='1.0'
            if config['version_override'] and not config['version']:raise Error('Enter a version or turn off the version override')
            if not config['version']:config['version']='1.0'
            summary=config['change_summary'] or ('Revised following editorial review and feedback.' if parent else 'Initial issue.')
            history.append(history_entry(config,created_at,summary))
            from .generation_intent import digest,author_material
            pipeline_version=app.config.get('GENERATOR_PIPELINE_VERSION',2)
            initial={'revision_history':history,'pipeline_version':pipeline_version}
            if pipeline_version==2:
                original=author_material(config)
                initial.update(prompt_policy_version=2,original_brief=config['topic'],author_original=original,author_source_hash=digest(original))
            state=json.dumps(initial,ensure_ascii=False)
            conn().execute('INSERT INTO generator_jobs(id,config,status,step,state,created_at,updated_at,parent_id,message) VALUES(?,?,?,?,?,?,?,?,?)',(job_id,json.dumps(config,ensure_ascii=False),'queued','collect',state,created_at,created_at,parent,'Queued for document generation.'))
            from .generator_library import attach_new
            document_id,version_id=attach_new(conn(),job_id,config,created_at,parent)
        return jsonify(id=job_id,version=config['version'],document_id=document_id,version_id=version_id),202

    @app.get(BASE+'/jobs/<job_id>')
    @login_required(owner=True)
    def job(job_id):
        from .generation_recovery import recovery_info
        row=job_or_404(job_id)
        state=json.loads(row['state']);sources=state.get('sources')
        waiting=json.loads(row['wait_state'])
        if waiting:
            waiting['elapsed_seconds']=max(0,int(time.time()-waiting['started_at']))
            waiting['remaining_seconds']=max(0,int(waiting['deadline_at']-time.time()))
        pending=conn().execute("SELECT stage,remote_id,result FROM generator_calls WHERE job_id=? AND status='submitted' AND remote_id IS NOT NULL LIMIT 1",(job_id,)).fetchone()
        batch={**(json.loads(pending['result']) if pending['result'] else {}),'stage':pending['stage'],'id':pending['remote_id'],'next_check_at':row['next_run_at']} if pending else None
        calls=conn().execute('SELECT stage,status,cost,cost_known,billing,reserved_cost,budget_scope FROM generator_calls WHERE job_id=?',(job_id,)).fetchall()
        breakdown=[{'stage':item['stage'],'status':item['status'],'total':item['cost'] if item['cost_known'] else None,**json.loads(item['billing'])} for item in calls]
        web=[item for item in calls if item['budget_scope']=='web' or item['stage'].startswith('web-research:')]
        web_cost=sum(item['cost'] for item in web if item['cost_known']);legacy=any(item['status']=='complete' and not json.loads(item['billing']).get('web_policy') for item in web)
        web_budget={'limit':json.loads(row['config']).get('web_budget_usd',0.30),'reported':web_cost,'reserved':sum(item['reserved_cost'] for item in web if not item['cost_known']),'historical':legacy}
        metrics={'source_characters':sum(len(source.get('text','')) for source in sources),'summary_chunks':sum((len(source.get('text',''))+23999)//24000 for source in sources),'web_cost':web_cost,'web_cost_known':bool(web) and all(item['status']=='complete' and item['cost_known'] for item in web)} if sources else None
        chapter_count=len(state.get('document',{}).get('chapters') or state.get('outline',{}).get('chapters') or [])
        return jsonify(chapter_count=chapter_count or None,pipeline_version=state.get('pipeline_version',1),document_intent=json.loads(row['config']).get('document_intent','research_report'),publication_quality=state.get('publication_quality'),intent_audits=state.get('intent_audits',[]),quality_errors=state.get('quality_errors',[]),step_progress=json.loads(row['work_progress']),recovery=recovery_info(conn(),row),server_time=time.time(),wait_state=waiting,batch_wait=batch,billing=breakdown,web_budget=web_budget,source_metrics=metrics,**{k:row[k] for k in ('id','status','step','error','created_at','published_at','parent_id','message','updated_at','document_id','version_id')},config={**DEFAULTS,**{'summary_service':'default','draft_service':'default','polish_service':'default'},**json.loads(row['config'])},events=json.loads(row['events']),worker_online=worker_online(),warnings=json.loads(row['state']).get('warnings',[]),cost=conn().execute('SELECT sum(cost) FROM generator_calls WHERE job_id=? AND cost_known=1',(job_id,)).fetchone()[0],unreported_calls=conn().execute("SELECT count(*) FROM generator_calls WHERE job_id=? AND status='complete' AND cost_known=0",(job_id,)).fetchone()[0])

    @app.post(BASE+'/jobs/<job_id>/resume')
    @login_required(owner=True)
    def resume(job_id):
        from .generation_recovery import recovery_info
        with db.transaction(conn()):
            row=job_or_404(job_id)
            if row['status']=='running':return jsonify(id=job_id,status='running'),202
            if row['status'] not in ('failed','cancelled','queued'):raise Error('This document cannot be resumed',409)
            info=recovery_info(conn(),row)
            if info['blocked_reason']:raise Error(info['blocked_reason'],409)
            from .generation_providers import ensure_provider
            ensure_provider({**DEFAULTS,**json.loads(row['config'])},Error)
            if conn().execute("SELECT 1 FROM generator_jobs WHERE status IN ('queued','running') AND id!=?",(job_id,)).fetchone():raise Error('Another document is generating. Wait for it to finish before resuming this one.',409)
            # Preserve the job, version, immutable configuration, checkpoint and paid responses.
            # Checking an active batch is idempotent and does not reset retry backoff.
            if row['status']=='queued' and info.get('retry_at'):return jsonify(id=job_id,status='queued'),202
            conn().execute("UPDATE generator_jobs SET status='queued',error='',message=?,next_run_at=0,recovery='{}',wait_state='{}',updated_at=? WHERE id=?",('Resuming from saved progress. Existing provider requests and completed responses will be reused.',db.now(),job_id))
        return jsonify(id=job_id,status='queued'),202

    @app.post(BASE+'/jobs/<job_id>/approve-html')
    @login_required(owner=True)
    def approve_html(job_id):
        with db.transaction(conn()):
            row=job_or_404(job_id)
            if row['status'] != 'awaiting_html_review':raise Error('This document is not waiting for HTML review',409)
            if conn().execute("SELECT 1 FROM generator_jobs WHERE status IN ('queued','running') AND id!=?",(job_id,)).fetchone():raise Error('Another document is generating. Wait for it to finish before continuing this version.',409)
            path=Path(app.config['DATABASE']).parent/'generated'/row['id']/'document.html'
            if not path.is_file():raise Error('HTML preview file is missing',409)
            if conn().execute("SELECT 1 FROM generator_jobs WHERE status IN ('queued','running') AND id!=?",(job_id,)).fetchone():raise Error('Another document is generating. Wait for it to finish before continuing.',409)
            state=json.loads(row['state'])
            if state.get('pipeline_version')==2:
                from .generation_quality import assert_publication
                from .generation_errors import GenerationError
                try:assert_publication(state,path.read_text())
                except GenerationError as error:raise Error(str(error),409)
            state['html_approved']=True
            conn().execute("UPDATE generator_jobs SET status='queued',state=?,error='',message=?,next_run_at=0,recovery='{}',wait_state='{}',updated_at=? WHERE id=?",(json.dumps(state,ensure_ascii=False),'HTML approved. Continuing to PDF export.',db.now(),job_id))
        return jsonify(id=job_id,status='queued'),202

    @app.post(BASE+'/jobs/<job_id>/cancel')
    @login_required(owner=True)
    def cancel(job_id):
        with db.transaction(conn()):
            row=job_or_404(job_id)
            if row['status'] not in ('queued','running'): raise Error('This job is not active',409)
            conn().execute("UPDATE generator_jobs SET status='cancelled',message=?,updated_at=? WHERE id=?",('Cancelled. Requests already submitted to a provider may still complete and be charged.',db.now(),job_id))
        return jsonify(ok=True)

    @app.get(BASE+'/jobs/<job_id>/download/<kind>')
    @login_required(owner=True)
    def download(job_id,kind):
        row=job_or_404(job_id)
        if (row['status'] not in ('ready','needs_review') and not (row['status']=='awaiting_html_review' and kind=='html')) or kind not in ('pdf','html'): raise Error('Document is not available yet',409)
        directory=Path(app.config['DATABASE']).parent/'generated'
        path=(directory/row['id']/('document.'+kind)).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file(): raise Error('Document file not found',404)
        if kind=='html' and request.args.get('view')=='1':
            from .generation_page_preview import paginated_preview
            from flask import make_response
            response=make_response(paginated_preview(path.read_text()))
            response.headers['Content-Security-Policy']="default-src 'none'; script-src 'self'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
            return response
        response=send_file(path,as_attachment=request.args.get('view')!='1',download_name='nxflo-'+row['id'][:8]+'.'+kind,mimetype='application/pdf' if kind=='pdf' else 'text/html')
        response.headers['Content-Security-Policy']="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
        return response

    @app.get(BASE+'/jobs/<job_id>/preview')
    @login_required(owner=True)
    def preview(job_id):
        row=job_or_404(job_id)
        if row['status']!='preview': raise Error('Layout preview is not available',409)
        conn().execute('UPDATE generator_jobs SET previewed_at=? WHERE id=?',(db.now(),job_id))
        return jsonify(html=json.loads(row['state'])['html'])

    @app.post(BASE+'/jobs/<job_id>/publish')
    @login_required(owner=True)
    def publish(job_id):
        job_or_404(job_id)
        raise Error('Documents are private downloads. Public website publication is not enabled.',409)
