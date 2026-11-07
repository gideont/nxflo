"""Publication and provenance checks applied to prose, not only model metadata."""
import re
from .generation_errors import GenerationError
from .generation_intent import digest,fidelity_issues
from .generation_document import chart_svg

PLACEHOLDERS=re.compile(r'\bTODO\b|\bTBD\b|\bFIXME\b|\[\s*(?:insert|citation needed|placeholder)[^\]]*\]|\b(?:insert (?:chart|table|text) here|rewrite this paragraph|as an AI language model|editorial instruction|editorial note|drafting instructions?|instructions? to (?:the )?(?:writer|editor)|please add|to be (?:completed|written)|chart goes here|replace this text|lorem ipsum)\b',re.I)
DISCLAIMERS=re.compile(r'not financial advice|not independently verified|unverified (?:claim|concept)|cannot be verified|independent verification (?:is )?required',re.I)


def manuscript_text(document):
    parts=[]
    for ch in document.get('chapters',[]):
        parts.extend([ch.get('title',''),*ch.get('paragraphs',[]),ch.get('takeaway','')])
        for table in ch.get('tables',[]):parts.extend([table.get('title',''),*table.get('columns',[]),*(str(cell) for row in table.get('rows',[]) for cell in row)])
    return '\n'.join(parts)


def table_issues(table,sources):
    if not isinstance(table,dict):return ['Invalid content table.']
    cols=table.get('columns');rows=table.get('rows');kind=table.get('classification')
    if not isinstance(table.get('title'),str) or not isinstance(cols,list) or not 1<=len(cols)<=8 or any(not isinstance(c,str) or not c.strip() for c in cols) or not isinstance(rows,list) or not rows or len(rows)>100:return ['Invalid content table dimensions.']
    if any(not isinstance(row,list) or len(row)!=len(cols) or any(not isinstance(cell,str) or len(cell)>2000 for cell in row) for row in rows):return ['Invalid content table cells.']
    if kind not in ('authorial','empirical'):return ['Hypothetical numerical tables must be calculated by the financial engine.']
    if kind=='empirical':
        evidence=table.get('evidence',[])
        if len(evidence)!=len(rows):return ['Each empirical table row needs exact source evidence.']
        for row,proof in zip(rows,evidence):
            source=next((s for s in sources if s['id']==proof.get('source_id')),None)
            quote=proof.get('quote','')
            if not source or not quote or ' '.join(quote.split()) not in ' '.join(source.get('text','').split()):return ['Empirical table evidence does not match its source.']
            nums=re.findall(r'-?\d[\d,]*(?:\.\d+)?',' '.join(row))
            if any(n.replace(',','') not in quote.replace(',','') for n in nums):return ['An empirical table number lacks matching source evidence.']
    return []


def provenance_issues(document,sources,config,financials=None):
    errors=[];available={s['id']:s for s in sources if s.get('text')}
    for ch in document.get('chapters',[]):
        text=' '.join(ch.get('paragraphs',[]))
        for citation in re.findall(r'\[([A-Z]\d+)\]',text):
            if citation not in available:errors.append('Unknown source citation ['+citation+'].')
        for claim in ch.get('claims',[]):
            if claim.get('classification') not in ('empirical','authorial'):errors.append('Model-written numerical projections are not permitted; use the financial engine.');continue
            if not isinstance(claim.get('text'),str) or claim['text'] not in text:errors.append('A claim register entry is absent from the chapter.');continue
            if claim['classification']=='empirical':
                source=available.get(claim.get('source_id'));quote=claim.get('quote','')
                if not source or not quote or ' '.join(quote.split()) not in ' '.join(source['text'].split()):errors.append('An empirical claim lacks exact source evidence.')
                elif any(number.replace(',','') not in quote.replace(',','') for number in re.findall(r'-?\d[\d,]*(?:\.\d+)?',claim['text'])):errors.append('An empirical claim contains an unsupported number.')
        for table in ch.get('tables',[]):errors.extend(table_issues(table,sources))
        for chart in ch.get('charts',[]):
            try:chart_svg(chart,config,sources)
            except (ValueError,TypeError,KeyError):errors.append('An empirical chart failed source verification.')
    if config.get('_pipeline_version')==2:
        # Reject unregistered prose numbers before semantic review. This is an
        # additional check, not a substitute for checking meaning and provenance.
        allowed={'0','1','2','3'}
        for source in sources:
            if source.get('role')=='author':allowed.update(n.replace(',','') for n in re.findall(r'-?\d[\d,]*(?:\.\d+)?',source.get('text','')))
        for ch in document.get('chapters',[]):
            for claim in ch.get('claims',[]):
                if claim.get('classification')=='empirical':allowed.update(n.replace(',','') for n in re.findall(r'-?\d[\d,]*(?:\.\d+)?',claim.get('quote','')))
        def numbers(value,key=''):
            if isinstance(value,dict):
                for name,item in value.items():numbers(item,name)
            elif isinstance(value,list):
                for item in value:numbers(item,key)
            elif type(value) in (int,float):
                variants=[value]
                if any(word in key for word in ('rate','growth','share','irr')):variants.append(value*100)
                for number in variants:
                    allowed.update((str(number),f'{number:.0f}',f'{number:.1f}',f'{number:.2f}'))
        if financials:numbers(financials)
        for ch in document.get('chapters',[]):
            texts=list(ch.get('paragraphs',[]))+[cell for table in ch.get('tables',[]) if table.get('classification')=='authorial' for row in table.get('rows',[]) for cell in row]
            for paragraph in texts:
                clean=re.sub(r'\[[A-Z]\d+\]','',paragraph)
                for value in re.findall(r'-?\d[\d,]*(?:\.\d+)?',clean):
                    number=value.replace(',','')
                    if number not in allowed and (number.rstrip('0').rstrip('.') if '.' in number else number) not in allowed:errors.append('A prose number is absent from the author material, cited claim register and calculated projections: '+number+'.')
    return list(dict.fromkeys(errors))


def local_publication_issues(document,contract,config,sources,plans,financials=None):
    issues=fidelity_issues(document,contract,plans)+provenance_issues(document,sources,config,financials)
    text=manuscript_text(document)
    if PLACEHOLDERS.search(text):issues.append('Unfinished placeholder or editorial instruction leaked into the manuscript.')
    if len(DISCLAIMERS.findall(text))>1:issues.append('Repetitive blanket disclaimers are replacing useful content.')
    # Formula bodies are rendered from a registry. Free-text equations bypass
    # that single source of truth and must be expressed as formula references.
    if re.search(r'(?i)\b(?:ROI|NPV|IRR|revenue|net_cash_flow|cumulative_cash_flow)\s*=|ROI\s+(?:is|equals)\s+(?:gross\s+)?revenue\s*(?:/|divided by)',text):issues.append('An unregistered or contradictory financial formula appears in the prose. Use a registered formula reference.')
    keys={key for ch in document.get('chapters',[]) for key in ch.get('section_keys',[])}
    for key in set(contract['required_sections'])-keys:issues.append('Missing required section: '+key+'.')
    for ch in document.get('chapters',[]):
        if not ch.get('paragraphs') or any(not p.strip() for p in ch['paragraphs']):issues.append('A required chapter is unfinished.')
    return list(dict.fromkeys(issues))


def criteria(contract):
    return ['author:'+item['id'] for item in contract['items']]+['section:'+key for key in contract['required_sections']]+['purpose','accuracy','formulas','publication']


def validate_publication_review(review,document,contract):
    checks=review.get('checks') if isinstance(review,dict) else None
    expected=set(criteria(contract));text=manuscript_text(document)
    if not isinstance(checks,list) or len(checks)!=len(expected) or {c.get('criterion') for c in checks if isinstance(c,dict)}!=expected:raise GenerationError('Publication review did not evaluate every author anchor, required section, factual accuracy and calculation consistency.')
    failures=[]
    for check in checks:
        if type(check.get('passed')) is not bool or not isinstance(check.get('reason'),str):raise GenerationError('Malformed publication review.')
        if not check['passed']:failures.append(check['criterion']+': '+check['reason'])
        elif not isinstance(check.get('evidence'),str) or len(check['evidence'])<20 or check['evidence'] not in text:failures.append(check['criterion']+': publication review has no real manuscript evidence.')
    return failures


def publication_fingerprint(state):
    payload={'document':state['document'],'contract':state['author_contract'],'financials':state.get('financials')}
    if 'publication_assets' in state:
        payload.update(publication_assets=state['publication_assets'],publication_calculations=state.get('publication_calculations',[]))
    return digest(payload)


def assert_publication(state,html=None):
    gate=state.get('publication_quality',{})
    if not gate.get('passed') or gate.get('fingerprint')!=publication_fingerprint(state):raise GenerationError('Publication-quality approval is missing or the manuscript changed after approval.')
    if html is not None and gate.get('html_hash')!=digest(html):raise GenerationError('The reviewed HTML changed after the publication-quality gate.')
