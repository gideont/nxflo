"""Verification is a delivery qualification, never evidence of authorial correctness."""
import json
import re
from urllib.parse import urlsplit
from .generation_intent import digest
from .generation_errors import GenerationError

POLICY_VERSION=1
RESEARCH_REVIEW_POLICY=2
LEGAL=re.compile(r'\b(?:regulat(?:ion|ory|ions)|bylaws?|zoning|MEHKO|MIKO|legaliz\w*|licens(?:e|ing)|permits?|statut(?:e|ory)|insurance coverage|food premises|clients? per day|home.occupation|strata|insurance|bans?|prohibit\w*)\b',re.I)
CRITICAL=re.compile(r'fabricat\w*|invented (?:citation|source|quote|data)|incorrect (?:calculation|arithmetic)|broken calculation|contradict(?:s|ory|ion)',re.I)
RESEARCH_INTEGRITY=re.compile(r'fabricat\w*|invented (?:citation|source|quote|data)|incorrect (?:calculation|arithmetic)|broken calculation|internal(?:ly)? (?:document |manuscript )?contradict\w*|self.contradict\w*|contradict\w* (?:\w+ ){0,3}(?:formulas?|calculations?|arithmetic)',re.I)
MISSING=re.compile(r'unverified|uncorroborated|without (?:external |source )?(?:verification|evidence|citations)|no (?:exact |matching |external |source )*(?:evidence|citations)|lack\w* (?:external |source )?(?:verification|evidence|corroboration)|cannot be certified|requiring verification',re.I)


def external_proof(claim,sources):
    source=next((s for s in sources if s['id']==claim.get('source_id') and s.get('role')=='external'),None)
    quote=claim.get('quote','')
    return bool(source and quote and ' '.join(quote.split()) in ' '.join(source.get('text','').split()))


def verification_findings(state):
    findings=[];sources=state['sources']
    for i,ch in enumerate(state['document']['chapters']):
        for block,p in [(f'P{i}.{j}',p) for j,p in enumerate(ch['paragraphs'])]+([(f'K{i}',ch['takeaway'])] if ch.get('takeaway') else []):
            claims=[c for c in ch.get('claims',[]) if c.get('text') and c['text'] in p]
            empirical=[c for c in claims if c.get('classification')=='empirical' and not external_proof(c,sources)]
            proposal=bool(re.match(r'(?:The author proposes|We propose|Our proposal|A proposed|A hypothetical|The proposed|The hypothetical)\b',p,re.I))
            factual=bool(re.search(r'\d|\b(?:current|existing|requires?|prohibits?|bans?|legally|introduced|enacted)\b',p,re.I))
            regulatory=bool(LEGAL.search(p)) and not (proposal and not factual)
            # A quotation proves provenance, not the current legal interpretation.
            # Regulatory text must also pass the independent accuracy review.
            if empirical or regulatory:
                findings.append({'code':'regulatory_evidence' if regulatory else 'unverified_claim','kind':'verification',
                    'reason':('Regulatory statement requires confirmation against current authoritative sources.' if regulatory else 'Author-provided factual claim has not been independently verified.'),
                    'blocks':[block],'claim':p,'chapter':i+1})
        for j,table in enumerate(ch.get('tables',[])):
            if table.get('classification')=='empirical' and any(not external_proof(proof,sources) for proof in table.get('evidence',[])):
                findings.append({'code':'unverified_table','kind':'verification','reason':'This empirical table is supported only by author-provided material, not independently verified evidence.','blocks':[f'T{i}.{j}'],'claim':table['title'],'chapter':i+1})
    for j,chart in enumerate(state.get('charts',[])):
        if chart.get('classification')=='hypothetical':continue
        ids=re.findall(r'Source \[([A-Z]\d+)\]',chart.get('caption',''))
        if any(not any(s['id']==ref and s.get('role')=='external' for s in sources) for ref in ids):
            findings.append({'code':'unverified_chart','kind':'verification','reason':'This empirical chart reproduces author-provided values; independent verification is incomplete.','blocks':[f'EMPIRICAL-{j}'],'claim':chart.get('caption',''),'chapter':chart['chapter']+1})
    return findings


def review_findings(review,state,blocks):
    """Unknown/ambiguous failures fail closed; only incomplete accuracy is advisory."""
    from .generation_publication import validate_bound_review
    try:_,bound=validate_bound_review(review,state,blocks)
    except GenerationError:
        if state.get('research_policy')!=2:raise
        checks=review.get('checks',[]) if isinstance(review,dict) else []
        critical=[check for check in checks if isinstance(check,dict) and check.get('passed') is False and (check.get('issue_type')=='integrity' or RESEARCH_INTEGRITY.search(str(check.get('reason',''))))] if isinstance(checks,list) else []
        if critical:return ([{'code':str(c.get('criterion','review_integrity')),'kind':'integrity','reason':str(c.get('reason','Critical integrity finding.')),'blocks':[]} for c in critical],[])
        return ([{'code':'review_protocol','kind':'verification','reason':'Independent publication review was malformed or incomplete. It cannot certify publication; deterministic manuscript integrity checks still apply.','blocks':[]}],[])
    findings=[]
    for check in review['checks']:
        ids=check.get('evidence_blocks',[])
        valid=isinstance(ids,list) and bool(ids) and all(isinstance(b,str) and b in blocks for b in ids)
        if check['passed'] and valid:continue
        reason=check['reason'];kind='verification' if state.get('research_policy')==2 else 'integrity'
        if check['passed'] and not valid and state.get('research_policy')==2:
            findings.append({'code':'review_protocol:'+check['criterion'],'kind':'verification','reason':'Independent publication review passed '+check['criterion']+' without valid manuscript references. This check cannot certify publication.','blocks':[]})
            continue
        if not check['passed']:
            declared=check.get('issue_type')
            # Old completed reviews used no severity field. Migrate only explicit
            # missing-evidence rejections; an ambiguous accuracy failure stays blocked.
            legacy=check['criterion']=='accuracy' and declared is None and MISSING.search(reason)
            cleaned=re.sub(r'not (?:for )?(?:a )?(?:demonstrated |actual )?contradiction','',reason,flags=re.I)
            advisory=(check['criterion']=='accuracy' and declared=='unverified_claim') or legacy
            if state.get('research_policy')==2 and declared=='unverified_claim':advisory=True
            critical=RESEARCH_INTEGRITY if state.get('research_policy')==2 else CRITICAL
            if state.get('research_policy')==2:
                if declared=='integrity' or critical.search(cleaned):kind='integrity'
                elif declared!='unverified_claim':reason+=' The reviewer returned an unclassified failure; this check cannot certify publication.'
                if check['criterion']=='purpose' and declared!='unverified_claim':kind='integrity'
            elif advisory and not critical.search(cleaned) and valid:kind='verification'
        if not valid and kind=='verification':
            ids=[key for key in ids if isinstance(key,str) and key in blocks] if isinstance(ids,list) else []
            reason+=' The reviewer included an unknown manuscript reference; this finding cannot certify publication.'
            valid=True
        findings.append({'code':check['criterion'],'kind':kind,'reason':reason if valid else check['criterion']+': review references unknown or missing publication evidence.','blocks':ids if valid else []})
    return findings,bound


def decide(state,review,blocks):
    findings,bound=review_findings(review,state,blocks)
    verified=any(c['criterion']=='accuracy' and c.get('passed') is True for c in bound)
    local=verification_findings(state)
    research=state.get('research',{})
    verified_blocks=set()
    if state.get('research_policy')==2 and research:
        from .research_workflow import blocks as manuscript_blocks
        content=manuscript_blocks(state)
        sources={source['id']:source for source in state['sources']}
        for key,block in content.items():
            related=[claim for claim in research.get('claims',[]) if key in claim.get('blocks',[])]
            good=bool(related) and research.get('block_hashes',{}).get(key)==digest(block['text'])
            for claim in related:
                good=good and claim.get('status') in ('supported','corrected') and bool(claim.get('evidence'))
                for proof in claim.get('evidence',[]):
                    source=sources.get(proof.get('source_id'))
                    good=good and bool(source and source.get('role')=='external' and proof.get('source_hash')==digest(source['text']) and proof.get('quote') in source['text'])
            if good:verified_blocks.add(key)
        for claim in research.get('claims',[]):
            if claim.get('status') not in ('supported','corrected'):
                findings.append({'code':'claim:'+claim['id'],'kind':'verification','reason':claim.get('reason','Verification incomplete.'),'blocks':claim.get('blocks',[]),'claim':claim['text']})
        if research.get('status')!='complete':
            findings.append({'code':'research_incomplete','kind':'verification','reason':research.get('message','Independent research is incomplete.'),'blocks':[]})
        # A verified claim ledger cannot clear unrelated or changed text.
        local=[finding for finding in local if not finding.get('blocks') or not set(finding['blocks'])<=verified_blocks]

    # Successful independent review can confirm sourced regulatory statements;
    # author-only assertions remain unverified even if a reviewer approves them.
    for finding in local:
        p=finding['claim'];ch=state['document']['chapters'][finding['chapter']-1]
        proof=any(c.get('text')==p and external_proof(c,state['sources']) for c in ch.get('claims',[]))
        if not (finding['code']=='regulatory_evidence' and verified and proof):findings.append(finding)
    findings=list({digest(f):f for f in findings}.values())
    outcome='BLOCKED' if any(f['kind']=='integrity' for f in findings) else 'WARNING' if findings else 'PASS'
    return outcome,findings,bound


def authoritative_url(url):
    host=(urlsplit(url).hostname or '').lower()
    return url.startswith('https://') and (host.endswith(('.gov','.gov.uk','.gov.au','.gc.ca','.gov.bc.ca','.europa.eu')) or host in ('vancouver.ca','www.vancouver.ca','vch.ca','www.vch.ca'))


def research(pipeline,state):
    """Reuse the single reserved search; download only primary regulatory pages."""
    config=pipeline.config
    pending=[f for f in verification_findings(state) if f['code']=='regulatory_evidence']
    if not pending or not config.get('web_search') or config.get('web_budget_usd',0.30)<=0:return state
    identity=digest({'document':state['document'],'policy':POLICY_VERSION})
    if state.get('verification_research',{}).get('identity')==identity:return state
    attempt={'identity':identity,'status':'attempted'}
    # Persist the bound before optional I/O. Provider uncertainty still uses the
    # existing submission guards; a resume never starts another search.
    state={**state,'verification_research':attempt};pipeline.e.checkpoint(state)
    try:
        if config.get('provider')=='databricks':raise GenerationError('Budgeted web discovery is unavailable through the configured Databricks provider.')
        result=pipeline.models.many('summary',['Find current primary government or regulator sources to verify these regulatory statements. Return source URLs and evidence, including contrary evidence. '+json.dumps([f['claim'] for f in pending])[:12000]],'web-research',structured=False,web=True)[0]
        urls=[a.get('url_citation',{}).get('url','') for a in result.get('annotations',[]) if a.get('type')=='url_citation']
        from .generation_sources import fetch_reference
        from .generation_tasks import monitored_call
        sources=list(state['sources'])
        for url in list(dict.fromkeys(urls))[:5]:
            if not authoritative_url(url) or any(s.get('url')==url and s.get('text') for s in sources):continue
            try:
                text,final=monitored_call(pipeline.e.db,pipeline.e.id,'Authoritative regulatory evidence',45,fetch_reference,(url,),check=pipeline.models.check,message=pipeline.e.message)
                if not authoritative_url(final):continue
                source_id='V'+str(len(sources)+1)
                remaining=8000000-sum(len(s.get('text','')) for s in sources)
                if remaining<=0:break
                sources.append({'id':source_id,'label':'Authoritative regulatory reference','role':'external','url':final,'text':text[:min(60000,remaining)]})
            except GenerationError:continue
        state={**state,'sources':sources,'verification_research':{**attempt,'status':'complete'}}
    except GenerationError as error:
        state={**state,'verification_research':{**attempt,'status':'unavailable','reason':str(error)}}
    pipeline.e.checkpoint(state)
    return state
