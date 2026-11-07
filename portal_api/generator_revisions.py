"""Server-assigned revision numbers and immutable document-control histories."""
from datetime import datetime
from decimal import Decimal
import json
import re
from zoneinfo import ZoneInfo


def next_version(version):
    if re.fullmatch(r'\d{1,6}(?:\.\d{1,6})?',version or ''):
        return format(Decimal(version)+Decimal('0.1'),'f')
    return '1.1'


def team_name(config):
    return next((team['name'] for team in config.get('teams',[]) if team['id']==config.get('prepared_team')),'')


def history_entry(config,created_at,summary=None):
    return {'version':config.get('version') or '1.0','date':datetime.fromisoformat(created_at.replace('Z','+00:00')).astimezone(ZoneInfo('America/Vancouver')).date().isoformat(),'prepared_by':team_name(config) or 'Not specified','summary':summary or config.get('change_summary') or 'Initial issue.'}


def prepare_revision(connection,parent,config,Error):
    row=connection.execute('SELECT * FROM generator_jobs WHERE id=?',(parent,)).fetchone()
    if not row:raise Error('Original document not found',404)
    if row['status'] not in ('ready','needs_review'):raise Error('Choose a completed document to revise',409)
    state=json.loads(row['state'])
    if not state.get('document',{}).get('chapters'):raise Error('This document has no generated text to revise',409)
    ancestors=[];current=row;seen=set()
    while current:
        if current['id'] in seen or len(ancestors)>1000:raise Error('Invalid revision history',409)
        seen.add(current['id']);ancestors.append(current)
        current=connection.execute('SELECT * FROM generator_jobs WHERE id=?',(current['parent_id'],)).fetchone() if current['parent_id'] else None
    root=ancestors[-1]['id']
    family=connection.execute('''WITH RECURSIVE family(id,config) AS (
        SELECT id,config FROM generator_jobs WHERE id=? UNION ALL
        SELECT j.id,j.config FROM generator_jobs j JOIN family f ON j.parent_id=f.id)
        SELECT config FROM family''',(root,)).fetchall()
    versions=[json.loads(item['config']).get('version','1.0') for item in family]
    numeric=[v for v in versions if re.fullmatch(r'\d{1,6}(?:\.\d{1,6})?',v)]
    latest=max(numeric,key=Decimal) if numeric else '1.0'
    if config.get('version_override'):
        if not config['version']:raise Error('Enter a version or turn off the version override')
        if config['version'] in versions:raise Error('This document version already exists. Choose a different override.',409)
    else:config['version']=next_version(latest)
    config['revision_parent']=parent
    history=state.get('revision_history')
    if history is None:
        history=[history_entry(json.loads(item['config']),item['created_at'],'Initial issue.' if not item['parent_id'] else 'Editorial revision.') for item in reversed(ancestors)]
    return list(history)
