"""Deterministic hypothetical cash-flow scenarios. No model-authored output numbers or eval."""
from decimal import Decimal, localcontext, ROUND_HALF_UP, ROUND_DOWN
from copy import deepcopy
from html import escape
import math
import re
from .generation_errors import GenerationError

FORMULAS = {
 'youtube_revenue':'revenue = monetized_views / 1000 * rpm + sponsorship + affiliate_income',
 'saas_revenue':'revenue = active_paying_customers * monthly_subscription',
 'operating_profit':'operating_profit = revenue - cash_operating_costs',
 'cash_flow':'net_cash_flow = revenue - cash_operating_costs',
 'cumulative_cash_flow':'cumulative_cash_flow = -initial_investment + sum(net_cash_flow)',
 'roi':'ROI = (sum(net_cash_flow) - initial_investment) / initial_investment',
 'npv':'NPV = sum(cash_flow[t] / (1 + monthly_discount_rate)^t), including t = 0',
 'discount_rate':'monthly_discount_rate = (1 + annual_discount_rate)^(1/12) - 1',
 'irr':'IRR solves sum(cash_flow[t] / (1 + monthly_IRR)^t) = 0',
}
COMMON=['initial_investment','fixed_monthly_cost','hours_per_month','hourly_opportunity_value','annual_discount_rate']
DRIVERS={
 'youtube':['videos_per_month','views_per_video','monthly_view_growth','rpm','monetization_month','production_cost_per_video','sponsorship_monthly','affiliate_monthly'],
 'saas':['initial_customers','new_customers_per_month','monthly_acquisition_growth','churn_rate','monthly_subscription','variable_cost_per_customer'],
 'generic':['initial_units','monthly_unit_growth','unit_price','variable_cost_per_unit'],
}
D=lambda x:Decimal(str(x))
def MONEY(value):
    amount=D(value)
    if not amount.is_finite() or abs(amount)>D('1e15'):raise GenerationError('The hypothetical model exceeds its supported monetary range.')
    return amount.quantize(D('.01'),rounding=ROUND_HALF_UP)



def number(value,label,low=0,high=1_000_000_000):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise GenerationError('Invalid hypothetical assumption: '+label+'.')
    return D(value)


def validate_plan(plan):
    groups=plan.get('groups') if isinstance(plan,dict) else None
    if not isinstance(groups,list) or not 1<=len(groups)<=3:raise GenerationError('Financial examples need 1–3 scenario groups.')
    ids=set()
    for group in groups:
        if not isinstance(group,dict) or group.get('kind') not in DRIVERS or not isinstance(group.get('title'),str) or not 1<=len(group['title'])<=160:raise GenerationError('Invalid financial scenario group.')
        if not re.fullmatch(r'[A-Z]{3}',group.get('currency','')) or type(group.get('months')) is not int or not 3<=group['months']<=36:raise GenerationError('Use an explicit currency and a 3–36 month forecast.')
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}',group.get('id','')) or group['id'] in ids:raise GenerationError('Scenario groups need unique stable IDs.')
        ids.add(group['id'])
        scenarios=group.get('scenarios',[])
        if not isinstance(scenarios,list) or len(scenarios)!=3 or {s.get('case') for s in scenarios if isinstance(s,dict)}!={'conservative','base','optimistic'}:raise GenerationError('Provide conservative, base and optimistic hypothetical scenarios.')
        for scenario in scenarios:
            inputs=scenario.get('inputs');expected=set(COMMON+DRIVERS[group['kind']])
            if not isinstance(inputs,dict) or set(inputs)!=expected:raise GenerationError('Scenario inputs do not match the registered financial model.')
            for key,value in inputs.items():
                low=-.95 if key.endswith('growth') else 0
                high=1 if key in ('churn_rate','annual_discount_rate') else 5 if key.endswith('growth') else 1_000_000_000
                number(value,key,low,high)
            if group['kind']=='youtube' and (type(inputs['monetization_month']) is not int or not 1<=inputs['monetization_month']<=group['months']+1):raise GenerationError('The monetization month must be explicit, including a possible delay beyond the forecast.')
        participants=group.get('participants')
        if not isinstance(participants,list) or not 1<=len(participants)<=12:raise GenerationError('Financial examples need explicit participant assumptions.')
        for p in participants:
            if not isinstance(p,dict) or set(p)!={'name','cash_contribution','profit_share'} or not isinstance(p['name'],str) or not 1<=len(p['name'])<=100:raise GenerationError('Invalid hypothetical participant.')
            number(p['cash_contribution'],'cash contribution');number(p['profit_share'],'profit share',0,1)
        if abs(sum(D(p['profit_share']) for p in participants)-1)>D('.000001'):raise GenerationError('Hypothetical profit shares must sum to 100%.')
        if not isinstance(group.get('assumption_note'),str) or not 20<=len(group['assumption_note'])<=1500:raise GenerationError('Explain the hypothetical assumptions and their provenance.')
    return plan


def npv(flows,rate):
    with localcontext() as ctx:
        ctx.prec=48
        return sum((D(flow)/(1+D(rate))**t for t,flow in enumerate(flows)),D(0))


def irr(flows):
    signs=[1 if value>0 else -1 for value in flows if value]
    if not signs or signs[0]!=-1 or sum(a!=b for a,b in zip(signs,signs[1:]))!=1:return None
    lo=D('-.999999');hi=D(1)
    for _ in range(40):
        if npv(flows,hi)<=0:break
        hi=hi*2+1
    else:return None
    for _ in range(180):
        mid=(lo+hi)/2
        if npv(flows,mid)>0:lo=mid
        else:hi=mid
    return float((lo+hi)/2)


def calculate(group,scenario):
    i={k:D(v) for k,v in scenario['inputs'].items()};months=group['months'];kind=group['kind'];initial=MONEY(i['initial_investment'])
    rows=[];cumulative=-initial;customers=i.get('initial_customers',D(0));break_even=None;payback=None;peak=initial;flows=[-initial]
    for month in range(1,months+1):
        if kind=='youtube':
            units=i['videos_per_month']*i['views_per_video']*(1+i['monthly_view_growth'])**(month-1)
            revenue=units/1000*i['rpm']+i['sponsorship_monthly']+i['affiliate_monthly'] if month>=i['monetization_month'] else D(0)
            costs=i['fixed_monthly_cost']+i['videos_per_month']*i['production_cost_per_video']
        elif kind=='saas':
            customers=customers*(1-i['churn_rate'])+i['new_customers_per_month']*(1+i['monthly_acquisition_growth'])**(month-1)
            units=customers;revenue=customers*i['monthly_subscription'];costs=i['fixed_monthly_cost']+customers*i['variable_cost_per_customer']
        else:
            units=i['initial_units']*(1+i['monthly_unit_growth'])**(month-1);revenue=units*i['unit_price'];costs=i['fixed_monthly_cost']+units*i['variable_cost_per_unit']
        revenue=MONEY(revenue);costs=MONEY(costs);net=revenue-costs;prior=cumulative;cumulative+=net;peak=max(peak,-cumulative)
        if break_even is None and cumulative>=0:
            break_even=month;payback=float(D(month-1)+(-prior/net if net else 0))
        opportunity=MONEY(i['hours_per_month']*i['hourly_opportunity_value'])
        rows.append({'month':month,'units':float(units.quantize(D('.01'))),'revenue':float(revenue),'cash_costs':float(costs),'net_cash_flow':float(net),'cumulative_cash_flow':float(cumulative),'opportunity_cost':float(opportunity),'economic_profit':float(net-opportunity)})
        flows.append(net)
    rate=(1+i['annual_discount_rate'])**(D(1)/12)-1
    cash_funding=sum(D(p['cash_contribution']) for p in group['participants']);funding_gap=max(D(0),peak-cash_funding)
    distributions=[]
    if funding_gap==0:
        cash_available=max(D(0),cash_funding+cumulative);returned_capital=min(cash_funding,cash_available);surplus=max(D(0),cash_available-cash_funding)
        amounts=[]
        for p in group['participants']:
            contribution=D(p['cash_contribution']);capital=returned_capital*contribution/cash_funding if cash_funding else D(0)
            amounts.append(capital+surplus*D(p['profit_share']))
        # Largest-remainder allocation balances to cents without negative residuals.
        raw=amounts
        amounts=[value.quantize(D('.01'),rounding=ROUND_DOWN) for value in raw]
        pennies=int((MONEY(cash_available)-sum(amounts))*100)
        order=sorted(range(len(raw)),key=lambda index:raw[index]-amounts[index],reverse=True)
        for index in order[:pennies]:amounts[index]+=D('.01')
        for p,amount in zip(group['participants'],amounts):
            contribution=D(p['cash_contribution'])
            distributions.append({'name':p['name'],'contribution':float(contribution),'distribution':float(amount),'return_pct':float((amount-contribution)/contribution*100) if contribution else None})
    monthly_irr=irr(flows)
    return {'case':scenario['case'],'rows':rows,'initial_investment':float(initial),'total_revenue':float(sum(D(row['revenue']) for row in rows)),
            'net_gain':float(cumulative),'total_opportunity_cost':float(sum(D(row['opportunity_cost']) for row in rows)),'economic_gain':float(cumulative-sum(D(row['opportunity_cost']) for row in rows)),'roi_pct':float(cumulative/initial*100) if initial else None,'break_even_month':break_even,'payback_months':payback,
            'maximum_funding_requirement':float(peak),'unallocated_funding_gap':float(funding_gap),'npv':float(MONEY(npv(flows,rate))),
            'monthly_irr':monthly_irr,'annualized_irr':(1+monthly_irr)**12-1 if monthly_irr is not None else None,
            'distributions':distributions,'cash_flows':[float(flow) for flow in flows]}


def build_financials(plan):
    validate_plan(plan)
    return {'formula_version':1,'classification':'hypothetical','formulas':FORMULAS,'groups':[{**deepcopy(group),'results':[calculate(group,scenario) for scenario in group['scenarios']]} for group in plan['groups']]}


def display(value):
    if value is None:return 'Not defined'
    if isinstance(value,(int,float)):return f'{value:,.2f}'
    return str(value)


def table(title,columns,rows):
    return {'title':title,'columns':columns,'rows':[[display(cell) for cell in row] for row in rows],'classification':'hypothetical'}


def financial_tables(group):
    base=next(result for result in group['results'] if result['case']=='base');currency=group['currency']
    assumptions=[]
    cases={scenario['case']:scenario['inputs'] for scenario in group['scenarios']}
    for key in COMMON+DRIVERS[group['kind']]:assumptions.append([key.replace('_',' '),*[cases[case][key] for case in ('conservative','base','optimistic')]])
    summary=[[result['case'],result['total_revenue'],result['net_gain'],result['roi_pct'],result['break_even_month'] or 'Never within forecast',result['maximum_funding_requirement'],result['npv']] for result in group['results']]
    result=[table('Hypothetical assumptions — '+group['title'],['Editable assumption','Conservative','Base','Optimistic'],assumptions),
            table('Calculated scenario comparison ('+currency+')',['Scenario','Revenue','Net gain','ROI %','Cash break-even month','Peak cash deficit','NPV'],summary),
            table('Base case monthly projection ('+currency+')',['Month','Revenue','Cash operating costs','Net cash flow','Cumulative cash flow','Non-cash opportunity cost','Economic profit'],[[row[k] for k in ('month','revenue','cash_costs','net_cash_flow','cumulative_cash_flow','opportunity_cost','economic_profit')] for row in base['rows']]),
            table('Return metrics — base case',['Metric','Calculated value'],[['Initial project expenditure',base['initial_investment']],['Maximum funding requirement',base['maximum_funding_requirement']],['Total non-cash opportunity cost',base['total_opportunity_cost']],['Economic gain after opportunity cost',base['economic_gain']],['Payback in months',base['payback_months']],['Monthly IRR (%)',base['monthly_irr']*100 if base['monthly_irr'] is not None else None],['Annualized IRR (%)',base['annualized_irr']*100 if base['annualized_irr'] is not None else None],['Unallocated funding gap',base['unallocated_funding_gap']]])]
    result.append(table('Hypothetical participant funding and profit-sharing assumptions',['Participant','Cash funding ('+currency+')','Profit share (%)'],[[p['name'],p['cash_contribution'],p['profit_share']*100] for p in group['participants']]))
    if base['distributions']:result.append(table('Calculated participant cash distributions ('+currency+')',['Participant','Cash contributed','Cash returned','Investor return %'],[[p['name'],p['contribution'],p['distribution'],p['return_pct']] for p in base['distributions']]))
    return result


def svg_plot(title,series,labels,kind='line',unit=''):
    """Registered, deterministic chart values; no untrusted SVG or remote assets."""
    e=lambda x:escape(str(x),quote=True);colors=['#315e55','#b97a44','#49699b'];width=680;height=390
    values=[float(value) for _,sequence in series for value in sequence];low=min(0,min(values));high=max(0,max(values));span=high-low or 1
    y=lambda value:300-(value-low)/span*180
    step=560/max(len(labels),1)
    out=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{e(title)}"><rect width="680" height="390" fill="white"/><text x="35" y="30" font-size="22" fill="#253d35">{e(title)}</text><text x="35" y="57" font-size="18">Hypothetical · {e(unit)}</text>'
    out+=f'<line x1="55" x2="635" y1="{y(0)}" y2="{y(0)}" stroke="#9baa9e"/>'
    for j,(name,sequence) in enumerate(series):
        points=[]
        for k,value in enumerate(sequence):
            x=65+(k+.5)*step;points.append(f'{x},{y(value)}')
            if kind=='bar':
                bar=step*.7/len(series);bx=x-step*.35+j*bar
                out+=f'<rect x="{bx}" y="{min(y(0),y(value))}" width="{bar}" height="{max(1,abs(y(value)-y(0)))}" fill="{colors[j%3]}"/>'
        if kind!='bar':out+=f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[j%3]}" stroke-width="4"/>'
        out+=f'<text x="{35+j*210}" y="375" font-size="18" fill="{colors[j%3]}">{e(name)}</text>'
    tick=max(1,math.ceil(len(labels)/6))
    for i,label in enumerate(labels):
        if i%tick==0 or i==len(labels)-1:out+=f'<text x="{65+(i+.5)*step}" y="331" text-anchor="middle" font-size="18">{e(label)}</text>'
    for value in (low,high):out+=f'<text x="35" y="{y(value)-7}" font-size="17">{value:,.0f}</text>'
    return out+'</svg>'


def donut(title,values,labels):
    total=sum(values);e=lambda x:escape(str(x),quote=True);colors=['#315e55','#b97a44','#49699b'];out=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 360" role="img" aria-label="{e(title)}"><rect width="680" height="360" fill="white"/><text x="25" y="30" font-size="22">{e(title)}</text><text x="25" y="58" font-size="18">Hypothetical cost composition</text>'
    offset=0;circ=2*math.pi*100
    for i,(value,label) in enumerate(zip(values,labels)):
        length=value/total*circ if total else 0
        out+=f'<circle cx="170" cy="205" r="100" fill="none" stroke="{colors[i%3]}" stroke-width="45" stroke-dasharray="{length} {circ-length}" stroke-dashoffset="{-offset}" transform="rotate(-90 170 205)"/>'
        out+=f'<text x="335" y="{150+i*45}" font-size="20" fill="{colors[i%3]}">{e(label)}: {value:,.2f}</text>';offset+=length
    return out+'</svg>'


def sensitivity(group):
    scenario=deepcopy(next(s for s in group['scenarios'] if s['case']=='base'));key={'youtube':'views_per_video','saas':'new_customers_per_month','generic':'initial_units'}[group['kind']]
    demands=(.1,.5,1,1.25,1.5);costs=(.5,1,1.5,2);rows=[];cells=[]
    for y,cost in enumerate(costs):
        for x,demand in enumerate(demands):
            changed=deepcopy(scenario);changed['inputs'][key]*=demand;changed['inputs']['fixed_monthly_cost']*=cost
            value=calculate(group,changed)['roi_pct'];rows.append([cost,demand,value]);cells.append((x,y,value))
    positive=max([value for _,_,value in cells if value is not None and value>0] or [1])
    negative=max([-value for _,_,value in cells if value is not None and value<0] or [1])
    def palette(value):
        if value is None:return '#e5e7e4','#243d35'
        intensity=min(1,abs(value)/(positive if value>=0 else negative))
        neutral=(245,247,241);target=(49,94,85) if value>=0 else (164,71,50)
        color='#'+''.join(f'{round(a+(b-a)*intensity):02x}' for a,b in zip(neutral,target))
        return color,'#fff' if intensity>.55 else '#243d35'
    out='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 400" role="img" aria-label="ROI sensitivity heatmap"><rect width="680" height="400" fill="white"/><text x="25" y="28" font-size="23">Hypothetical ROI sensitivity</text><text x="25" y="57" font-size="17">Rows: cash cost multiplier · Columns: demand multiplier</text>'
    for y,cost in enumerate(costs):out+=f'<text x="25" y="{127+y*55}" font-size="19">{cost}x</text>'
    for x,demand in enumerate(demands):out+=f'<text x="{144+x*112}" y="82" text-anchor="middle" font-size="18">{demand}x</text>'
    for x,y,value in cells:
        color,ink=palette(value);label=f'{value:.1f}%' if value is not None else 'N/A'
        out+=f'<rect x="{90+x*112}" y="{93+y*55}" width="108" height="51" fill="{color}"/><text x="{144+x*112}" y="{126+y*55}" text-anchor="middle" font-size="19" fill="{ink}">{label}</text>'
    out+='<text x="90" y="350" font-size="18">Red: loss · Green: gain · Darker: larger magnitude</text>'
    return out+'</svg>',table('Calculated ROI sensitivity',['Cash cost multiplier','Demand multiplier','ROI %'],rows)


def financial_figures(group):
    base=next(result for result in group['results'] if result['case']=='base');rows=base['rows'];labels=[row['month'] for row in rows];cur=group['currency']
    figures=[]
    def add(title,svg):figures.append({'svg':svg,'caption':title+' · Hypothetical projection calculated from the assumption register.','classification':'hypothetical'})
    add('Monthly revenue versus cash expenses',svg_plot('Monthly revenue versus cash expenses',[('Revenue',[r['revenue'] for r in rows]),('Cash expenses',[r['cash_costs'] for r in rows])],labels,'bar',cur))
    add('Cumulative project cash flow',svg_plot('Cumulative project cash flow',[('Base case',[r['cumulative_cash_flow'] for r in rows])],labels,unit=cur))
    add('Initial and recurring cost composition',donut('Initial and recurring costs',[base['initial_investment'],sum(r['cash_costs'] for r in rows)],['Initial expenditure','Recurring cash costs']))
    add('Conservative, base and optimistic outcomes',svg_plot('Three-scenario cash flow comparison',[(r['case'],[row['cumulative_cash_flow'] for row in r['rows']]) for r in group['results']],labels,unit=cur))
    cumulative_revenue=[];cumulative_cost=[];rev=0;cost=base['initial_investment']
    for row in rows:rev+=row['revenue'];cost+=row['cash_costs'];cumulative_revenue.append(rev);cumulative_cost.append(cost)
    suffix='month '+str(base['break_even_month']) if base['break_even_month'] else 'never within forecast'
    add('Cash break-even: '+suffix,svg_plot('Cash break-even: '+suffix,[('Cumulative revenue',cumulative_revenue),('Cumulative cash costs',cumulative_cost)],labels,unit=cur))
    heatmap,heat_table=sensitivity(group);add('ROI sensitivity heatmap',heatmap)
    if base['distributions']:add('Participant contributions and cash distributions',svg_plot('Participant contributions and returns',[('Cash funded',[p['contribution'] for p in base['distributions']]),('Cash distributed',[p['distribution'] for p in base['distributions']])],list(range(1,len(base['distributions'])+1)),'bar',cur+' · participant numbers follow the table'))
    return figures,heat_table
