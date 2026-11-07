"""Validate generated text/data and assemble private themed HTML/PDF artifacts."""
import base64
from datetime import datetime
from html import escape
import math
import re
from zoneinfo import ZoneInfo
from .generation_models import GenerationError


def chapter(value):
    if not isinstance(value,dict) or not isinstance(value.get('title'),str) or not value['title'].strip() or not isinstance(value.get('paragraphs'),list) or not value['paragraphs'] or any(not isinstance(p,str) for p in value['paragraphs']):raise GenerationError('The model returned invalid chapter text.')
    if sum(len(p) for p in value['paragraphs'])>150000:raise GenerationError('Chapter output exceeds its text budget.')
    if not isinstance(value.get('charts',[]),list):raise GenerationError('Invalid structured chart data.')
    return value


def chart_svg(chart,config,sources):
    """No model-drawn graphics. Every plotted number must have a source excerpt."""
    if not isinstance(chart,dict) or chart.get('kind') not in ('bar','line'):raise ValueError('Unsupported chart type')
    labels=chart.get('labels');values=chart.get('values');evidence=chart.get('evidence');source=next((s for s in sources if s['id']==chart.get('source_id') and s.get('text')),None)
    if not source or not isinstance(labels,list) or not isinstance(values,list) or not 1<=len(values)<=16 or len(labels)!=len(values) or not isinstance(evidence,list) or len(evidence)!=len(values):raise ValueError('Chart lacks source evidence')
    normalized=lambda text:' '.join(str(text).split()).casefold()
    for number,quote,label in zip(values,evidence,labels):
        if type(number) not in (int,float) or not math.isfinite(number) or not isinstance(label,str) or not isinstance(quote,str) or not quote.strip() or normalized(quote) not in normalized(source['text']):raise ValueError('Unverifiable chart data')
        numbers=[float(n.replace(',','')) for n in re.findall(r'-?\d[\d,]*(?:\.\d+)?',quote)]
        if not any(math.isclose(number,n,rel_tol=1e-7,abs_tol=1e-7) for n in numbers):raise ValueError('Chart number does not match the quoted evidence')
    e=lambda text:escape(str(text),quote=True)
    low=min(0,min(values));high=max(0,max(values));span=high-low or 1
    y=lambda value:260-(value-low)/span*205
    step=590/len(values);points=[]
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 370" role="img" aria-label="'+e(chart.get('title','Chart'))+'"><rect width="720" height="370" fill="white"/><text x="45" y="25" font-size="17" fill="'+config['color']+'">'+e(chart.get('title','Chart'))+'</text>'
    for i,(label,number) in enumerate(zip(labels,values)):
        x=65+(i+.5)*step;points.append((x,y(number)))
        if chart['kind']=='bar':svg+='<rect x="'+str(x-step*.32)+'" y="'+str(min(y(0),y(number)))+'" width="'+str(step*.64)+'" height="'+str(max(1,abs(y(number)-y(0))))+'" fill="'+config['color']+'"/>'
        svg+='<text x="'+str(x)+'" y="'+str(y(number)-7)+'" font-size="11" text-anchor="middle">'+e(number)+'</text><text transform="translate('+str(x)+',284) rotate(25)" font-size="10">'+e(label)+'</text>'
    if chart['kind']=='line':svg+='<polyline points="'+' '.join(str(x)+','+str(yv) for x,yv in points)+'" fill="none" stroke="'+config['color']+'" stroke-width="3"/>'+''.join('<circle cx="'+str(x)+'" cy="'+str(yv)+'" r="4" fill="'+config['accent']+'"/>' for x,yv in points)
    svg+='<text x="45" y="355" font-size="11">'+e(chart.get('unit',''))+' · Source ['+e(source['id'])+']</text></svg>'
    return svg


def assemble(config,state):
    e=lambda text:escape(str(text),quote=True)
    sources=state['sources'];allowed={s['id'] for s in sources}
    def paragraph(text):
        encoded=e(text)
        return re.sub(r'\[([A-Z]\d+)\]',lambda m:'<a href="#source-'+m[1]+'">'+m[0]+'</a>' if m[1] in allowed else m[0],encoded)
    title=config['title'] or state.get('outline',{}).get('title') or 'Research report'
    company=config['company'] or 'Independent research';credits=config['credits'] or 'AI-assisted research draft'
    date=config['release_date'] or datetime.now(ZoneInfo('America/Vancouver')).date().isoformat()
    logo='<img class="logo" src="'+config['logo']+'" alt="'+e(company)+' logo">' if config['logo'] else ''
    notes='<section id="editorial-notes" class="appendix editorial-notes"><p class="eyebrow">Appendix · editorial transparency</p><h2>Source and editorial notes</h2><p class="small">Prepared with AI assistance. Review facts, quotations and recommendations before distribution. Source availability and editorial limitations are recorded below.</p>'+('<ul>'+''.join('<li>'+e(warning)+'</li>' for warning in state.get('warnings',[]))+'</ul>' if state.get('warnings') else '<p>No source-collection or automated editorial warnings were recorded.</p>')+'</section>'
    team=next((team for team in config.get('teams',[]) if team['id']==config.get('prepared_team')),None)
    email=team.get('email','') if team else ''
    website=config.get('website','')
    prepared=('<p class="prepared-by"><strong>Prepared by</strong><br>'+e(team['name'])+('<br><a href="mailto:'+e(email)+'">'+e(email)+'</a>' if email else '')+'</p>') if team else ''
    company_link='<p><a href="'+e(website)+'">'+e(website)+'</a></p>' if website else ''
    cover='<div class="cover-brand">'+logo+'<p class="cover-company">'+e(company)+'</p></div><div class="cover-body"><p class="eyebrow">'+e(config['report_type'])+'</p><h1>'+e(title)+'</h1><span class="cover-rule"></span></div><div class="cover-details"><dl class="cover-meta"><div><dt>Release date</dt><dd>'+e(date)+'</dd></div><div><dt>Document version</dt><dd>'+e(config['version'] or '1.0')+'</dd></div></dl><p class="cover-credits">Created by '+e(credits)+'</p>'+prepared+'<div class="cover-website">'+company_link+'</div></div>'
    toc='<nav class="contents" aria-label="Table of contents"><p class="eyebrow">In this document</p><h2>Contents</h2><ol>'+''.join('<li><a href="#chapter-'+str(i)+'">'+e(ch['title'])+'</a></li>' for i,ch in enumerate(state['document']['chapters']))+'<li><a href="#sources">Sources</a></li><li><a href="#editorial-notes">Source and editorial notes</a></li><li><a href="#document-control">Document control and revision history</a></li></ol></nav>' if config['toc'] else ''
    body=''
    for i,ch in enumerate(state['document']['chapters']):
        body+='<section class="report-chapter section-wrap" id="chapter-'+str(i)+'"><p class="eyebrow">Chapter '+str(i+1).zfill(2)+'</p><h2 class="section">'+e(ch['title'])+'</h2>'+''.join('<p>'+paragraph(p)+'</p>' for p in ch['paragraphs'])
        if config['graphics'] and isinstance(ch.get('takeaway'),str):body+='<aside class="callout info"><strong class="ico">Key takeaway</strong><div class="body"><p>'+paragraph(ch['takeaway'])+'</p></div></aside>'
        for chart in state.get('charts',[]):
            if chart['chapter']==i:body+='<figure>'+chart['svg']+'<figcaption>'+e(chart['caption'])+'</figcaption></figure>'
        if config['images'] and i<len(config['illustrations']):body+='<figure><img src="'+config['illustrations'][i]+'" alt="Supporting image '+str(i+1)+'"></figure>'
        body+='</section>'
    body+='<section id="sources" class="appendix"><p class="eyebrow">Reference register</p><h2>Sources</h2><ol class="sources-list">'+''.join('<li id="source-'+e(s['id'])+'"><strong>['+e(s['id'])+']</strong> '+e(s['label'])+(' · <a rel="noopener noreferrer" href="'+e(s['url'])+'">'+e(s['url'])+'</a>' if s.get('url','').startswith(('https://','http://')) else '')+(' · '+e(s['warning']) if s.get('warning') else '')+'</li>' for s in sources)+'</ol></section>'+notes
    history=state.get('revision_history') or [{'version':config.get('version') or '1.0','date':date,'prepared_by':team['name'] if team else credits,'summary':'Initial issue.'}]
    body+='<section id="document-control" class="document-control"><p class="eyebrow">Document governance</p><h2>Document control and revision history</h2><dl class="document-register"><dt>Document title</dt><dd>'+e(title)+'</dd><dt>Issuing organization</dt><dd>'+e(company)+'</dd><dt>Current version</dt><dd>'+e(config['version'] or '1.0')+'</dd><dt>Release date</dt><dd>'+e(date)+'</dd></dl><div class="revision-table-wrap"><table class="revision-table"><caption>Record of document revisions</caption><thead><tr><th scope="col">Version</th><th scope="col">Revision date</th><th scope="col">Prepared by</th><th scope="col">Change summary</th></tr></thead><tbody>'+''.join('<tr><td data-label="Version">'+e(item['version'])+'</td><td data-label="Revision date">'+e(item['date'])+'</td><td data-label="Prepared by">'+e(item['prepared_by'])+'</td><td data-label="Change summary">'+e(item['summary'])+'</td></tr>' for item in history)+'</tbody></table></div><p class="small">This record identifies the document issue and its revisions. A generated revision does not imply independent verification or formal approval.</p></section>'
    if team or website:
        body+='<section id="document-contact" class="document-contact"><h2>Document enquiries</h2><p>For questions regarding this document, please contact:</p><p><strong>'+(e(team['name']) if team else e(company))+'</strong></p>'+('<p><a href="mailto:'+e(email)+'">'+e(email)+'</a></p>' if email else '')+company_link+'</section>'
    from .generation_layout import REPORT_CSS
    css=REPORT_CSS
    running='<div class="running-header">'+e(company)+' · '+e(config['report_type'])+'</div><div class="running-footer">Version '+e(config['version'] or '1.0')+' · '+e(date)+'</div>'
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+e(title)+'</title><style>:root{--theme:'+config['color']+';--accent:'+config['accent']+'}'+css+'</style></head><body data-theme="report" data-document-engine="folio">'+running+'<main><header class="cover">'+cover+'</header>'+toc+body+'<footer>'+e(company)+' · '+e(credits)+' · v'+e(config['version'] or '1.0')+'</footer></main></body></html>'


def export_pdf(html,path):
    from weasyprint import HTML
    from weasyprint.urls import default_url_fetcher
    def fetch(url,*args,**kwargs):
        if not url.startswith('data:image/'):raise ValueError('PDF assets must be embedded images')
        return default_url_fetcher(url,*args,**kwargs)
    temporary=path.with_suffix('.tmp.pdf');HTML(string=html,url_fetcher=fetch).write_pdf(temporary);temporary.replace(path)
