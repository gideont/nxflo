"""Private verification-only revisions and explicit shared-allowance increases."""
from copy import deepcopy
import json
import os
import uuid
from flask import jsonify,request
from . import db
from .generation_errors import GenerationError
from .generation_intent import digest
from .generator_revisions import prepare_revision,history_entry
from .generator_library import attach_new
from .research_store import ensure_budget,increase,summary
from .research_workflow import report,VALIDATION_POLICY


def start_verification(connection,parent_id,Error):
    with db.transaction(connection):
        parent=connection.execute('SELECT * FROM generator_jobs WHERE id=?',(parent_id,)).fetchone()
        if not parent:raise Error('Document not found',404)
        original=json.loads(parent['state']);config=json.loads(parent['config'])
        if parent['status'] not in ('ready','needs_review','awaiting_html_review') or not original.get('document',{}).get('chapters'):raise Error('Choose a complete manuscript to verify',409)
        if config.get('provider')!='databricks':raise Error('Select the configured Databricks model for research; alternate AI models are not used.',409)
        from .generation_providers import databricks_settings
        try:settings=databricks_settings()
        except GenerationError as error:raise Error(str(error),503)
        if not os.environ.get('TAVILY_API_KEY','').strip():raise Error('Tavily is not configured on the running server.',503)
        ensure_budget(connection,parent['document_id'],5)
        limit=summary(connection,parent['document_id'])['limit']
        research=original.get('research',{})
        if original.get('operation')=='verification' and research.get('status')=='complete' and research.get('validation_policy')==VALIDATION_POLICY and research.get('model')==settings['model'] and research.get('as_of')==db.now()[:10] and research.get('budget',{}).get('limit',0)>=limit:
            from .research_workflow import blocks
            if research.get('block_hashes')=={key:digest(value['text']) for key,value in blocks({**original,'config':config}).items()}:
                return {'id':parent['id'],'document_id':parent['document_id'],'version_id':parent['version_id'],'version':config['version'],'status':parent['status'],'reused':True}
        input_key=digest({'document':original['document'],'sources':original.get('sources',[]),'model':settings['model'],'limit':limit,'date':db.now()[:10],'policy':2,'validation':VALIDATION_POLICY})
        for row in connection.execute('SELECT id,state,config,status,document_id,version_id FROM generator_jobs WHERE document_id=? ORDER BY created_at DESC',(parent['document_id'],)):
            saved=json.loads(row['state'])
            if saved.get('verification_request_key')==input_key:
                return {'id':row['id'],'document_id':row['document_id'],'version_id':row['version_id'],'version':json.loads(row['config'])['version'],'status':row['status'],'reused':True}
        if connection.execute("SELECT 1 FROM generator_jobs WHERE status IN ('running','queued')").fetchone():raise Error('Another document is generating. Wait for it to finish.',409)
        uncertain=connection.execute("SELECT c.stage FROM generator_calls c JOIN generator_jobs j ON j.id=c.job_id WHERE j.document_id=? AND c.status='submitting' AND c.remote_id IS NULL LIMIT 1",(parent['document_id'],)).fetchone()
        if uncertain:raise Error('A prior '+uncertain['stage']+' request has an unknown provider outcome. Reconcile its activity before another verification request.',409)
        config.update(web_search=True,web_budget_usd=limit,version_override=False,databricks_model=settings['model'],feedback='',change_summary='Independent research, factual verification, and documented corrections.')
        # Revisions use the existing immutable lineage and automatic version allocator.
        if parent['status']=='awaiting_html_review':raise Error('Continue the HTML review before creating a verification revision.',409)
        history=prepare_revision(connection,parent_id,config,Error);created=db.now();history.append(history_entry(config,created))
        state=deepcopy(original)
        for key in ('publication_review_deferred','publication_quality','publication_review','publication_review_fingerprint','html_approved','quality_errors','blocked_candidate','chapter_diagnostics','research'):
            state.pop(key,None)
        state.update(revision_history=history,research_policy=2,operation='verification',verification_request_key=input_key,verification_parent=parent_id,next_step='assemble',reused_generation=True)
        state['warnings']=[w for w in state.get('warnings',[]) if not w.startswith('Verification required:')]
        job_id=uuid.uuid4().hex
        events=[{**event,'reused':True} for event in json.loads(parent['events']) if event.get('status')=='complete' and event.get('step') not in ('assemble','html_review','pdf','deliver')]
        connection.execute('INSERT INTO generator_jobs(id,config,status,step,state,events,created_at,updated_at,parent_id,message) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (job_id,json.dumps(config,ensure_ascii=False),'queued','assemble',json.dumps(state,ensure_ascii=False),json.dumps(events),created,created,parent_id,'Queued for independent verification. Saved chapters and previous downloads are retained.'))
        document_id,version_id=attach_new(connection,job_id,config,created,parent_id)
        return {'id':job_id,'document_id':document_id,'version_id':version_id,'version':config['version'],'status':'queued','reused':False}


def register(app,connection,login_required,Error,job_or_404,base):
    @app.post(base+'/jobs/<job_id>/verify')
    @login_required(owner=True)
    def verify(job_id):return jsonify(start_verification(connection(),job_id,Error)),202

    @app.get(base+'/jobs/<job_id>/verification')
    @login_required(owner=True)
    def verification_report(job_id):
        row=job_or_404(job_id)
        return jsonify(report(json.loads(row['state']),summary(connection(),row['document_id'])))

    @app.post(base+'/documents/<document_id>/research-budget')
    @login_required(owner=True)
    def research_budget(document_id):
        if not connection().execute('SELECT 1 FROM generator_documents WHERE id=?',(document_id,)).fetchone():raise Error('Document not found',404)
        body=request.get_json(silent=True)
        if not isinstance(body,dict) or set(body)!={'limit_usd'}:raise Error('Supply the new total research allowance.')
        try:value=increase(connection(),document_id,body['limit_usd'])
        except GenerationError as error:raise Error(str(error),400)
        return jsonify(value)
