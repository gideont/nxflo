"""De-identified author brief and transparent provider fixtures; no live model calls."""
from pathlib import Path
from copy import deepcopy
import json
import re
from portal_api.generation_models import Models
from portal_api.generation_intent import build_contract,source_chunks

BRIEF=(Path(__file__).parent/'fixtures/investment-return-simulator.md').read_text()
# Each passage is a real author anchor, paired with professional paraphrase.
ANCHORS=[
 ('thesis','Investment decision simulator','Build a financial decision simulator that helps users understand whether an idea is worth investing in, what assumptions must hold true, and what it would take to achieve a return.',
  'The Investment & Return Simulator is a financial decision simulator for judging whether an idea is worth investing in, which assumptions must hold true and what it would take to achieve a return.'),
 ('audience','Intended users','Build a modern, interactive financial planning application that allows individuals, entrepreneurs, investors, and small teams to model the potential financial outcome of a project or business opportunity **before committing resources**.',
  'Individuals, entrepreneurs, investors and small teams can explore a business opportunity before committing money and resources. The opportunity is to make financial planning understandable without requiring accounting expertise.'),
 ('argument','FP&A rather than expense tracking','It is a lightweight **FP&A and investment decision-support tool** that turns business ideas into measurable financial projections.',
  'This lightweight FP&A and investment decision-support tool turns business ideas into measurable financial projections. It addresses the decision to invest, rather than merely tracking expenses after spending has occurred.'),
 ('example','YouTube venture','Include a sample project: "Three Brothers AI Cartoon YouTube Channel".',
  'The Three Brothers AI Cartoon YouTube Channel illustrates a small team testing a creative venture. The simulator connects video production, monetized views, advertising RPM, sponsorship and affiliate assumptions to a cash forecast.'),
 ('example','SaaS business drivers','Monthly revenue = Active paying customers × Average monthly subscription fee.',
  'A SaaS example links active paying customers and the average monthly subscription fee. Acquisition and churn assumptions explain how customer growth affects recurring revenue and the funding needed to support the service.'),
 ('message','No double-counting cash and time','Distinguish cash expenditure from non-cash opportunity costs. Never count the same cost twice.',
  'The economic model separates initial investment and recurring cash expenditure from non-cash opportunity costs. Participant time is valued separately, so the model never counts the same cost twice.'),
 ('message','Delayed monetization','Do not assume that a new YouTube channel immediately earns advertising revenue. Allow zero revenue during the pre-monetization period.',
  'A new YouTube channel earns no advertising revenue during its pre-monetization period. Monetization eligibility and timing remain editable assumptions, making a delayed or unprofitable outcome visible.'),
 ('argument','Partnership resources','Cash contributions and work contributions should remain separate unless users explicitly agree to convert work into ownership.',
  'The partnership model keeps cash contributions and work contributions separate. Ownership and profit-sharing are explicit agreements; hours of work do not silently become equity. Participants can compare their cash contributions and projected distributions.'),
 ('argument','Budget versus actual FP&A','Maintain an original baseline so users can see how expectations changed over time.',
  'Budget-versus-actual performance and reforecasting retain an original baseline, so users see how expectations changed over time. This FP&A workflow compares spending, revenue, operational KPIs and cumulative cash flow against the initial investment case.'),
 ('message','Conditional forecasts','Never present a financial forecast as a guaranteed outcome.',
  'A financial forecast describes a conditional outcome rather than a guarantee. Adoption, production costs and monetization timing are practical risks to test through conservative, base and optimistic assumptions.'),
 ('message','Practical prototype','Organize the calculation engine separately from UI components so that it can later be reused in a production application.',
  'A working interactive prototype keeps the calculation engine separate from UI components. React and TypeScript, local persistence, JSON import and export, CSV projections and a printable summary support a reusable model without unnecessary backend complexity.'),
 ('message','Go/no-go decision','Use the result to make an informed go/no-go investment decision.',
  'The practical value is an informed go/no-go investment decision. A short pilot tests operational milestones, cash exposure and acceptable loss before a larger commitment; users can revise assumptions and compare the outcome with the preserved baseline.'),
]
SECTION_KEYS=['problem','opportunity','solution','economic_model','use_cases','financial_projections','risks','practical_value']
ASSIGN=[[0,2],[1],[0,10],[5,6],[3,4,7],[3,4],[9],[8,11]]
TITLES=['The decision problem','An accessible planning opportunity','The proposed simulator','Economic model and cash discipline','YouTube, SaaS and partnership use cases','Worked financial projections','Risks and decision conditions','Practical FP&A value']


def extraction(part):
    return {'items':[{'role':role,'label':label,'quote':quote} for role,label,quote,_ in ANCHORS if quote in part]}


def contract(config):
    parts=source_chunks(config['topic'])
    return build_contract(config,parts,[extraction(part['text']) for part in parts])


def outline():
    return {'title':'Investment & Return Simulator: From Product Vision to Investment Decision','chapters':[
        {'title':title,'brief':'Explain this part of the product vision with its original examples.','charts_needed':[],'section_keys':[key],'author_refs':['A'+str(i+1) for i in ids]}
        for title,key,ids in zip(TITLES,SECTION_KEYS,ASSIGN)]}


def manuscript():
    chapters=[]
    for plan,indices in zip(outline()['chapters'],ASSIGN):
        paragraphs=[ANCHORS[i][3] for i in indices]
        if 'financial_projections' in plan['section_keys']:paragraphs.append('Worked hypothetical projections make the investment decision concrete. The accompanying tables disclose every assumption, a pre-monetization pilot, monthly cash flows, break-even, investment returns and scenario sensitivity. Calculations keep funding separate from revenue and non-cash time separate from cash operating costs.')
        chapters.append({'title':plan['title'],'paragraphs':paragraphs,'takeaway':'Test the investment decision against explicit assumptions.','charts':[],'tables':[],
                         'section_keys':plan['section_keys'],'coverage':[{'author_ref':'A'+str(i+1),'text_excerpt':ANCHORS[i][3]} for i in indices],
                         'claims':[{'text':p,'classification':'authorial','source_id':'','quote':''} for p in paragraphs],'formula_refs':[]})
    chapters[2]['tables']=[{'title':'How the product supports investment decisions','columns':['Capability','Practical use'],'rows':[['Scenario planning','Compare adoption and operating-cost assumptions'],['Budget versus actual','Preserve a baseline and reforecast from actual performance']],'classification':'authorial','evidence':[]}]
    return {'chapters':chapters}


def financial_plan():
    common={'initial_investment':200,'fixed_monthly_cost':40,'hours_per_month':20,'hourly_opportunity_value':25,'annual_discount_rate':.1}
    youtube={'videos_per_month':8,'views_per_video':5000,'monthly_view_growth':.12,'rpm':5,'monetization_month':3,'production_cost_per_video':4,'sponsorship_monthly':0,'affiliate_monthly':0}
    base={**common,**youtube}
    scenarios=[{'case':'conservative','inputs':{**base,'rpm':1.5,'monthly_view_growth':.02,'monetization_month':7,'fixed_monthly_cost':120}},
               {'case':'base','inputs':base},{'case':'optimistic','inputs':{**base,'rpm':7,'monthly_view_growth':.25,'monetization_month':2}}]
    participants=[{'name':'Partner A','cash_contribution':200,'profit_share':.4},{'name':'Partner B','cash_contribution':150,'profit_share':.3},{'name':'Partner C','cash_contribution':150,'profit_share':.3}]
    groups=[{'id':'youtube','title':'Three Brothers AI Cartoon YouTube Channel','kind':'youtube','currency':'USD','months':12,'assumption_note':'All values in this worked example are illustrative assumptions, including views, RPM, costs, monetization timing and the participant funding agreement. They are not observed channel performance.','participants':participants,'scenarios':scenarios}]
    saas={**common,'initial_investment':1500,'fixed_monthly_cost':300,'initial_customers':0,'new_customers_per_month':10,'monthly_acquisition_growth':.05,'churn_rate':.03,'monthly_subscription':29,'variable_cost_per_customer':2}
    groups.append({'id':'saas','title':'A SaaS subscription pilot','kind':'saas','currency':'USD','months':12,'assumption_note':'These hypothetical acquisition, churn, pricing, cash-cost and funding inputs illustrate how a SaaS business case is calculated; none is an empirical performance claim.','participants':[{'name':'Founder','cash_contribution':3000,'profit_share':1}],
                   'scenarios':[{'case':'conservative','inputs':{**saas,'new_customers_per_month':2,'fixed_monthly_cost':600}}, {'case':'base','inputs':saas}, {'case':'optimistic','inputs':{**saas,'new_customers_per_month':15,'churn_rate':.02}}]})
    return {'groups':deepcopy(groups)}


class FixtureModels(Models):
    requests=[]
    bad_stage=None
    reject_publication=False
    def request(self,method,path,body=None):
        self.check()
        if method!='POST':raise AssertionError('No provider metadata lookup expected')
        row=self.db.execute("SELECT stage FROM generator_calls WHERE job_id=? AND status='submitting' ORDER BY rowid DESC LIMIT 1",(self.job_id,)).fetchone()
        full=row['stage'];stage,index=full.rsplit(':',1);index=int(index);self.requests.append(full)
        prompt=body['messages'][-1]['content']
        if stage=='author-intent':value=extraction(prompt)
        elif stage=='outline':value=outline()
        elif stage=='financial-plan':value=financial_plan()
        elif stage.startswith('review-'):value={'major_issues':[],'minor_notes':[]}
        elif stage.startswith('publication-quality'):
            doc=json.JSONDecoder().raw_decode(prompt.split('\nManuscript: ',1)[1])[0]
            ids=json.JSONDecoder().raw_decode(prompt.split('Evaluate each required criterion exactly once: ',1)[1])[0]
            proofs={proof['author_ref']:proof['text_excerpt'] for ch in doc['chapters'] for proof in ch['coverage']}
            sections={key:ch['paragraphs'][0] for ch in doc['chapters'] for key in ch['section_keys']}
            value={'checks':[]}
            for criterion in ids:
                evidence=proofs[criterion.split(':',1)[1]] if criterion.startswith('author:') else sections[criterion.split(':',1)[1]] if criterion.startswith('section:') else doc['chapters'][0]['paragraphs'][0]
                value['checks'].append({'criterion':criterion,'passed':not(self.reject_publication and criterion=='purpose'),'evidence':evidence,'reason':'The original product vision and source distinctions are preserved.' if not self.reject_publication else 'The document has become an academic research report rather than a product concept.'})
        else:
            value=deepcopy(manuscript()['chapters'][index])
            if self.bad_stage and (stage==self.bad_stage or stage.startswith('intent-repair-')):
                value['paragraphs']=['This academic research report cannot verify the product concept and recommends further independent verification.'];value['coverage']=[];value['claims']=[]
        return {'id':'fixture-'+full,'choices':[{'message':{'content':json.dumps(value)},'finish_reason':'stop'}],'usage':{'cost':0,'is_byok':False}}
