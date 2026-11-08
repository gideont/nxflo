"""Source-owned publication assets, registered example calculations and review blocks."""
from decimal import Decimal
from html import escape
import json
import re
from .generation_errors import GenerationError
from .generation_finance import svg_plot,MONEY,financial_figures,financial_tables,display
from .generation_calculated_charts import recipes,canonical_financials
from .generation_blocks import render_table
from .generation_quality import criteria

ASSET_CSS='''
.publication-figure{margin:24px 0;break-inside:avoid}.publication-flow{list-style:none;padding:0;display:grid;grid-template-columns:repeat(var(--node-count),minmax(0,1fr));gap:10px}.publication-flow li{position:relative;min-width:0;padding:14px 10px;border:1px solid #cbd8d4;border-radius:8px;background:#f0f5f2;overflow-wrap:anywhere}.publication-flow li:not(:last-child)::after{content:'→';position:absolute;right:-13px;top:18px;color:#315e55}.publication-flow small{display:block;color:#315e55;font-weight:600;margin-bottom:8px}.publication-flow strong{display:block;font-size:13px;line-height:1.4}.publication-flow p{font-size:12px;line-height:1.5;margin:8px 0 0}.publication-branches{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}.publication-branches span{padding:8px 12px;border:1px solid #315e55;border-radius:6px;color:#315e55;font-size:12px}.publication-chart-key{display:flex;flex-wrap:wrap;gap:6px 18px;font:13px/1.5 sans-serif;margin:8px 0}.publication-series-label{display:none}.publication-calculations{margin:24px 0;break-inside:avoid}.publication-calculations p{font-size:14px}
@media screen and (max-width:600px){.publication-figure svg>text{font-size:30px}.publication-figure svg>text:nth-of-type(-n+2){display:none}.publication-flow{grid-template-columns:1fr;gap:20px}.publication-flow li:not(:last-child)::after{content:'↓';top:auto;bottom:-20px;right:50%}.publication-flow strong{font-size:15px}.publication-flow p{font-size:14px}}
'''


def source_sections(state):
    original=state['author_original'];headings=state['author_contract']['structure']
    for i,h in enumerate(headings):
        end=headings[i+1]['start'] if i+1<len(headings) else len(original)
        owner=next((j for j,p in enumerate(state['outline']['chapters']) if h['id'] in p['section_keys']),None)
        if owner is not None:yield h,original[h['end']:end],owner


def automation_calculation(original):
    match=re.search(r'(\d+) hours × \$([\d,.]+) × (\d+) weeks = \$([\d,.]+)',original)
    initial=re.search(r'Implementation cost:\s*\$([\d,.]+)',original)
    monthly=re.search(r'Monthly operating cost:\s*\$([\d,.]+)',original)
    if not match or not initial or not monthly:return None
    dec=lambda v:Decimal(v.replace(',',''))
    hours,rate,weeks,total=map(dec,match.groups());benefit=MONEY(hours*rate*weeks)
    if benefit!=total:raise GenerationError('The authored automation benefit contradicts its inputs.')
    cash=MONEY(dec(initial[1])+12*dec(monthly[1]));net=MONEY(benefit-cash)
    for label,value in (('First-year cash expenditure',cash),('Net modeled economic benefit',net)):
        declared=re.search(re.escape(label)+r':\s*\$([\d,.]+)',original)
        if declared and dec(declared[1])!=value:raise GenerationError('The authored '+label.lower()+' contradicts its formula.')
    return {'id':'automation','title':'Hypothetical automation: economic benefit and cash expenditure','inputs':{'hours_per_week':float(hours),'hourly_value':float(rate),'working_weeks':float(weeks),'implementation_cost':float(dec(initial[1])),'monthly_operating_cost':float(dec(monthly[1]))},
            'outputs':{'annual_economic_benefit':float(benefit),'first_year_cash_expenditure':float(cash),'net_modeled_economic_benefit':float(net),'economic_return_on_cash_expenditure_pct':float(net/cash*100) if cash else None},
            'formulas':{'annual_economic_benefit':'hours_per_week × hourly_value × working_weeks','first_year_cash_expenditure':'implementation_cost + 12 × monthly_operating_cost','net_modeled_economic_benefit':'annual_economic_benefit − first_year_cash_expenditure','economic_return_on_cash_expenditure_pct':'net_modeled_economic_benefit / first_year_cash_expenditure × 100'},
            'note':'Time released is modeled economic capacity value, not automatically realized cash savings. Realization depends on reducing expenditure or productively redeploying the hours.'}


def publication_assets(state):
    financials=canonical_financials(state.get('financials'));groups=financials['groups'] if financials else []
    group=next((g for g in groups if g['kind']=='schedule'),groups[0] if groups else None)
    assets=[];calculations=[]
    native={number for chart in state.get('charts',[]) if chart.get('classification')!='hypothetical' for number in re.findall(r'\bFigure\s+(\d+)\b',chart.get('caption',''))}
    for h,body,owner in source_sections(state):
        figure=re.match(r'Figure\s+(\d+)\b',h['title'])
        if figure:
            if figure[1] in native:continue
            asset={'id':'F'+figure[1],'chapter':owner,'title':h['title'],'source_heading':h['id'],'classification':'authorial'}
            days=list(re.finditer(r'\*\*Day (\d+)\s+[—–-]\s+([^*]+)\*\*',body))
            arrow=next((line.strip() for line in body.splitlines() if line.count('→')>=2),None)
            if days:
                nodes=[]
                for i,m in enumerate(days):
                    tail=body[m.end():days[i+1].start() if i+1<len(days) else len(body)].strip()
                    nodes.append({'label':'Day '+m[1],'title':m[2].strip(),'description':tail.split('\n\n')[0]})
                asset.update(kind='diagram',nodes=nodes,branches=['CONTINUE','ADAPT','SCALE','STOP'] if 'CONTINUE / ADAPT / SCALE / STOP' in body else [])
            elif arrow:asset.update(kind='diagram',nodes=[{'label':str(i+1),'title':text.strip('* '),'description':''} for i,text in enumerate(arrow.split('→'))],branches=[])
            elif group:
                title=h['title'].casefold();key=None
                if 'labor' in title or 'labour' in title:key='labor_value'
                elif 'forecast' in title and 'change' in title or 'sensitivity' in title:key='sensitivity'
                elif 'futures' in title or 'scenario' in title:key='scenario_cash_flow'
                elif 'cash flow' in title:key='cumulative_cash_flow'
                elif 'revenue' in title:key='monthly_operating'
                elif 'cost' in title:key='expense_components'
                available=recipes(group);base=next(r for r in group['results'] if r['case']=='base')
                available['monthly_operating']={'title':'Monthly revenue and cash operating costs','kind':'bar','labels':[r['month'] for r in base['rows']],'series':[('Revenue',[r['revenue'] for r in base['rows']]),('Cash costs',[r['cash_costs'] for r in base['rows']])]}
                recipe=available.get(key)
                if not recipe:raise GenerationError('The authored '+h['title']+' has no supported calculated figure recipe.')
                asset.update(kind='chart',classification='hypothetical',recipe=key,group_id=group['id'],currency=group['currency'],labels=recipe['labels'],series=recipe['series'],svg=svg_plot(recipe['title'],recipe['series'],[str(i+1) for i in range(len(recipe['labels']))] if any(not str(label).isdigit() for label in recipe['labels']) else recipe['labels'],recipe['kind'],group['currency']))
            else:raise GenerationError('An authored figure needs explicit diagram or financial inputs: '+h['title'])
            assets.append(asset)
        elif 'proposed product experience' in h['title'].casefold():
            panels=list(re.finditer(r'\*\*\d+\.\s+([^*]+)\*\*',body))
            if panels:
                nodes=[]
                for i,m in enumerate(panels):
                    tail=body[m.end():panels[i+1].start() if i+1<len(panels) else len(body)].strip()
                    nodes.append({'label':str(i+1),'title':m[1].strip(),'description':tail.split('\n\n')[0]})
                assets.append({'id':'PRODUCT-EXPERIENCE','chapter':owner,'title':'Proposed product experience','classification':'authorial','kind':'diagram','nodes':nodes,'branches':[],'source_heading':h['id']})
        elif h['title'].startswith('Final Full-Page Visual'):
            parts=re.findall(r'(?m)^(?:On the|In the) (left|center|right): (.+)$',body)
            if len(parts)==3:assets.append({'id':'CLOSING-VISUAL','chapter':owner,'title':'From idea to informed investment','kind':'diagram','classification':'authorial','nodes':[{'label':place.title(),'title':text,'description':''} for place,text in parts],'branches':[],'source_heading':h['id']})
    if group:
        rows=[]
        for result in group['results']:
            spent=result['initial_investment']+sum(r['cash_costs'] for r in result['rows'])
            rows.append([result['case'],result['roi_pct'],float(Decimal(str(result['net_gain']))/Decimal(str(spent))*100) if spent else None,spent])
        owner=next((a['chapter'] for a in assets if a.get('recipe')=='scenario_cash_flow'),next((i for i,p in enumerate(state['outline']['chapters']) if 'financial_projections' in p['section_keys']),len(state['document']['chapters'])-1))
        calculations.append({'id':'return-definitions','chapter':owner,'title':'Return definitions: use the stated denominator','note':'Return on initial investment uses startup expenditure as its denominator. Return on total cash expenditure uses startup expenditure plus operating cash expenses. Both use the same net project cash result; they answer different questions and must be labeled distinctly. Total cash expenditure is not the peak funding requirement: cash receipts may finance later expenses. Percentages may be rounded to the displayed precision.',
                             'formulas':{'return_on_initial_investment':'net_project_cash_result / initial_expenditure × 100','return_on_total_cash_expenditure':'net_project_cash_result / (initial_expenditure + operating_cash_expenses) × 100'},
                             'table':{'title':'Calculated returns under both explicit definitions','columns':['Scenario','Return on initial investment (%)','Return on total cash expenditure (%)','Total cash expenditure'],'rows':[[display(cell) for cell in row] for row in rows],'classification':'hypothetical'}})
        funding_rows=[]
        for result in group['results']:
            initial=Decimal(str(result['initial_investment']));peak=Decimal(str(result['maximum_funding_requirement']))
            funding_rows.append([result['case'],display(float(initial)),display(float(peak)),display(float(peak/initial)) if initial else 'Undefined',str(result['break_even_month']) if result['break_even_month'] is not None else 'Not reached'])
        calculations.append({'id':'funding-definitions','chapter':owner,'title':'Cash funding exposure and recovery',
            'note':'Peak cash funding is the largest cumulative cash deficit, including startup expenditure. The funding multiple compares that complete requirement with startup expenditure alone; it is not the incremental shortfall. Cash outlay is recovered at the first month-end when cumulative project cash flow is nonnegative. These are calculated hypothetical results, not observed outcomes.',
            'formulas':{'peak_cash_funding':'max(0, −min(cumulative_project_cash_flow))','funding_multiple':'peak_cash_funding / initial_expenditure','cash_recovery_month':'first month with cumulative_project_cash_flow >= 0'},
            'table':{'title':'Calculated cash funding and recovery checkpoints','columns':['Scenario','Initial expenditure','Peak cash funding','Peak / initial (times)','Cash recovery month'],'rows':funding_rows,'classification':'hypothetical'}})
    automation=automation_calculation(state['author_original'])
    if automation:
        owner=next((i for i,ch in enumerate(state['document']['chapters']) if any('19,200' in p or '19200' in p for p in ch['paragraphs'])),len(state['document']['chapters'])-1)
        automation['chapter']=owner;calculations.append(automation)
    # Every numbered figure mentioned in the manuscript must actually render.
    mentioned=set(re.findall(r'\bFigure\s+(\d+)\b',' '.join(p for ch in state['document']['chapters'] for p in ch['paragraphs'])))
    present={a['id'][1:] for a in assets if re.fullmatch(r'F\d+',a['id'])}
    present.update(native)
    if not mentioned<=present:raise GenerationError('The manuscript references missing figures: '+', '.join(sorted(mentioned-present)))
    return assets,calculations


def render_asset(asset):
    e=lambda s:escape(str(s),quote=True)
    if asset['kind']=='chart':
        body=re.sub(r'<text x="([^"]+)" y="375"',r'<text class="publication-series-label" x="\1" y="375"',asset['svg'])
        colors=['#315e55','#b97a44','#49699b']
        body+='<div class="publication-chart-key">'+''.join('<span style="color:'+colors[i%3]+'">■ '+e(name)+'</span>' for i,(name,_) in enumerate(asset['series']))+'</div>'
        if any(not str(label).isdigit() for label in asset['labels']):
            body+='<div class="publication-chart-key">'+''.join('<span>'+str(i+1)+': '+e(label)+'</span>' for i,label in enumerate(asset['labels']))+'</div>'
    else:
        nodes=asset['nodes'];body='<ol class="publication-flow" style="--node-count:'+str(len(nodes))+'">'+''.join('<li><small>'+e(n['label'])+'</small><strong>'+e(n['title'])+'</strong>'+('<p>'+e(n['description'])+'</p>' if n['description'] else '')+'</li>' for n in nodes)+'</ol>'
        if asset.get('branches'):body+='<div class="publication-branches">'+''.join('<span>'+e(branch)+'</span>' for branch in asset['branches'])+'</div>'
    label='Hypothetical projection calculated from registered inputs ('+asset.get('currency','')+').' if asset['classification']=='hypothetical' else 'Author’s proposed process and product concept.'
    return '<figure class="publication-figure" id="publication-'+e(asset['id'])+'">'+body+'<figcaption>'+e(asset['title'])+' · '+label+'</figcaption></figure>'


def render_calculation(calc):
    e=lambda s:escape(str(s),quote=True)
    body='<section class="publication-calculations"><h3>'+e(calc['title'])+'</h3><p>'+e(calc['note'])+'</p>'
    if calc.get('table'):body+=render_table(calc['table'])
    else:
        labels={'hours_per_week':'Hours released per week','hourly_value':'Illustrative value per hour','working_weeks':'Working weeks per year','implementation_cost':'Implementation cash cost','monthly_operating_cost':'Monthly cash operating cost','annual_economic_benefit':'Modeled annual economic benefit','first_year_cash_expenditure':'First-year cash expenditure','net_modeled_economic_benefit':'Net modeled economic benefit','economic_return_on_cash_expenditure_pct':'Economic return on total cash expenditure (%)'}
        rows=[[labels.get(name,name.replace('_',' ')),display(value)] for name,value in {**calc['inputs'],**calc['outputs']}.items()]
        body+=render_table({'title':'Author-supplied hypothetical inputs and calculated economic outcomes','columns':['Input or result','Value'],'rows':rows,'classification':'hypothetical'})
    body+='<dl class="formula-register">'+''.join('<dt>'+e(name.replace('_',' '))+'</dt><dd><code>'+e(formula)+'</code></dd>' for name,formula in calc['formulas'].items())+'</dl></section>'
    return body


def review_blocks(state):
    blocks={}
    for i,ch in enumerate(state['document']['chapters']):
        for j,p in enumerate(ch['paragraphs']):blocks[f'P{i}.{j}']={'chapter':i,'text':p}
        for j,table in enumerate(ch.get('tables',[])):blocks[f'T{i}.{j}']={'chapter':i,'text':json.dumps(table,ensure_ascii=False)}
    for index,chart in enumerate(state.get('charts',[])):
        blocks[('CALCULATED-' if chart.get('classification')=='hypothetical' else 'EMPIRICAL-')+str(index)]={'chapter':chart['chapter'],'text':json.dumps({k:v for k,v in chart.items() if k!='svg'},ensure_ascii=False)}
    for asset in state.get('publication_assets',[]):blocks[asset['id']]={'chapter':asset['chapter'],'text':json.dumps({k:v for k,v in asset.items() if k!='svg'},ensure_ascii=False)}
    for calc in state.get('publication_calculations',[]):blocks['CALC-'+calc['id']]={'chapter':calc['chapter'],'text':json.dumps(calc,ensure_ascii=False)}
    for group in (state.get('financials') or {}).get('groups',[]):blocks['MODEL-'+group['id']]={'chapter':None,'text':json.dumps({'assumptions':group['scenarios'],'results':group['results']},ensure_ascii=False)}
    return blocks


def validate_bound_review(review,state,blocks):
    checks=review.get('checks');expected=set(criteria(state['author_contract']))
    if not isinstance(checks,list) or len(checks)!=len(expected) or {check.get('criterion') for check in checks if isinstance(check,dict)}!=expected:raise GenerationError('Publication review did not evaluate every required criterion.')
    failures=[];bound=[]
    for check in checks:
        if type(check.get('passed')) is not bool or not isinstance(check.get('reason'),str):raise GenerationError('Malformed publication review.')
        ids=check.get('evidence_blocks')
        if not check['passed']:failures.append(check['criterion']+': '+check['reason'])
        elif not isinstance(ids,list) or not ids or any(not isinstance(block,str) or block not in blocks for block in ids):failures.append(check['criterion']+': review evidence references an unknown publication block.')
        else:bound.append({**check,'evidence':'\n'.join(blocks[block]['text'] for block in ids)})
    return failures,bound
