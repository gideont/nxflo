"""Intent-aware graph implementation; legacy jobs continue on their original graph."""
import json
import re
from pathlib import Path
from .generation_errors import GenerationError
from .generation_intent import (MODES,POLICY,source_chunks,extraction_prompt,build_contract,context,
                                instructions,review_instructions,evidence_context,fidelity_issues,digest,validate_contract)
from .generation_document import chapter,chart_svg,assemble
from .generation_finance import build_financials,financial_figures,financial_tables,FORMULAS
from .generation_quality import (provenance_issues,local_publication_issues,criteria,validate_publication_review,
                                publication_fingerprint,assert_publication,manuscript_text)

CHAPTER_INSTRUCTIONS=('Return a structured chapter with title, paragraphs, takeaway, section_keys, coverage, tables, charts, claims and formula_refs. '
 'Coverage entries bind each assigned author_ref to a verbatim text_excerpt from your NEW prose that communicates its meaning. '
 'Discuss the idea substantively, not merely by naming its keywords. Include useful original examples and audience context. '
 'List empirical assertions in claims with exact source quotes and source IDs; authorial proposals use classification authorial. '
 'Tables have title, columns, rows of strings, classification authorial or empirical, and evidence per empirical row. '
 'Empirical charts use the existing exact-quote chart schema. Do not supply hypothetical output numbers as empirical data. '
 'Financial tables, worked projections, formula bodies and figures will be inserted by the deterministic calculator: refer to the supplied results and use formula_refs for registered formulas. '
 'Do not write free-text financial equations. Never insert placeholders, author-facing instructions, instructions to the editor or requests for charts. '
 'No HTML or Markdown in prose. Return only JSON matching the chapter schema.')


class IntentPipeline:
    def __init__(self,engine):self.e=engine;self.config=engine.config;self.models=engine.models

    def run(self,name,state):
        method=getattr(self,name,None)
        return method(state) if method else getattr(self.e,name)(state)

    def collect(self,s):
        result=self.e.collect(s)
        result['sources'][0]['label']='Author’s original brief and intended message'
        result['sources'][0]['role']='author'
        for source in result['sources'][1:]:
            doc=next((doc for i,doc in enumerate(self.config.get('documents',[])) if source['id']=='D'+str(i+1)),None)
            source['role']='author' if doc and doc.get('role','author')=='author' else 'external'
        return result

    def summarize(self,s):
        original=s['author_original']
        if digest(original)!=s['author_source_hash']:raise GenerationError('The original author brief changed after job creation.')
        parts=source_chunks(original)
        extractions=self.models.many('summary',[extraction_prompt(part,self.config['document_intent']) for part in parts],'author-intent')
        if len(extractions)!=len(parts):raise GenerationError('Some parts of the original brief were not analyzed for intent.')
        contract=build_contract({**self.config,'topic':original},parts,extractions)
        # This intermediate checkpoint survives a deployment between author extraction
        # and external-source summarization. Provider results remain durably cached too.
        state={**s,'author_contract':contract}
        self.e.checkpoint(state)
        external=[source for source in s['sources'] if source.get('role')!='author']
        if external:
            notes=self.e.summarize({**s,'sources':external})['notes']
        else:notes=[]
        return {'author_contract':contract,'notes':notes,'intent_audits':[{'stage':'extract','source_hash':contract['source_hash'],'passed':True}]}

    def outline(self,s):
        c=self.config;contract=s['author_contract'];refs=[item['id'] for item in contract['items']]
        prompt=('Plan this document around its original author intent. '+instructions(c)+context(s)+evidence_context(s['sources'])+
                '\nReturn JSON {"title":"...","chapters":[{"title":"...","brief":"...","charts_needed":[],"section_keys":[],"author_refs":[]}]}. '
                'Assign EVERY author anchor to at least one chapter; do not omit any. The opening chapter must communicate the thesis. '
                'Cover these required section keys: '+json.dumps(contract['required_sections'])+'. '
                'Use 2–12 chapters, or the original top-level heading sequence for a content-preserving rewrite. '
                'For that rewrite, retain the original heading titles and order, without the leading heading number. '
                'Author document objectives/questions: '+c.get('questions','')+'; author revision feedback: '+c.get('feedback','')+'. Match length to the content'+(' within approximately '+str(c['pages'])+' body pages' if c['length_mode']=='target' else '')+'. '
                'The original brief is not replaced by these external evidence notes: '+json.dumps(s.get('notes',[])))
        plan=self.models.many('draft',[prompt],'outline')[0];chapters=plan.get('chapters')
        if not isinstance(chapters,list) or not 1<=len(chapters)<=24:raise GenerationError('Invalid intent-aware outline.')
        covered=set();keys=set()
        for ch in chapters:
            if not isinstance(ch,dict) or not isinstance(ch.get('title'),str) or not ch['title'].strip() or not isinstance(ch.get('brief'),str) or not isinstance(ch.get('author_refs'),list) or any(not isinstance(ref,str) for ref in ch['author_refs']) or not set(ch['author_refs'])<=set(refs) or not isinstance(ch.get('section_keys'),list) or any(not isinstance(key,str) for key in ch['section_keys']):raise GenerationError('Outline contains invalid author-intent assignments.')
            covered.update(ch['author_refs']);keys.update(ch['section_keys'])
        if covered!=set(refs) or not set(contract['required_sections'])<=keys:raise GenerationError('The outline omitted original author messages or required sections.')
        thesis={item['id'] for item in contract['items'] if item['role']=='thesis'}
        if not thesis.intersection(chapters[0]['author_refs']):raise GenerationError('The outline does not open on the author\'s thesis.')
        financials=None
        if contract['financial_examples']:
            prompt=('Plan clearly hypothetical WORKED financial examples for this author\'s product. '+instructions(c)+context(s)+
                    '\nReturn financial-plan JSON: groups with unique id, title, kind (youtube, saas or generic), currency, months, assumption_note, participants and conservative/base/optimistic scenarios. '
                    'Use only calculator inputs, never output metrics or invented empirical evidence. Distinguish assumptions supplied by the author from additional illustrative assumptions in assumption_note. '
                    'Include a 12-month YouTube example and a SaaS example when both occur in the original brief; show a 90-day pilot using the first three months. '
                    'Choose genuinely different cases, including a loss-making conservative case and a feasible positive case. '
                    'Initial investment is project startup expenditure; participant cash is financing, never revenue. Include working-capital funding sufficient for the base case. '
                    'Profit shares are explicit illustrative agreements, not inferred from hours or cash. Opportunity-cost hours are non-cash and must not be counted twice. '
                    'Delay YouTube monetization; zero revenue before that month. Define all inputs as editable assumptions, not observations. '
                    'Annual discount rate and all growth/churn/profit shares are fractions, not percentages. No tax, debt, terminal value or depreciation unless a future registered model supports them. '
                    'Common inputs: initial_investment, fixed_monthly_cost, hours_per_month, hourly_opportunity_value, annual_discount_rate. '
                    'YouTube inputs: videos_per_month, views_per_video, monthly_view_growth, rpm, monetization_month, production_cost_per_video, sponsorship_monthly, affiliate_monthly. '
                    'SaaS inputs: initial_customers, new_customers_per_month, monthly_acquisition_growth, churn_rate, monthly_subscription, variable_cost_per_customer. '
                    'Generic inputs: initial_units, monthly_unit_growth, unit_price, variable_cost_per_unit. '
                    'Participants: name, cash_contribution, profit_share. For sample identities use neutral Partner A/B/C, not invented real people.')
            plan_inputs=self.models.many('draft',[prompt],'financial-plan')[0]
            financials=build_financials(plan_inputs)
            for group in financials['groups']:
                results={result['case']:result for result in group['results']}
                if not results['conservative']['net_gain']<=results['base']['net_gain']<=results['optimistic']['net_gain']:raise GenerationError('Scenario names contradict their calculated conservative/base/optimistic outcomes.')
            outcomes=[result['net_gain'] for group in financials['groups'] for result in group['results']]
            if 'both profitable and unprofitable' in s['author_original'].casefold() and not (min(outcomes)<0<max(outcomes)):raise GenerationError('The author requested profitable and unprofitable worked cases; the financial plan omitted one outcome.')
            kinds={group['kind'] for group in financials['groups']};original=s['author_original'].casefold()
            for marker,kind in [('youtube','youtube'),('saas','saas')]:
                if marker in original and kind not in kinds:raise GenerationError('The financial plan omitted the author\'s '+marker+' use case.')
            if any(next(r for r in group['results'] if r['case']=='base')['unallocated_funding_gap']>0 for group in financials['groups']):raise GenerationError('The illustrative base case has an unfunded cash deficit. Its funding assumptions must be explicit and sufficient.')
            if any(group['kind']=='youtube' and next(case for case in group['scenarios'] if case['case']=='base')['inputs']['monetization_month']<2 for group in financials['groups']):raise GenerationError('The YouTube pilot must include an explicit pre-monetization period.')
            if any(group['months']<12 for group in financials['groups']):raise GenerationError('Worked investment examples must include the 12-month forecast and its 90-day pilot.')
        return {'outline':plan,'financials':financials,'intent_audits':s['intent_audits']+[{'stage':'outline','source_hash':contract['source_hash'],'passed':True,'plan_hash':digest(plan)}]}

    def chapter_context(self,s,plan):
        financials=s.get('financials')
        financial_summary=[]
        if financials:
            financial_summary=[{'id':g['id'],'title':g['title'],'assumption_note':g['assumption_note'],'scenarios':g['scenarios'],
                                'results':[{k:v for k,v in r.items() if k not in ('rows','cash_flows')} for r in g['results']]} for g in financials['groups']]
        return (instructions(self.config)+context(s,plan['author_refs'])+evidence_context(s['sources'])+
                '\nVisual planning: When charts are enabled, aim for 1–2 useful charts or graphs per 1–2 pages, where appropriate. Calculator figures are inserted automatically; do not duplicate or fabricate them. Use source-backed empirical figures only. '+
                '\nAuthor document objectives/questions: '+self.config.get('questions','')+'\nAuthor revision feedback: '+self.config.get('feedback','')+
                '\nAssigned chapter plan: '+json.dumps(plan)+
                '\nRegistered formulas (reference their IDs, never replace them): '+json.dumps(FORMULAS)+
                '\nCalculated hypothetical examples and assumptions: '+json.dumps(financial_summary)+
                '\nExternal evidence notes (supporting material, not the author\'s intent): '+json.dumps(s.get('notes',[])))

    def validate_chapters(self,s,chapters,stage,repair=True):
        plans=s['outline']['chapters'];document={'chapters':chapters}
        if len(chapters)!=len(plans):raise GenerationError('A generation stage lost planned chapters.')
        for ch in chapters:
            for field in ('section_keys','coverage','claims','tables','charts','formula_refs'):
                if not isinstance(ch.get(field),list):raise GenerationError('A structured chapter is missing '+field+'.')
            if any(not isinstance(x,str) for x in ch['section_keys']+ch['formula_refs']) or not set(ch['formula_refs'])<=set(FORMULAS):raise GenerationError('A chapter used an unknown registered formula.')
            if any(not isinstance(value,dict) for field in ('coverage','claims','tables','charts') for value in ch[field]):raise GenerationError('Invalid structured chapter content.')
            if any(not isinstance(proof.get('author_ref'),str) or not isinstance(proof.get('text_excerpt'),str) for proof in ch['coverage']):raise GenerationError('Invalid author-intent coverage proof.')
            if any(not isinstance(claim.get('text'),str) or not isinstance(claim.get('source_id'),str) or not isinstance(claim.get('quote'),str) for claim in ch['claims']):raise GenerationError('Invalid factual claim register.')
        errors=local_publication_issues(document,s['author_contract'],self.config,s['sources'],plans,s.get('financials'))
        if errors and repair:
            prompts=[]
            for ch,plan in zip(chapters,plans):
                prompts.append('Repair the manuscript against the original author contract, not into a different genre. '+self.chapter_context(s,plan)+
                               '\nWhole-document fidelity/provenance issues: '+json.dumps(errors)+'\nCurrent chapter: '+json.dumps(ch)+'\n'+CHAPTER_INSTRUCTIONS)
            chapters=[chapter(ch) for ch in self.models.many('draft',prompts,'intent-repair-'+stage)]
            return self.validate_chapters(s,chapters,stage,False)
        if errors:
            self.e.checkpoint({**s,'blocked_candidate':document,'quality_errors':errors})
            raise GenerationError('Intent/provenance gate rejected '+stage+': '+' '.join(errors[:8]))
        return {'document':document,'intent_audits':s['intent_audits']+[{'stage':stage,'source_hash':s['author_contract']['source_hash'],'manuscript_hash':digest(document),'passed':True}]}

    def draft(self,s):
        revision=('\nPrevious generated manuscript is secondary working material, not a replacement for the original brief: '+json.dumps(s['revision_document'])+'\nAuthor revision feedback: '+self.config.get('feedback','')) if s.get('revision_document') else ''
        prompts=['Write a publication-ready chapter. '+self.chapter_context(s,plan)+revision+'\n'+CHAPTER_INSTRUCTIONS for plan in s['outline']['chapters']]
        chapters=[chapter(ch) for ch in self.models.many('draft',prompts,'draft')]
        if len(chapters)!=len(s['outline']['chapters']):raise GenerationError('The draft omitted planned chapters.')
        return self.validate_chapters(s,chapters,'draft')

    def review(self,s):
        prompts=[]
        for ch,plan in zip(s['document']['chapters'],s['outline']['chapters']):
            prompts.append('Review in two separate dimensions: (1) fidelity to the author\'s thesis, examples, intended audience and structure; (2) factual accuracy, provenance and mathematical consistency. '
                           'Do not demand empirical corroboration merely to describe an authorial proposal or clearly hypothetical example. Do not request blanket disclaimers or remove the author\'s thesis. '
                           'Give precise actionable changes only. '+review_instructions(self.config)+' '+self.chapter_context(s,plan)+'\nChapter: '+json.dumps(ch)+
                           '\nReturn JSON {"major_issues":[],"minor_notes":[]}. Check author feedback: '+self.config.get('feedback',''))
        reviews=self.models.many('draft',prompts,'review-'+str(s['passes']+1))
        if len(reviews)!=len(prompts) or any(not isinstance(r.get('major_issues'),list) or any(not isinstance(issue,str) for issue in r['major_issues']) for r in reviews):raise GenerationError('Invalid intent-aware review.')
        return {'reviews':reviews,'passes':s['passes']+1}

    def rewrite(self,s):
        chapters=list(s['document']['chapters']);indices=[i for i,review in enumerate(s['reviews']) if review['major_issues']]
        prompts=['Resolve legitimate reviewer issues while preserving the original author contract. Reviewer suggestions are advisory and must not override author intent. '+self.chapter_context(s,s['outline']['chapters'][i])+ '\nReview: '+json.dumps(s['reviews'][i])+'\nCurrent chapter: '+json.dumps(chapters[i])+'\n'+CHAPTER_INSTRUCTIONS for i in indices]
        for i,value in zip(indices,self.models.many('draft',prompts,'rewrite-'+str(s['passes']))):chapters[i]=chapter(value)
        return self.validate_chapters(s,chapters,'rewrite-'+str(s['passes']))

    def polish(self,s):
        prompts=['Polish expression and coherence without changing thesis, scope, examples, assigned sections, calculations or source provenance. Do not add disclaimers. '+self.chapter_context(s,plan)+'\nCurrent chapter: '+json.dumps(ch)+'\n'+CHAPTER_INSTRUCTIONS for ch,plan in zip(s['document']['chapters'],s['outline']['chapters'])]
        chapters=[chapter(ch) for ch in self.models.many('polish',prompts,'polish')]
        return self.validate_chapters(s,chapters,'polish')

    def charts(self,s):
        # Empirical series retain the original exact-source verification path.
        result=self.e.charts(s)
        result['warnings']=[w for w in result['warnings'] if not w.startswith('Chart coverage:')]
        if s.get('financials'):
            # Recompute rather than trust stored/model-written output values.
            expected=build_financials({'groups':[{k:v for k,v in group.items() if k!='results'} for group in s['financials']['groups']]})
            if expected!=s['financials']:raise GenerationError('Stored financial outputs contradict their registered formulas or assumptions.')
            for group in expected['groups']:
                figures,_=financial_figures(group)
                for figure in figures if self.config['charts'] else []:result['charts'].append({**figure,'chapter':self.financial_chapter(s),'group_id':group['id']})
            result['warnings']=[w for w in result['warnings'] if not w.startswith('Chart coverage:')]
        return result

    def financial_chapter(self,s):
        return next((i for i,plan in enumerate(s['outline']['chapters']) if 'financial_projections' in plan['section_keys']),len(s['outline']['chapters'])-1)

    def assemble(self,s):
        errors=local_publication_issues(s['document'],s['author_contract'],self.config,s['sources'],s['outline']['chapters'],s.get('financials'))
        if s['author_contract']['financial_examples'] and not s.get('financials'):errors.append('Required worked financial projections are missing.')
        if errors:
            self.e.checkpoint({**s,'quality_errors':errors})
            raise GenerationError('Publication-quality gate rejected the manuscript: '+' '.join(errors[:8]))
        all_criteria=criteria(s['author_contract'])
        prompts=[]
        for offset in range(0,len(all_criteria),24):
            requested=all_criteria[offset:offset+24]
            prompt=('Independently assess this manuscript for publication. '+instructions(self.config)+context(s)+evidence_context(s['sources'])+
                '\nEvaluate each required criterion exactly once: '+json.dumps(requested)+
                '\nFor each author:A reference, check that its actual meaning, examples, distinctions and constraints survive, not just its keywords. '
                'For each section key check substantive content, not a heading alone. Accuracy: all empirical claims and numeric tables/charts need matching source evidence; inspect for unregistered claims as well. '
                'Formulas: ensure the prose is consistent with the calculator, no double-counted costs, cash financing is not revenue, opportunity costs are separate, and projections are explicitly hypothetical rather than guaranteed or observed. '
                'Purpose: the document must communicate this author\'s intended message in the selected genre; reject an academic cautionary report substituted for a product concept. '
                'Publication: reject unfinished placeholders, leaked editorial instructions, missing worked examples or substantive drift. Do not require repetitive disclaimers. '
                'Return JSON {"checks":[{"criterion":"exact criterion ID","passed":true,"evidence":"verbatim substantive passage from the manuscript","reason":"assessment"}]}. '
                '\nManuscript: '+json.dumps(s['document'])+'\nCalculated hypothetical models: '+json.dumps(s.get('financials')))
            if len(prompt)>300000:raise GenerationError('The manuscript exceeds the publication-review context budget. Split it into smaller documents.')
            prompts.append(prompt)
        reviews=self.models.many('polish',prompts,'publication-quality')
        if any(not isinstance(result,dict) or not isinstance(result.get('checks'),list) for result in reviews):raise GenerationError('Malformed publication review response.')
        review={'checks':[check for result in reviews for check in result['checks']]}
        failures=validate_publication_review(review,s['document'],s['author_contract'])
        if failures:
            self.e.checkpoint({**s,'quality_errors':failures,'publication_review':review})
            raise GenerationError('Publication-quality gate rejected the manuscript: '+' '.join(failures[:8]))
        gate={'passed':True,'fingerprint':publication_fingerprint(s),'checks':review['checks']}
        html=assemble(self.config,{**s,'publication_quality':gate})
        gate['html_hash']=digest(html)
        self.e.directory.mkdir(parents=True,exist_ok=True)
        temporary=self.e.directory/'document.tmp.html';temporary.write_text(html);temporary.replace(self.e.directory/'document.html')
        (self.e.directory/'sources.json').write_text(json.dumps(s['sources'],ensure_ascii=False))
        return {'publication_quality':gate,'quality_errors':[],'intent_audits':s['intent_audits']+[{'stage':'publication','passed':True,'manuscript_hash':digest(s['document'])}]}

    def html_review(self,s):
        assert_publication(s,(self.e.directory/'document.html').read_text())
        return self.e.html_review(s)

    def pdf(self,s):
        assert_publication(s,(self.e.directory/'document.html').read_text())
        return self.e.pdf(s)
