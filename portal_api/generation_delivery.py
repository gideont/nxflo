"""Deliver usable drafts; keep verification and editorial findings in private history."""
from copy import deepcopy
import json
import re
from . import db
from .generation_errors import GenerationError

POLICY='draft_first'

def enabled(state):return state.get('delivery_policy')==POLICY

def migrate(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS generator_version_reviews(
        version_id TEXT PRIMARY KEY REFERENCES generator_versions(id),job_id TEXT NOT NULL,
        updated_at TEXT NOT NULL,report TEXT NOT NULL)''')

def issues(state,stage,reasons,chapter=None):
    saved=state.setdefault('delivery_issues',[])
    for reason in reasons:
        message=str(reason);where=str(chapter) if chapter is not None else None
        match=re.match(r'Chapter (\d+):\s*',message)
        if match and (where is None or where==match[1]):where=match[1];message=message[match.end():]
        item={'stage':stage,'reason':message,'chapter':where,'status':'open'}
        if not any((i['stage'],i['reason'],i.get('chapter'))==(stage,message,where) for i in saved):saved.append(item)
    return state

def persist(engine,state):
    row=engine.db.execute('SELECT version_id FROM generator_jobs WHERE id=?',(engine.id,)).fetchone()
    if not row or not row['version_id']:return
    research=state.get('research',{})
    source_lookup={source['id']:source for source in state.get('sources',[])}
    original=state.get('delivery_original_candidate',state.get('document',{}))
    register=[]
    for index,ch in enumerate(original.get('chapters',[])):
        for claim in ch.get('claims',[]):
            if not isinstance(claim,dict) or claim.get('classification')!='empirical':continue
            source=source_lookup.get(claim.get('source_id'),{});quote=claim.get('quote','')
            register.append({'chapter':index+1,'statement':claim.get('text',''),'source_id':claim.get('source_id',''),'source_url':source.get('url',''),
                'submitted_quote':quote,'quote_matches':isinstance(quote,str) and bool(quote) and ' '.join(quote.split()) in ' '.join(source.get('text','').split())})
    report={'policy':POLICY,'job_id':engine.id,'outcome':state.get('publication_quality',{}).get('outcome','PENDING'),
        'issues':state.get('delivery_issues',[]),'verification':research,'corrections':state.get('research_corrections',[]),
        'chapter_diagnostics':state.get('delivery_chapter_diagnostics',{}),'claim_register':register,
        'sources':[{'id':s['id'],'url':s.get('url',''),'label':s.get('label',''),'available':bool(s.get('text'))} for s in state.get('sources',[])], 'updated_at':db.now()}
    engine.db.execute('INSERT INTO generator_version_reviews VALUES(?,?,?,?) ON CONFLICT(version_id) DO UPDATE SET job_id=excluded.job_id,updated_at=excluded.updated_at,report=excluded.report',
        (row['version_id'],engine.id,report['updated_at'],json.dumps(report,ensure_ascii=False)))

def report(connection,version_id):
    row=connection.execute('SELECT report FROM generator_version_reviews WHERE version_id=?',(version_id,)).fetchone()
    return json.loads(row['report']) if row else {'policy':POLICY,'issues':[],'verification':{},'corrections':[]}

def sanitize(state,document):
    """Remove invalid attributions, not the author's unverified assertions."""
    result=deepcopy(document);sources={s['id']:s for s in state.get('sources',[]) if s.get('text')}
    def text(value,where):
        if not isinstance(value,str):return value
        unknown=set(re.findall(r'\[([A-Z]\d+)\]',value))-sources.keys()
        if unknown:
            issues(state,'citation cleanup',[where+': removed unavailable citation '+', '.join('['+v+']' for v in sorted(unknown))+'.'])
            value=re.sub(r'\[([A-Z]\d+)\]',lambda m:m[0] if m[1] in sources else '',value)
        return value
    for i,ch in enumerate(result.get('chapters',[])):
        where='Chapter '+str(i+1)
        ch['paragraphs']=[text(p,where) for p in ch.get('paragraphs',[]) if isinstance(p,str) and p.strip()]
        ch['takeaway']=text(ch.get('takeaway',''),where)
        ch['claims']=[claim for claim in ch.get('claims',[]) if isinstance(claim,dict)]
        for claim in ch['claims']:
            source=sources.get(claim.get('source_id'));quote=claim.get('quote','')
            if claim.get('classification')=='empirical' and (not source or not isinstance(quote,str) or not quote or ' '.join(quote.split()) not in ' '.join(source['text'].split())):
                issues(state,'citation cleanup',[where+': removed an unsupported source attribution from the claim register. Statement: '+str(claim.get('text',''))])
                if isinstance(quote,str) and len(quote)>=20:
                    quoted=['"'+quote+'"','“'+quote+'”','‘'+quote+'’']
                    clean=[p for p in ch['paragraphs'] if not any(value in p for value in quoted)]
                    if len(clean)!=len(ch['paragraphs']):
                        issues(state,'citation cleanup',[where+': removed an untraceable verbatim quotation from reader-facing prose. Original quotation: '+quote])
                        ch['paragraphs']=clean
                claim.update(classification='authorial',source_id='',quote='')
        for table in ch.get('tables',[]):
            table['title']=text(table.get('title',''),where)
            table['rows']=[[text(cell,where) for cell in row] for row in table.get('rows',[])]
            if table.get('classification')=='empirical':
                from .generation_quality import table_issues
                problems=table_issues(table,list(sources.values()))
                if problems:
                    issues(state,'table attribution',problems,i+1)
                    table.update(classification='authorial',evidence=[])
    if not result.get('chapters') or any(not ch.get('paragraphs') for ch in result['chapters']):raise GenerationError('No readable chapter text is available to export. Saved work is preserved.')
    return result

def critical_issues(state,config):
    """Keep citation fabrication, financial integrity and renderability blocking."""
    from .generation_quality import provenance_issues,manuscript_text
    document=state.get('document',{})
    problems=provenance_issues(document,state.get('sources',[]),{**config,'_pipeline_version':2},state.get('financials'),state.get('research'))
    critical=[p for p in problems if any(term in p for term in ('Unknown source citation','fabricated source quotation','Model-written numerical projections'))]
    if re.search(r'(?i)\b(?:ROI|NPV|IRR|revenue|net_cash_flow|cumulative_cash_flow)\s*=',manuscript_text(document)):
        critical.append('An unregistered financial formula must be repaired before export.')
    if state.get('financials'):
        from .generation_finance import build_financials
        try:
            expected=build_financials({'groups':[{k:v for k,v in group.items() if k!='results'} for group in state['financials']['groups']]})
            if expected!=state['financials']:critical.append('Stored financial outputs contradict their registered formulas or assumptions.')
        except (GenerationError,KeyError,TypeError):critical.append('Financial calculations cannot be validated.')
    return list(dict.fromkeys(critical))

def recover(state,config):
    """Promote saved repaired prose without replaying paid chapter generation."""
    state=deepcopy(state);state['delivery_policy']=POLICY;state['research_policy']=2
    candidate=state.get('blocked_candidate') or state.get('document')
    if not candidate or not candidate.get('chapters'):return state
    issues(state,'previous validation',state.get('quality_errors',[]))
    for chapter,reasons in state.get('chapter_diagnostics',{}).items():issues(state,'previous validation',reasons,chapter)
    state['delivery_chapter_diagnostics']=deepcopy(state.get('chapter_diagnostics',{}))
    state.setdefault('delivery_original_candidate',deepcopy(candidate))
    # Production instructions were incorrectly drafted as reader-facing chapters.
    # Keep the saved subject chapter(s); retain the complete candidate privately.
    page_keys={h['id'] for h in state.get('author_contract',{}).get('structure',[]) if re.match(r'PAGE\s+\d+\b',h['title'],re.I)}
    if page_keys and re.search(r'DOCUMENT GENERATION BRIEF',state.get('author_original',''),re.I):
        selected=[(i,ch) for i,ch in enumerate(candidate['chapters']) if page_keys.intersection(ch.get('section_keys',[]))]
        if selected and len(selected)<len(candidate['chapters']):
            state['delivery_original_outline']=deepcopy(state['outline'])
            candidate={**candidate,'chapters':[ch for _,ch in selected]}
            state['outline']={**state['outline'],'chapters':[state['outline']['chapters'][i] for i,_ in selected]}
            for ch in candidate['chapters']:
                if re.search(r'CONTENT PLAN',ch['title'],re.I):ch['title']=config['title']
            issues(state,'structure recovery',['Removed production-brief scaffolding from the reader export; the saved subject prose and tables were retained. The original candidate is preserved for review.'])
    state['document']=sanitize(state,candidate)
    critical=critical_issues(state,config)
    if critical:raise GenerationError('Critical integrity correction is still required: '+' '.join(critical))
    state.update(next_step='charts',delivery_saved_work_only=True,blocked_candidate=None,quality_errors=[],chapter_diagnostics={})
    return state

def capture_findings(state,stage,findings):
    for finding in findings:
        reason=finding.get('reason','Review incomplete.')
        if finding.get('claim'):reason+=' Statement: '+finding['claim']
        issues(state,stage,[reason],finding.get('chapter'))

def retain(pipeline,state,document,stage,reasons,diagnostics):
    state=deepcopy(state)
    state.setdefault('delivery_original_candidate',deepcopy(document))
    issues(state,stage,reasons)
    state['delivery_chapter_diagnostics']={str(i+1):value for i,value in diagnostics.items()}
    state['document']=sanitize(state,document)
    critical=critical_issues(state,pipeline.config)
    if critical:raise GenerationError('Critical integrity correction is still required: '+' '.join(critical))
    persist(pipeline.e,state)
    return {'document':state['document'],'delivery_issues':state.get('delivery_issues',[]),'delivery_original_candidate':state['delivery_original_candidate'],'delivery_chapter_diagnostics':state['delivery_chapter_diagnostics'],
        'blocked_candidate':None,'quality_errors':[],'chapter_diagnostics':{},
        'intent_audits':state.get('intent_audits',[])+[{'stage':stage,'passed':False,'outcome':'WARNING','details':'Review issues retained in version history.'}]}

def finish_pdf(engine,state):
    from pypdf import PdfReader
    actual=len(PdfReader(engine.directory/'document.pdf').pages)
    state['delivered_pages']=actual
    exact=re.search(r'exactly\s+(\d+)\b[^\n]{0,60}\bpages',state.get('author_original',''),re.I)
    target=int(exact[1]) if exact else engine.config.get('pages') if engine.config.get('length_mode')=='target' else None
    if target and actual!=target:
        issues(state,'layout',[f"Requested {target} pages; exported {actual} pages. Revisit layout if an exact page count is required."])
    if state.get('delivery_issues'):
        state['publication_quality'].update(outcome='WARNING',passed=False)
        state['warnings']=['Private review notes are saved in version history.']
    persist(engine,state)
