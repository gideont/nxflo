"""Typed chapter boundaries and source-bound diagnostics for targeted repairs."""
from copy import deepcopy
import re
from .generation_document import chapter
from .generation_errors import GenerationError
from .generation_finance import FORMULAS
from .generation_intent import locate,tokens
from .generation_quality import local_publication_issues

# The equation symbol and its registry ID refer to exactly the same formula.
# Never guess the meaning of arbitrary model-provided formula names.
FORMULA_ALIASES={'net_cash_flow':'cash_flow'}


def normalize_chapter(value,contract=None,restore=False,assigned_refs=None):
    value=deepcopy(value)
    if not isinstance(value,dict):return value
    refs=value.get('formula_refs')
    if isinstance(refs,list):value['formula_refs']=[FORMULA_ALIASES.get(ref,ref) if isinstance(ref,str) else ref for ref in refs]
    paragraphs=value.get('paragraphs')
    if isinstance(paragraphs,list) and all(isinstance(p,str) for p in paragraphs):
        anchors={item['id']:item for item in contract['items']} if contract else {}
        entries=value.get('coverage',[]) if isinstance(value.get('coverage'),list) else []
        for proof in entries:
            if not isinstance(proof,dict):continue
            anchor=anchors.get(proof.get('author_ref'))
            if not anchor:continue
            original=re.sub(r'(?m)^>\s?','',anchor['quote']).replace('**','').replace('__','').strip()
            # Bind intent to an actual occurrence of the original statement,
            # without inventing a quotation or relying on a guessed index.
            variants=[original,re.sub(r'\s+[—–]\s+([A-Z][A-Z&]{1,12})\s+[—–]\s*',r', or \1, ',original),re.sub(r'\s+[—–]\s+([A-Z][A-Z&]{1,12})\s+[—–]\s*',r' (\1) ',original)]
            if original.startswith('But '):variants.append(original[4:])
            matches=[i for i,p in enumerate(paragraphs) if any(locate(quote,p) for quote in variants)]
            if len(matches)==1:
                proof.pop('paragraph_index',None);proof['text_excerpt']=paragraphs[matches[0]]
            elif proof.get('paragraph_index')==len(paragraphs) and type(proof.get('paragraph_index')) is int:
                meaningful=tokens(anchor['quote']+' '+anchor['label'])
                if len(tokens(paragraphs[-1])&meaningful)>=min(2,len(meaningful)):
                    proof['paragraph_index']=len(paragraphs)-1
        # New repair responses use paragraph indices. Bind to actual returned
        # prose with strict bounds; never clamp a bad index or accept summaries.
        for field,target in (('coverage','text_excerpt'),('claims','text')):
            entries=value.get(field)
            if not isinstance(entries,list):continue
            for entry in entries:
                if not isinstance(entry,dict) or 'paragraph_index' not in entry:continue
                index=entry.pop('paragraph_index')
                if type(index) is int and 0<=index<len(paragraphs):entry[target]=paragraphs[index]
                else:entry.pop(target,None)
        for proof in value.get('coverage',[]) if isinstance(value.get('coverage'),list) else []:
            if not isinstance(proof,dict):continue
            quote=proof.get('text_excerpt')
            if not isinstance(quote,str):continue
            for paragraph in paragraphs:
                span=locate(quote,paragraph)
                if span:
                    proof['text_excerpt']=paragraph[span[0]:span[1]];break
    if restore and contract and contract.get('mode')=='content_preserving_rewrite' and isinstance(paragraphs,list) and all(isinstance(p,str) for p in paragraphs) and isinstance(value.get('coverage'),list) and isinstance(value.get('claims'),list):
        headings={h['title'].casefold() for h in contract.get('structure',[]) if not h['title'].startswith('Figure')}
        for anchor in contract['items']:
            quote=anchor['quote'].replace('**','').strip()
            # Preserve a missing, author-written closing statement verbatim.
            # Never synthesize factual numbers or append editorial directives.
            if anchor['id'] not in (assigned_refs or []) or anchor['role']!='message' or quote.casefold() not in headings:continue
            if not 20<=len(quote)<=500 or not re.search(r'[.!?]$',quote) or re.search(r'\d|\b(?:create|design|draw|insert|replace|editorial|instructions?|emphasize)\b',quote,re.I):continue
            if not any(locate(quote,p) for p in paragraphs):paragraphs.append(quote)
            for proof in value['coverage']:
                if isinstance(proof,dict) and proof.get('author_ref')==anchor['id']:
                    proof.clear();proof.update(author_ref=anchor['id'],text_excerpt=quote);break
            else:value['coverage'].append({'author_ref':anchor['id'],'text_excerpt':quote})
            claim={'text':quote,'classification':'authorial','source_id':'','quote':''}
            if claim not in value['claims']:value['claims'].append(claim)
    return value


def structure_issues(value):
    try:chapter(value)
    except GenerationError as error:return [str(error)]
    if not isinstance(value.get('takeaway'),str):return ['A structured chapter is missing its takeaway text.']
    errors=[]
    for field in ('section_keys','coverage','claims','tables','charts','formula_refs'):
        if not isinstance(value.get(field),list):errors.append('A structured chapter is missing '+field+'.')
    if errors:return errors
    if any(not isinstance(x,str) for x in value['section_keys']+value['formula_refs']):errors.append('Section and formula references must be strings.')
    if any(not isinstance(x,dict) for field in ('coverage','claims','tables','charts') for x in value[field]):return errors+['Invalid structured chapter content.']
    if any(not isinstance(p.get('author_ref'),str) or not isinstance(p.get('text_excerpt'),str) for p in value['coverage']):errors.append('Invalid author-intent coverage proof.')
    if any(not isinstance(c.get('text'),str) or not isinstance(c.get('source_id'),str) or not isinstance(c.get('quote'),str) for c in value['claims']):errors.append('Invalid factual claim register.')
    for table in value['tables']:
        if not isinstance(table.get('title'),str) or not isinstance(table.get('columns'),list) or any(not isinstance(c,str) for c in table['columns']) or not isinstance(table.get('rows'),list) or any(not isinstance(row,list) or any(not isinstance(cell,str) for cell in row) for row in table['rows']):errors.append('Invalid content table cells.')
        if table.get('classification')=='empirical' and (not isinstance(table.get('evidence'),list) or any(not isinstance(proof,dict) or not isinstance(proof.get('source_id'),str) or not isinstance(proof.get('quote'),str) for proof in table['evidence'])):errors.append('Invalid empirical table evidence.')
    return errors


def chapter_issues(value,plan,state,config):
    errors=structure_issues(value)
    if errors:return errors,False
    unknown=set(value['formula_refs'])-set(FORMULAS)
    if unknown:errors.append('Unknown registered formula reference(s): '+', '.join(sorted(unknown))+'. Use only the registered IDs.')
    # Scope obligations to this chapter while permitting valid repeated anchors.
    known=state['author_contract'];refs=set(plan['author_refs'])|{p['author_ref'] for p in value['coverage']}
    keys=set(plan['section_keys'])
    scoped={**known,'items':[item for item in known['items'] if item['id'] in refs],
            'required_sections':sorted(keys),'structure':[h for h in known['structure'] if h['id'] in keys]}
    if 'narrative_structure' in known:scoped['narrative_structure']=[h for h in known['narrative_structure'] if h['id'] in keys]
    errors.extend(local_publication_issues({'chapters':[value]},scoped,config,state['sources'],[plan],state.get('financials')))
    return sorted({error.replace('Chapter 1','This chapter') for error in errors}),True
