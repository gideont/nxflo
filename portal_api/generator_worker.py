"""Single durable LangGraph worker for real private document generation."""
import fcntl
import json
import os
from pathlib import Path
import re
import time
from . import db
from .generator_sources import extract_sources
from .generation_models import Models,GenerationError,PendingBatch,Cancelled
from .generation_sources import fetch_reference,transcript
from .generation_document import chapter,chart_svg,assemble,export_pdf
from .generation_tasks import monitored_call
from .generation_recovery import recover_failure
from . import generation_shutdown as shutdown

STEPS=['collect','summarize','outline','draft','review','rewrite','polish','charts','assemble','html_review','pdf','deliver']
CHAPTER_SCHEMA='Return JSON {"title":"...","paragraphs":["plain text paragraphs with [B1], [D1] or [R1] source citations"],"takeaway":"...","charts":[{"kind":"bar or line","title":"...","labels":["..."],"values":[1.0],"unit":"...","source_id":"B1","evidence":["exact source excerpt containing the corresponding number"]}]}. No HTML or Markdown. Use charts only when requested and supported by exact numerical source evidence. Never invent chart values.'


def chart_guidance(config):
    if not config['charts']:
        return 'Charts are disabled. Return an empty charts array; do not propose charts.'
    return ('Aim for 1–2 useful charts or graphs per 1–2 pages of body content '
            '(approximately 450–900 words). Plan distinct comparisons, trends or distributions '
            'where numerical source evidence supports them. Include exact source excerpts for '
            'every plotted value. Preserve valid charts through review and polishing. '
            'Never invent values, fill a visual quota, or present assumptions as measured results. '
            'When evidence is insufficient, explain the limitation instead.')


def chart_evidence(config, sources):
    """Bounded exact excerpts let the writer satisfy the chart verifier."""
    if not config['charts']:
        return ''
    evidence=[];remaining=8000
    for source in sources:
        excerpts=[];text=source.get('text','');covered=0
        for match in re.finditer(r'\d[\d,.]*',text):
            if match.start()<covered:continue
            covered=min(len(text),match.end()+250)
            quote=text[max(0,match.start()-100):covered].strip()
            if not quote or len(quote)>remaining:continue
            excerpts.append(quote);remaining-=len(quote)
            if len(excerpts)>=6 or remaining<100:break
        if excerpts:evidence.append({'source_id':source['id'],'exact_excerpts':excerpts})
        if remaining<100:break
    return '\nOriginal numerical source excerpts for charts (use only relevant supported values): '+json.dumps(evidence)


class HTMLReviewPaused(Exception):
    """The saved HTML needs explicit approval before PDF export."""


class Engine:
    def __init__(self,path,job_id,model_factory=Models):
        self.db=db.connect(path);self.id=job_id
        row=self.db.execute('SELECT * FROM generator_jobs WHERE id=?',(job_id,)).fetchone()
        from .generator import DEFAULTS
        self.config={**DEFAULTS,**json.loads(row['config'])};self.events=json.loads(row['events']);self.state=json.loads(row['state']);self.state['config']=self.config
        self.config['_pipeline_version']=self.state.get('pipeline_version',1)
        self.config['_prompt_policy_version']=self.state.get('prompt_policy_version',1)
        parent=self.config.get('revision_parent') or row['parent_id']
        previous=self.db.execute('SELECT state FROM generator_jobs WHERE id=?',(parent,)).fetchone() if parent else None
        self.previous=json.loads(previous['state']) if previous else None
        self.directory=Path(path).parent/'generated'/job_id
        self.models=model_factory(self.db,job_id,self.config,self.message)
    def heartbeat(self):self.db.execute("INSERT INTO generator_meta VALUES('heartbeat',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(time.time()),))
    def message(self,text):
        self.models.check();self.heartbeat()
        self.db.execute('UPDATE generator_jobs SET message=?,updated_at=? WHERE id=?',(text,db.now(),self.id))
    def checkpoint(self,state,status='running'):
        self.models.check();self.heartbeat();self.state=state
        saved={key:value for key,value in state.items() if key!='config'}
        self.db.execute('UPDATE generator_jobs SET state=?,events=?,status=?,updated_at=? WHERE id=?',(json.dumps(saved,ensure_ascii=False),json.dumps(self.events),status,db.now(),self.id))
    def source_progress(self,total,completed):
        self.db.execute('UPDATE generator_jobs SET work_progress=? WHERE id=?',(json.dumps({'step':'collect','stage':'collect','completed':completed,'total':total,'unit':'source checks'}),self.id))
    def collect(self,s):
        c=self.config;links=extract_sources(c['topic'],c['youtube']);warnings=[]
        sources=[{'id':'B1','label':'User-provided brief and research (not independently verified)','text':c['topic']}]
        sources +=[{'id':'D'+str(i+1),'label':doc['name']+' (uploaded source)','text':doc['text']} for i,doc in enumerate(c['documents'])]
        budget=sum(len(source['text']) for source in sources);urls=list(links['references']);seen=set(urls);collected=0
        legacy_web=c['web_search'] and s.get('research_policy',1)<2
        web_step=1 if legacy_web and c.get('web_budget_usd',0.30)>0 else 0
        self.source_progress(max(1,len(urls)+len(links['youtube'])+web_step),0)
        if legacy_web and c.get('web_budget_usd',0.30)>0:
            try:
                self.message('Budgeted research: one Parallel Turbo search with Luna Flex notes; US$'+str(c.get('web_budget_usd',0.30))+' maximum.')
                research=self.models.many('summary',['Research this topic and return verifiable facts, dates and source links. Topic: '+(c['title'] or c['topic'][:5000])+'\nResearch questions: '+c['questions']],'web-research',structured=False,web=True)[0]
                citations=[a.get('url_citation',{}).get('url','') for a in research.get('annotations',[]) if a.get('type')=='url_citation']
                if not citations:warnings.append('Web search returned no citations. The document needs manual source review.')
                else:
                    sources.append({'id':'W1','label':'AI-assisted web-search notes; verify against the linked primary sources','text':research['content'],'url':citations[0]})
                    for url in citations:
                        if url.startswith(('https://','http://')) and url not in seen:urls.append(url);seen.add(url)
            except GenerationError as error:
                warnings.append('Optional web research was unavailable. '+str(error)+' The document uses the supplied brief, uploads and available reference links; review its source coverage.')
                self.message('Web research unavailable; continuing with your supplied research and reference links.')
        if web_step:collected+=1
        self.source_progress(max(1,len(urls)+len(links['youtube'])+web_step),collected)
        for i,url in enumerate(links['youtube']):
            shutdown.checkpoint()
            self.models.check();source={'id':'Y'+str(i+1),'label':'YouTube transcript','url':url,'text':''}
            try:
                if i>=50 or budget>=8000000:raise GenerationError('Collection budget reached; upload selected transcript excerpts.')
                self.message('Collecting YouTube transcript '+str(i+1)+' of '+str(len(links['youtube']))+'.')
                text=monitored_call(self.db,self.id,'YouTube transcript '+str(i+1)+' of '+str(len(links['youtube'])),60,transcript,(url,),check=self.models.check,message=self.message)
                if budget+len(text)>8000000:raise GenerationError('Collection budget reached; upload selected transcript excerpts.')
                source['text']=text;budget+=len(text)
            except GenerationError as error:source['warning']=str(error);warnings.append('YouTube source '+source['id']+': '+str(error))
            sources.append(source)
            collected+=1;self.source_progress(max(1,len(urls)+len(links['youtube'])+web_step),collected)
        for i,url in enumerate(urls):
            shutdown.checkpoint()
            self.models.check();source={'id':'R'+str(i+1),'label':'Reference '+str(i+1),'url':url,'text':''}
            try:
                if i>=200 or budget>=8000000:raise GenerationError('Collection budget reached; upload selected reference excerpts.')
                self.message('Extracting reference '+str(i+1)+' of '+str(len(urls))+'.')
                text,final_url=monitored_call(self.db,self.id,'reference '+str(i+1)+' of '+str(len(urls)),45,fetch_reference,(url,),check=self.models.check,message=self.message)
                if budget+len(text)>8000000:raise GenerationError('Collection budget reached; upload selected reference excerpts.')
                source.update(text=text,url=final_url);budget+=len(text)
            except GenerationError as error:source['warning']=str(error);warnings.append('Reference '+source['id']+': '+str(error))
            sources.append(source)
            collected+=1;self.source_progress(max(1,len(urls)+len(links['youtube'])+web_step),collected)
        if not collected:self.source_progress(1,1)
        # Keep all original source URLs; report every unavailable source in the manifest.
        update={'sources':sources,'warnings':list(dict.fromkeys(warnings)),'passes':0}
        if self.previous:
            previous=json.loads(json.dumps(self.previous['document']));mapping={};next_id=1
            for old in self.previous.get('sources',[]):
                current=next((source for source in sources if old.get('url') and source.get('url')==old['url'] or not old.get('url') and source['label']==old['label']),None)
                if current:mapping[old['id']]=current['id'];continue
                if budget+len(old.get('text',''))>8000000:raise GenerationError('Combined revision evidence exceeds the source budget. Reduce source material before revising.')
                while any(source['id']=='P'+str(next_id) for source in sources):next_id+=1
                kept={**old,'id':'P'+str(next_id)};sources.append(kept);budget+=len(kept.get('text',''));mapping[old['id']]=kept['id'];next_id+=1
            def remap(text):return re.sub(r'\[([A-Z]\d+)\]',lambda m:'['+mapping.get(m[1],m[1])+']',text)
            for ch in previous['chapters']:
                ch['paragraphs']=[remap(text) for text in ch['paragraphs']]
                if isinstance(ch.get('takeaway'),str):ch['takeaway']=remap(ch['takeaway'])
                for chart in ch.get('charts',[]):
                    if isinstance(chart,dict):chart['source_id']=mapping.get(chart.get('source_id'),chart.get('source_id'))
            update['revision_document']=previous
        return update
    def summarize(self,s):
        prompts=[]
        for source in s['sources']:
            text=source.get('text','')
            for i in range(0,len(text),24000):
                prompts.append('Summarize this source excerpt into evidence notes, ideally 1000 characters. Keep source IDs, exact figures, short exact quotes, dates and limitations. Do not promote user-supplied claims to verified facts. Return JSON {"notes":"..."}. Source '+source['id']+' ('+source['label']+'), part '+str(i//24000+1)+':\n'+text[i:i+24000])
        notes=self.models.many('summary',prompts,'summarize')
        for item in notes:
            if not isinstance(item.get('notes'),str) or not item['notes'].strip() or len(item['notes'])>6000:raise GenerationError('Invalid evidence summary returned by the model.')
        level=0
        while len(json.dumps(notes))>160000:
            groups=[notes[i:i+20] for i in range(0,len(notes),20)]
            prompts=['Consolidate these evidence notes into at most 2500 characters. Preserve source IDs, numbers, direct quotes and uncertainties. JSON {"notes":"..."}.\n'+json.dumps(group) for group in groups]
            newer=self.models.many('summary',prompts,'consolidate-'+str(level))
            if any(not isinstance(item.get('notes'),str) or len(item['notes'])>12000 for item in newer):raise GenerationError('Invalid consolidated notes.')
            if len(json.dumps(newer))>=len(json.dumps(notes)):raise GenerationError('Source notes could not be condensed safely. Reduce the source material.')
            notes=newer;level+=1
        return {'notes':notes}
    def outline(self,s):
        c=self.config
        count=max(2,min(12,(c['pages']+2)//3)) if c['length_mode']=='target' else None
        revision=('\nThis is an editorial revision of an existing document. Preserve its useful structure and content unless the feedback asks for changes. Previous chapter titles: '+json.dumps([ch['title'] for ch in s['revision_document']['chapters']])+'\nUser review feedback (editorial instructions, not verified evidence): '+self.config.get('feedback','')) if s.get('revision_document') else ''
        prompt='Create a useful chapter outline for a '+c['report_type']+' titled '+c['title']+'. Target '+(str(c['pages'])+' approximate A4 pages' if c['length_mode']=='target' else 'a natural length based on evidence, without padding')+'. Research questions: '+c['questions']+'\nReturn JSON {"title":"...","chapters":[{"title":"...","brief":"...","charts_needed":["..."]}]}, '+('exactly '+str(count)+' chapters' if count else '2–12 chapters')+'. '+chart_guidance(c)+'. Evidence notes:\n'+json.dumps(s['notes'])+revision
        result=self.models.many('draft',[prompt],'outline')[0]
        if not isinstance(result.get('chapters'),list) or not 2<=len(result['chapters'])<=12 or count is not None and len(result['chapters'])!=count or any(not isinstance(ch,dict) or not isinstance(ch.get('title'),str) for ch in result['chapters']):raise GenerationError('Invalid chapter outline.')
        return {'outline':result}
    def draft(self,s):
        c=self.config;count=len(s['outline']['chapters']);words=max(100,int(c['pages']*450/count)) if c['length_mode']=='target' else 650
        revision=('\nRevise the existing document rather than replacing it with unrelated new writing. Apply this editorial feedback where relevant: '+c.get('feedback','')+'\nPrevious manuscript with source IDs mapped to the supplied evidence: '+json.dumps(s['revision_document'])) if s.get('revision_document') else ''
        prompts=['Write a complete chapter, approximately '+str(words)+' words, for this '+c['report_type']+'. Chapter plan: '+json.dumps(plan)+'\n'+chart_guidance(c)+'\n'+CHAPTER_SCHEMA+'\nEvidence: '+json.dumps(s['notes'])+chart_evidence(c,s['sources'])+revision for plan in s['outline']['chapters']]
        return {'document':{'chapters':[chapter(ch) for ch in self.models.many('draft',prompts,'draft')]}}
    def review(self,s):
        prompts=['Review this chapter for unsupported figures, gaps, weak reasoning, missing citations and practical recommendations. Return JSON {"major_issues":["specific problem and fix"],"minor_notes":["..."]}. Empty major_issues means approved. Evidence: '+json.dumps(s['notes'])+'\nChapter: '+json.dumps(ch)+'\nCheck that applicable editorial feedback was addressed: '+self.config.get('feedback','') for ch in s['document']['chapters']]
        reviews=self.models.many('draft',prompts,'review-'+str(s['passes']+1))
        if any(not isinstance(item.get('major_issues'),list) or any(not isinstance(issue,str) for issue in item['major_issues']) for item in reviews):raise GenerationError('Invalid reviewer response.')
        return {'reviews':reviews,'passes':s['passes']+1}
    def rewrite(self,s):
        chapters=list(s['document']['chapters']);indices=[i for i,item in enumerate(s['reviews']) if item['major_issues']]
        prompts=['Fix every major reviewer issue while preserving supported facts, source IDs and chapters. '+chart_guidance(self.config)+' '+CHAPTER_SCHEMA+'\nReview: '+json.dumps(s['reviews'][i])+'\nEvidence: '+json.dumps(s['notes'])+chart_evidence(self.config,s['sources'])+'\nChapter: '+json.dumps(chapters[i]) for i in indices]
        for i,revised in zip(indices,self.models.many('draft',prompts,'rewrite-'+str(s['passes']))):chapters[i]=chapter(revised)
        warnings=list(s.get('warnings',[]))
        if s['passes']>=self.config['review_passes']:warnings.append('The review budget was reached. The final corrective rewrite requires manual review.')
        return {'document':{'chapters':chapters},'warnings':warnings}
    def polish(self,s):
        prompts=['Polish tone, terminology, consistency and actionable recommendations. Preserve every fact, source citation and chart number. Do not introduce new claims. '+chart_guidance(self.config)+' '+CHAPTER_SCHEMA+'\nChapter: '+json.dumps(ch)+'\nPreserve changes requested in the user editorial feedback: '+self.config.get('feedback','') for ch in s['document']['chapters']]
        chapters=[chapter(ch) for ch in self.models.many('polish',prompts,'polish')]
        available={source['id'] for source in s['sources'] if source.get('text')};warnings=list(s.get('warnings',[]))
        for ch in chapters:
            bad=set(re.findall(r'\[([A-Z]\d+)\]',' '.join(ch['paragraphs'])))-available
            if bad:warnings.append('Manual citation review required for: '+', '.join(sorted(bad))+'.')
        return {'document':{'chapters':chapters},'warnings':list(dict.fromkeys(warnings))}
    def charts(self,s):
        charts=[];warnings=list(s.get('warnings',[]))
        if self.config['charts']:
            for i,ch in enumerate(s['document']['chapters']):
                for data in ch.get('charts',[]):
                    try:charts.append({'chapter':i,'svg':chart_svg(data,self.config,s['sources']),'caption':str(data.get('title','Chart'))+' · Source ['+str(data.get('source_id',''))+']'})
                    except (ValueError,TypeError,KeyError):warnings.append('A proposed chart was omitted because its data could not be verified against exact source excerpts.')
        if self.config['charts']:
            words=sum(len(p.split()) for ch in s['document']['chapters'] for p in ch['paragraphs'])
            minimum=max(1,(words+899)//900)
            if len(charts)<minimum:
                warnings.append('Chart coverage: '+str(len(charts))+' verified charts for approximately '+str(max(1,(words+449)//450))+' body pages. Aim for 1–2 charts or graphs per 1–2 pages where numerical source evidence supports them. More numerical evidence may be needed.')
        return {'charts':charts,'warnings':list(dict.fromkeys(warnings))}
    def assemble(self,s):
        self.directory.mkdir(parents=True,exist_ok=True)
        html=assemble(self.config,s)
        temporary=self.directory/'document.tmp.html';temporary.write_text(html);temporary.replace(self.directory/'document.html')
        (self.directory/'sources.json').write_text(json.dumps(s['sources'],ensure_ascii=False))
        return {}
    def html_review(self,s):
        if not s.get('html_approved'):
            self.message('HTML is ready. Preview the document, then choose Continue to PDF when you are ready.')
            self.checkpoint(s, 'awaiting_html_review')
            raise HTMLReviewPaused()
        return {}
    def pdf(self,s):
        monitored_call(self.db,self.id,'PDF export',120,export_pdf,((self.directory/'document.html').read_text(),self.directory/'document.pdf'),check=self.models.check,message=self.message)
        return {}
    def run(self):
        from langgraph.graph import StateGraph,START,END
        def route(s):return s.get('next_step','collect')
        def next_step(name,s):
            if name=='review':return 'rewrite' if any(item['major_issues'] for item in s['reviews']) else 'polish'
            if name=='rewrite':return 'review' if s['passes']<self.config['review_passes'] else 'polish'
            return STEPS[STEPS.index(name)+1] if name!='deliver' else 'end'
        def node(name):
            def execute(s):
                shutdown.checkpoint()
                self.models.check();self.db.execute('UPDATE generator_jobs SET step=? WHERE id=?',(name,self.id));self.message('Running '+name+(' · pass '+str(s.get('passes',0)+1) if name=='review' else '')+'.')
                self.db.execute("UPDATE generator_jobs SET work_progress='{}' WHERE id=?",(self.id,))
                token=name+':'+str(s.get('passes',0))
                if not any(event.get('token')==token and event['status']=='started' for event in self.events):self.events.append({'step':name,'status':'started','token':token,'at':db.now()})
                self.checkpoint(s)
                if self.state.get('pipeline_version')==2 and name!='deliver':
                    from .generation_v2 import IntentPipeline
                    update=IntentPipeline(self).run(name,s)
                else:update=getattr(self,name)(s) if name!='deliver' else {}
                result={**s,**update};result['next_step']=next_step(name,result)
                self.events.append({'step':name,'status':'complete','token':token,'at':db.now(),'pass':result.get('passes',0)})
                self.checkpoint(result,'needs_review' if name=='deliver' and result.get('warnings') else 'ready' if name=='deliver' else 'running')
                self.db.execute("UPDATE generator_jobs SET recovery='{}' WHERE id=?",(self.id,))
                if name=='deliver':self.message('Document ready'+(' · review the reported source/editorial warnings.' if result.get('warnings') else '.'))
                return result
            return execute
        graph=StateGraph(dict);dest={step:step for step in STEPS};dest['end']=END
        for step in STEPS:graph.add_node(step,node(step))
        graph.add_conditional_edges(START,route,dest)
        for step in STEPS:graph.add_conditional_edges(step,route,dest)
        try:graph.compile().invoke(self.state,{'recursion_limit':60})
        except PendingBatch:self.db.execute("UPDATE generator_jobs SET status='queued',recovery='{}',next_run_at=?,updated_at=? WHERE id=? AND status!='cancelled'",(time.time()+60,db.now(),self.id))
        except shutdown.WorkerDraining:
            self.db.execute("UPDATE generator_jobs SET status='queued',message='Deployment pause: saved progress will resume after the worker restarts.',next_run_at=0,updated_at=? WHERE id=? AND status='running'",(db.now(),self.id))
        except (Cancelled, HTMLReviewPaused):pass
        except Exception as error:
            message=str(error) if isinstance(error,GenerationError) else 'Generation failed during the '+self.db.execute('SELECT step FROM generator_jobs WHERE id=?',(self.id,)).fetchone()[0]+' stage.'
            recover_failure(self.db,self.id,error,message)
            print('Generation job',self.id,'interrupted:',type(error).__name__,flush=True)
        finally:
            self.db.execute("UPDATE generator_jobs SET wait_state='{}' WHERE id=?",(self.id,));self.heartbeat();self.db.close()


def main():
    shutdown.install_handlers()
    path=os.environ.get('BMS_DATABASE_PATH','/data/bms_hub.sqlite3');lock=open(Path(path).parent/'.generator-worker.lock','a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('A generation worker is already running.')
    connection=db.connect(path);connection.execute("UPDATE generator_jobs SET status='queued' WHERE status='running'")
    while not shutdown.requested():
        connection.execute("INSERT INTO generator_meta VALUES('heartbeat',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(time.time()),))
        with db.transaction(connection):
            row=connection.execute("SELECT id FROM generator_jobs WHERE status='queued' AND next_run_at<=? ORDER BY created_at LIMIT 1",(time.time(),)).fetchone()
            if row:connection.execute("UPDATE generator_jobs SET status='running',updated_at=? WHERE id=?",(db.now(),row['id']))
        if row:Engine(path,row['id']).run()
        else:time.sleep(2)
    connection.close()
    lock.close()

if __name__=='__main__':main()
