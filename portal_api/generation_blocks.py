"""Escaped publication tables and deterministic worked-example blocks."""
from html import escape
from .generation_finance import financial_tables,financial_figures,FORMULAS,display


def render_table(table):
    e=lambda value:escape(str(value),quote=True)
    columns=table['columns']
    return ('<table class="report-data-table"><caption>'+e(table['title'])+'</caption><thead><tr>'+''.join('<th scope="col">'+e(col)+'</th>' for col in columns)+
            '</tr></thead><tbody>'+''.join('<tr>'+''.join('<td data-label="'+e(columns[i])+'">'+e(value)+'</td>' for i,value in enumerate(row))+'</tr>' for row in table['rows'])+'</tbody></table>')


def worked_examples(state,index):
    financials=state.get('financials')
    if not financials:return ''
    plans=state['outline']['chapters']
    target=next((i for i,plan in enumerate(plans) if 'financial_projections' in plan.get('section_keys',[])),len(plans)-1)
    if index!=target:return ''
    e=lambda value:escape(str(value),quote=True)
    out='<div class="worked-financials"><h3>Worked investment scenarios</h3><p>These illustrative projections are calculated from the explicit hypothetical assumptions below. They show conditional outcomes rather than observed performance or guaranteed returns.</p><p>Initial project expenditure is paid at month zero. Operating cash flows arrive at month end. The 90-day pilot uses three 30-day planning months. Project ROI uses initial project expenditure as its denominator; participant returns use each participant’s cash funding. Cash funding is financing, not sales; distributions are financing cash flows, not operating expenses. Participant time is a separate non-cash opportunity cost. This simplified unlevered model excludes tax, debt, terminal value and working-capital timing beyond the stated cash expenses.</p>'
    for group in financials['groups']:
        base=next(result for result in group['results'] if result['case']=='base');pilot=base['rows'][:3];cur=group['currency']
        out+='<section class="financial-example"><h4>'+e(group['title'])+'</h4><p>'+e(group['assumption_note'])+'</p>'
        out+='<p>In the base case, initial project expenditure is '+e(cur)+' '+display(base['initial_investment'])+'. The first 90 days generate '+e(cur)+' '+display(sum(row['revenue'] for row in pilot))+' of revenue and '+e(cur)+' '+display(sum(row['cash_costs'] for row in pilot))+' of operating cash costs, leaving cumulative project cash flow of '+e(cur)+' '+display(pilot[-1]['cumulative_cash_flow'])+'. Over '+str(group['months'])+' months, projected revenue is '+e(cur)+' '+display(base['total_revenue'])+' and net project gain is '+e(cur)+' '+display(base['net_gain'])+'.</p>'
        out+='<p>Cash break-even '+('first occurs in month '+str(base['break_even_month']) if base['break_even_month'] else 'does not occur within this forecast')+'. Peak funding required is '+e(cur)+' '+display(base['maximum_funding_requirement'])+'. ROI is '+(display(base['roi_pct'])+'%' if base['roi_pct'] is not None else 'undefined because the initial investment is zero')+'. Participant distributions remain conditional on funding the modeled cash deficit. IRR is reported only for a conventional cash-flow sequence with a unique bracketed root; an undefined value is not zero.</p>'
        if base['unallocated_funding_gap']>0:out+='<p>Financing still required: '+e(cur)+' '+display(base['unallocated_funding_gap'])+'. Participant distributions are omitted until this cash shortfall is funded.</p>'
        if group['kind']=='youtube':out+='<p>Advertising, sponsorship and affiliate receipts are modeled as zero until the stated monetization month. Views then follow the assumed monthly growth rate; revenue uses views per thousand and the assumed RPM.</p>'
        if group['kind']=='saas':out+='<p>Paying customers equal retained opening customers plus new customers. Churn applies once per month; revenue uses closing paying customers at the assumed subscription fee. Fractional customer counts represent expected averages.</p>'
        out+=''.join(render_table(t) for t in financial_tables(group))
        figures,heat_table=financial_figures(group)
        if state.get('config',{}).get('charts',True):
            out+=''.join('<figure class="calculated-figure">'+fig['svg'].replace('#315e55',state.get('config',{}).get('color','#315e55')).replace('#b97a44',state.get('config',{}).get('accent','#b97a44'))+'<figcaption>'+e(fig['caption'])+'</figcaption></figure>' for fig in figures)
            out+=render_table(heat_table)
        out+='</section>'
    out+='<h4>Calculation definitions</h4><dl class="formula-register">'+''.join('<dt>'+e(key.replace('_',' '))+'</dt><dd><code>'+e(value)+'</code></dd>' for key,value in FORMULAS.items())+'</dl></div>'
    return out
