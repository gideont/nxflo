"""Read explicit hypothetical monthly schedules without estimating replacement inputs."""
import re
from decimal import Decimal
from .generation_errors import GenerationError


def money(cell):
    value=cell.strip().replace('**','').replace('−','-').replace(',','').replace('$','')
    if not re.fullmatch(r'[+-]?\d+(?:\.\d{1,2})?',value):raise GenerationError('An authored financial table contains an unsupported monetary input.')
    return Decimal(value)


def tables(text):
    pattern=r'(?m)^\|[^\n]+\|\s*\n\|[ :|\-]+\|\s*\n(?:\|[^\n]+\|[ \t]*(?:\n|$))+'
    for match in re.finditer(pattern,text):
        lines=match.group().strip().splitlines()
        rows=[[cell.strip() for cell in line.strip().strip('|').split('|')] for line in lines]
        yield rows[0],rows[2:],match.start(),match.end()


def authored_financial_plan(text):
    """Recognize complete, explicitly hypothetical source tables or leave planning alone.

    Source rows are inputs. Net flows, returns, deficits and charts are recomputed.
    No interpolation, inferred growth, fictitious financing or new revenue curve.
    """
    parsed=list(tables(text))
    base=next((t for t in parsed if t[0]==['Month','Revenue','Operating Expense','Monthly Operating Cash Flow']),None)
    scenarios=next((t for t in parsed if t[0]==['Month','Conservative','Base','Optimistic'] and t[1] and t[1][0][0]=='1' and 'hypothetical USD revenue per month' in text[max(0,t[2]-500):t[2]]),None)
    expenses=next((t for t in parsed if t[0]==['Expense','Amount','Frequency']),None)
    if not base or not scenarios or not expenses:return None
    startup=[money(row[1]) for row in expenses[1] if len(row)==3 and row[2].casefold()=='one-time']
    if not startup:return None
    base_rows=base[1];case_rows=[row for row in scenarios[1] if row[0].isdigit()]
    months=len(base_rows)
    if not 3<=months<=36 or len(case_rows)!=months:raise GenerationError('The authored monthly scenario tables have inconsistent forecast lengths.')
    revenues={name:[] for name in ('conservative','base','optimistic')};costs=[]
    for index,(row,cases) in enumerate(zip(base_rows,case_rows),1):
        if len(row)!=4 or len(cases)!=4 or row[0]!=str(index) or cases[0]!=str(index):raise GenerationError('The authored forecast must have contiguous matching monthly rows.')
        revenue,cost,net=map(money,row[1:])
        if revenue-cost!=net:raise GenerationError('The authored monthly operating cash-flow formula is contradictory in month '+str(index)+'.')
        if revenue!=money(cases[2]):raise GenerationError('The authored base-case revenue disagrees between its tables.')
        costs.append(float(cost))
        for name,value in zip(revenues,cases[1:]):revenues[name].append(float(money(value)))
    for row in scenarios[1]:
        if row[0].replace('**','').casefold()=='total revenue':
            for name,value in zip(revenues,row[1:]):
                if sum(Decimal(str(v)) for v in revenues[name])!=money(value):raise GenerationError('The authored scenario revenue total is contradictory.')
    hours=hourly=0
    labor=re.search(r'\*\*(\d+) hours × \$(\d+(?:\.\d+)?) = \$([\d,]+) of contributed labor value\*\*',text)
    if labor:
        total_hours,rate,total=map(lambda value:Decimal(value.replace(',','')),labor.groups())
        if total_hours*rate!=total:raise GenerationError('The authored contributed-labor calculation is contradictory.')
        hours=float(total_hours/months);hourly=float(rate)
    inputs={'initial_investment':float(sum(startup)),'fixed_monthly_cost':0,'hours_per_month':hours,'hourly_opportunity_value':hourly,'annual_discount_rate':0}
    group={'id':'authored-monthly-scenarios','title':'The author’s worked investment scenarios','kind':'schedule','currency':'USD','months':months,
           'assumption_note':'Hypothetical revenue and cash expenses come directly from the original monthly tables. Startup expenditure is counted once at month zero. All outcomes are recalculated. Contributed labor, when specified, is spread across the forecast as a non-cash opportunity cost. Discounting is excluded (rate zero). Financing has not been allocated; the calculated cash deficit is the amount still to be funded. No participant agreement or distribution is assumed.',
           'participants':[],'scenarios':[{'case':name,'inputs':dict(inputs)} for name in revenues],
           'authored_schedule':{name:{'revenue':values,'cash_costs':list(costs)} for name,values in revenues.items()},
           'source_spans':[{'start':t[2],'end':t[3],'quote':text[t[2]:t[3]]} for t in (expenses,base,scenarios)]}
    return {'groups':[group]}
