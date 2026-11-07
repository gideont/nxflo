"""Resolve calculator-owned chart requests to trusted, recomputed figure recipes."""
from decimal import Decimal
import math
import re
from .generation_finance import build_financials,svg_plot,MONEY
from .generation_authored_finance import tables,money
from .generation_errors import GenerationError


def recipes(group):
    base=next(r for r in group['results'] if r['case']=='base');rows=base['rows'];months=list(range(1,group['months']+1))
    costs=base['initial_investment']+sum(r['cash_costs'] for r in rows);labor=base['total_opportunity_cost']
    result={
        'monthly_revenue':{'title':'Monthly revenue','kind':'bar','labels':months,'series':[('Revenue',[r['revenue'] for r in rows])]},
        'cumulative_cash_flow':{'title':'Cumulative project cash flow','kind':'line','labels':[0]+months,'series':[('Base',[-base['initial_investment']]+[r['cumulative_cash_flow'] for r in rows])]},
        'scenario_cash_flow':{'title':'Three-scenario cumulative cash flow','kind':'line','labels':[0]+months,'series':[(r['case'],[-r['initial_investment']]+[row['cumulative_cash_flow'] for row in r['rows']]) for r in group['results']]},
        'labor_value':{'title':'Cash expenditure and contributed labor','kind':'bar','labels':['Cash costs','Labor value','Combined'],'series':[('Resource value',[costs,labor,costs+labor])]}}
    # Cost components are read from the exact retained source table, never guessed.
    for span in group.get('source_spans',[]):
        for header,source_rows,_,_ in tables(span['quote']):
            if header!=['Expense','Amount','Frequency']:continue
            components=[];labels=[]
            for row in source_rows:
                if len(row)!=3 or row[0].casefold().startswith('total'):continue
                if row[2].casefold() not in ('one-time','monthly'):break
                components.append(float(money(row[1])*(group['months'] if row[2].casefold()=='monthly' else 1)))
                labels.append(row[0].split(':')[0])
            else:
                if components and abs(sum(components)-costs)<.005:
                    result['expense_components']={'title':'Startup and recurring cash expenditure','kind':'bar','labels':[str(i+1) for i in range(len(components))]+['Total'],'series':[('Cash expenditure',components+[costs])],'details':'; '.join(str(i+1)+': '+name for i,name in enumerate(labels))}
    if group['kind']=='schedule':
        initial=Decimal(str(base['initial_investment']));revenue=[Decimal(str(r['revenue'])) for r in rows];cash=[Decimal(str(r['cash_costs'])) for r in rows]
        outcomes=[base['net_gain'],float(-initial+sum(MONEY(r*Decimal('.8'))-c for r,c in zip(revenue,cash))),
                  float(-initial+sum(revenue[:-1])-sum(cash)),float(-initial+sum(revenue)-sum(cash)-20*group['months'])]
        result['sensitivity']={'title':'Sensitivity of the projected cash result','kind':'bar','labels':['Base','Revenue −20%','Delay 1 month','Costs +20/mo'],'series':[('Cash result',outcomes)]}
    return result


def canonical_financials(financials):
    if not financials:return None
    rebuilt=build_financials({'groups':[{k:v for k,v in group.items() if k!='results'} for group in financials['groups']]})
    if rebuilt!=financials:raise GenerationError('Stored financial outputs contradict their registered calculations.')
    return rebuilt


def chart_reference(chart,financials,original):
    if not isinstance(chart,dict) or not financials:return None
    group=next((g for g in financials['groups'] if g['id']==chart.get('source_id')),None)
    if not group:return None
    values=chart.get('values');labels=chart.get('labels')
    if not isinstance(values,list) or not isinstance(labels,list) or len(labels)!=len(values) or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):return None
    candidates=recipes(group)
    # A base-case cumulative series requests the complete scenario comparison
    # when its author-provided caption explicitly identifies several futures.
    order=list(candidates)
    if re.search(r'three|scenario|futures',str(chart.get('title','')),re.I):order.remove('scenario_cash_flow');order.insert(0,'scenario_cash_flow')
    for key in order:
        recipe=candidates[key]
        if chart.get('kind')!=recipe['kind']:continue
        if key in ('monthly_revenue','cumulative_cash_flow','scenario_cash_flow'):
            parsed=[re.fullmatch(r'(?:Month\s*)?(\d+)',str(label),re.I) for label in labels]
            if not all(parsed) or [int(label[1]) for label in parsed]!=recipe['labels']:continue
        for _,series in recipe['series']:
            if len(values)==len(series) and all(math.isclose(a,b,rel_tol=0,abs_tol=1e-7) for a,b in zip(values,series)):
                figure=re.match(r'Figure\s+(\d{1,2})\b',str(chart.get('title','')),re.I)
                return {'group_id':group['id'],'recipe':key,'figure_number':int(figure[1]) if figure and re.search(r'(?m)^#{1,4}\s+Figure\s+'+figure[1]+r'\b',original) else None}
    return None


def route_calculated_charts(chapters,financials,original):
    financials=canonical_financials(financials)
    for group in financials['groups'] if financials else []:
        for span in group.get('source_spans',[]):
            if not isinstance(span,dict) or type(span.get('start')) is not int or type(span.get('end')) is not int or not 0<=span['start']<=span['end']<=len(original) or original[span['start']:span['end']]!=span.get('quote'):
                raise GenerationError('A financial input source span does not match the original brief.')
    for chapter in chapters:
        if not isinstance(chapter,dict) or not isinstance(chapter.get('charts'),list):continue
        remaining=[];refs=chapter.get('calculated_chart_refs',[])
        if not isinstance(refs,list):refs=[]
        for chart in chapter['charts']:
            ref=chart_reference(chart,financials,original)
            if ref:
                if ref not in refs:refs.append(ref)
            else:remaining.append(chart)
        chapter['charts']=remaining
        if refs:chapter['calculated_chart_refs']=refs
    return chapters


def render_reference(ref,financials,original):
    if not isinstance(ref,dict):raise GenerationError('Invalid calculated figure reference.')
    group=next((g for g in financials['groups'] if g['id']==ref.get('group_id')),None)
    recipe=recipes(group).get(ref.get('recipe')) if group else None
    if not recipe:raise GenerationError('Unknown calculated figure recipe.')
    title=recipe['title'];number=ref.get('figure_number')
    if number is not None:
        if type(number) is not int:raise GenerationError('Invalid authored figure number.')
        heading=re.search(r'(?m)^#{1,4}\s+(Figure\s+'+str(number)+r'\b[^\n]*)',original)
        if not heading:raise GenerationError('Calculated figure number is absent from the original brief.')
        title=heading[1]
    svg=svg_plot(recipe['title'],recipe['series'],recipe['labels'],recipe['kind'],group['currency'])
    caption=title+' · Hypothetical projection calculated from registered inputs.'
    if recipe.get('details'):caption+=' '+recipe['details']
    return {'svg':svg,'caption':caption,'classification':'hypothetical','in_chapter':True,'group_id':group['id'],'recipe':ref['recipe']}
