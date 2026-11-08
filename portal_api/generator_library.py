"""Persistent logical documents and saved versions; execution attempts stay internal."""
import json
import uuid
import re
from decimal import Decimal
from .generator_revisions import next_version
from . import db
from .generation_recovery import recovery_info

SAVED=('awaiting_html_review','ready','needs_review')
FINAL=('ready','needs_review')
LABELS={'queued':'Generating','running':'Generating','awaiting_html_review':'Awaiting HTML review','ready':'Ready','needs_review':'Needs review','failed':'Needs attention','cancelled':'Paused','preview':'Draft'}


def migrate(connection):
    with db.transaction(connection):
        connection.execute('CREATE TABLE IF NOT EXISTS generator_documents(id TEXT PRIMARY KEY,title TEXT NOT NULL,created_at TEXT NOT NULL)')
        connection.execute('''CREATE TABLE IF NOT EXISTS generator_versions(id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES generator_documents(id),
            version TEXT NOT NULL,config TEXT NOT NULL,created_at TEXT NOT NULL,saved_at TEXT,UNIQUE(document_id,version))''')
        columns={r['name'] for r in connection.execute('PRAGMA table_info(generator_jobs)')}
        for name,table in (('document_id','generator_documents'),('version_id','generator_versions')):
            if name not in columns:connection.execute('ALTER TABLE generator_jobs ADD COLUMN '+name+' TEXT REFERENCES '+table+'(id)')
        connection.execute('CREATE INDEX IF NOT EXISTS generator_jobs_version ON generator_jobs(version_id,created_at)')
        for name,event in (('insert','INSERT'),('update','UPDATE OF document_id,version_id')):
            connection.execute("CREATE TRIGGER IF NOT EXISTS generator_identity_"+name+" BEFORE "+event+" ON generator_jobs WHEN NEW.version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM generator_versions WHERE id=NEW.version_id AND document_id=NEW.document_id) BEGIN SELECT RAISE(ABORT,'Mismatched document/version identity'); END")
        connection.execute('''CREATE TRIGGER IF NOT EXISTS generator_version_saved AFTER UPDATE OF status ON generator_jobs
            WHEN NEW.status IN ('awaiting_html_review','ready','needs_review') AND NEW.version_id IS NOT NULL
            BEGIN UPDATE generator_versions SET saved_at=COALESCE(saved_at,NEW.updated_at) WHERE id=NEW.version_id; END''')
        connection.execute('''CREATE TRIGGER IF NOT EXISTS generator_version_saved_insert AFTER INSERT ON generator_jobs
            WHEN NEW.status IN ('awaiting_html_review','ready','needs_review') AND NEW.version_id IS NOT NULL
            BEGIN UPDATE generator_versions SET saved_at=COALESCE(saved_at,NEW.updated_at) WHERE id=NEW.version_id; END''')
        backfill(connection)


def backfill(connection):
    if not connection.execute('SELECT 1 FROM generator_jobs WHERE version_id IS NULL LIMIT 1').fetchone():return
    rows={r['id']:r for r in connection.execute('SELECT id,parent_id,document_id,version_id,config,status,created_at,updated_at FROM generator_jobs ORDER BY created_at,rowid')}
    def identity(row):
        current=row;seen=set()
        while True:
            if current['id'] in seen:return row['id'] # Ambiguous lineage stays separate, never title-matched.
            seen.add(current['id'])
            if current['document_id']:return current['document_id']
            parent=current['parent_id'] or json.loads(current['config']).get('revision_parent')
            if not parent or parent not in rows:return current['id']
            current=rows[parent]
    for row in rows.values():
        if row['version_id']:continue
        config=json.loads(row['config']);document=identity(row)
        connection.execute('INSERT OR IGNORE INTO generator_documents VALUES(?,?,?)',(document,config.get('title') or 'Untitled document',row['created_at']))
        label=config.get('version') or '1.0'
        version=uuid.uuid5(uuid.NAMESPACE_URL,'nxflo:'+document+':'+label).hex
        saved=row['updated_at'] if row['status'] in SAVED else None
        connection.execute('INSERT OR IGNORE INTO generator_versions VALUES(?,?,?,?,?,?)',(version,document,label,row['config'],row['created_at'],saved))
        version=connection.execute('SELECT id FROM generator_versions WHERE document_id=? AND version=?',(document,label)).fetchone()['id']
        if saved:connection.execute('UPDATE generator_versions SET saved_at=COALESCE(saved_at,?) WHERE id=?',(saved,version))
        connection.execute('UPDATE generator_jobs SET document_id=?,version_id=? WHERE id=?',(document,version,row['id']))


def attach_new(connection,job_id,config,created,parent=None):
    if parent:
        prior=connection.execute('SELECT document_id FROM generator_jobs WHERE id=?',(parent,)).fetchone()
        if not prior or not prior['document_id']:raise ValueError('Original document identity is missing')
        document=prior['document_id']
    else:
        document=uuid.uuid4().hex
        connection.execute('INSERT INTO generator_documents VALUES(?,?,?)',(document,config.get('title') or 'Untitled document',created))
    version=uuid.uuid4().hex
    connection.execute('INSERT INTO generator_versions VALUES(?,?,?,?,?,NULL)',(version,document,config['version'],json.dumps(config,ensure_ascii=False),created))
    connection.execute('UPDATE generator_documents SET title=? WHERE id=?',(config.get('title') or 'Untitled document',document))
    connection.execute('UPDATE generator_jobs SET document_id=?,version_id=? WHERE id=?',(document,version,job_id))
    return document,version


def library(connection):
    # Also attach legacy/manual records inserted after startup, without changing their jobs or files.
    if connection.execute('SELECT 1 FROM generator_jobs WHERE version_id IS NULL LIMIT 1').fetchone():
        with db.transaction(connection):backfill(connection)
    docs={r['id']:{'id':r['id'],'title':r['title'],'versions':[],'_versions':[]} for r in connection.execute('SELECT * FROM generator_documents')}
    jobs={}
    for row in connection.execute("""SELECT id,status,step,created_at,updated_at,recovery,next_run_at,version_id,json_extract(state,'$.publication_quality.outcome') AS publication_outcome,
        json_object('title',json_extract(config,'$.title'),'provider',json_extract(config,'$.provider'),'databricks_model',json_extract(config,'$.databricks_model'),
        'summary_model',json_extract(config,'$.summary_model'),'draft_model',json_extract(config,'$.draft_model'),
        'polish_model',json_extract(config,'$.polish_model')) AS config FROM generator_jobs ORDER BY updated_at,created_at,rowid"""):
        jobs.setdefault(row['version_id'],[]).append(row)
    def snapshot(row):
        info=recovery_info(connection,row)
        return {'job_id':row['id'],'status':row['status'],'status_label':('Draft · verification required' if row['publication_outcome']=='WARNING' and row['status']=='needs_review' else LABELS.get(row['status'],'In progress')),'updated_at':row['updated_at'],
            'can_resume':row['status'] in ('failed','cancelled') and bool(info['can_resume']),'recovery_blocked':bool(info['blocked_reason']),
            'notice':(info['blocked_reason'] if info['blocked_reason'] else 'Generation needs attention. Saved progress is preserved; resume generation to recover.' if row['status']=='failed' else 'Generation is paused. Saved progress is preserved.' if row['status']=='cancelled' else '')}
    for version in connection.execute('SELECT id,document_id,version,created_at,saved_at FROM generator_versions ORDER BY created_at,rowid'):
        attempts=jobs.get(version['id'],[])
        if not attempts:continue
        current=next((r for r in reversed(attempts) if r['status'] in ('queued','running')),attempts[-1]);final=next((r for r in reversed(attempts) if r['status'] in FINAL),None)
        saved=next((r for r in reversed(attempts) if r['status'] in SAVED),None)
        chosen=final if final and current['status'] not in ('queued','running','awaiting_html_review') else current
        item={**snapshot(chosen),'id':version['id'],'version':version['version'],'saved':bool(version['saved_at'] or saved),
              'pdf_job_id':final['id'] if final else None,'html_job_id':saved['id'] if saved else None,
              'updated_at':max(r['updated_at'] for r in attempts)}
        if chosen['id']!=current['id']:item['recovery']={**snapshot(current),'version':version['version']}
        document=docs[version['document_id']];document['_versions'].append(item)
        if item['saved']:document['versions'].insert(0,item)
        document['title']=json.loads(current['config']).get('title') or document['title']
    result=[]
    for document in docs.values():
        versions=document.pop('_versions')
        if not versions:continue
        latest=versions[-1];document['latest']=latest
        numeric=[v['version'] for v in versions if re.fullmatch(r'\d{1,6}(?:\.\d{1,6})?',v['version'])]
        document['next_version']=next_version(max(numeric,key=Decimal) if numeric else '1.0')
        document['updated_at']=max(v['updated_at'] for v in versions)
        document['latest_downloadable']=next((v for v in reversed(versions) if v['pdf_job_id']),None)
        document['current_work']=latest.get('recovery') or (None if latest['saved'] else latest)
        for version in document['versions']:version['is_current']=version['id']==latest['id']
        result.append(document)
    return sorted(result,key=lambda d:(d['updated_at'],d['id']),reverse=True)
