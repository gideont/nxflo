"""Saved-state reproduction of the Vancouver/California regulatory rejection."""
from portal_api.generation_intent import build_contract,source_chunks,digest
from portal_api.generation_quality import criteria

CLAIMS=[
 'Micro-cafés can support neighbourhood walkability and community connection; the author proposes lower barriers to experimentation.',
 'California MEHKO permits were introduced around 2024 with a $100,000 annual gross sales cap.',
 'The author describes BC Food Premises Regulation categories as separating low-risk cottage food from high-risk dairy preparation.',
 'The brief describes Vancouver home-occupation limits of 33.3% or 46 m² and 3 clients/day, with no walk-in retail.',
 'The author proposes a BC MIKO framework with revenue ceilings and localized health standards.'
]
TITLES=['The opportunity','California blueprint','Health requirements','Home occupation','A proposed framework']
BRIEF='\n\n'.join('## '+title+'\n'+text for title,text in zip(TITLES,CLAIMS))
REJECTION="Empirical regulatory specifics (BC Food Premises Regulation categories, Vancouver home-occupation bylaw limits of 33.3%/46 m² and 3 clients/day, California MEHKO $100,000 cap and the 'around 2024' date) are stated as the author's brief with no exact external source evidence in the supplied packet (external evidence excerpts are empty). The brief itself says the claims remain subject to verification. Accuracy cannot be certified without source citations, so this criterion is rejected for unverified empirical claims, not for a demonstrated contradiction."


def saved_state(config):
    contract=build_contract(config,source_chunks(BRIEF),[{'items':[{'role':'thesis' if i==0 else 'argument','label':title,'quote':text} for i,(title,text) in enumerate(zip(TITLES,CLAIMS))]}])
    plans=[];chapters=[]
    for i,(title,text) in enumerate(zip(TITLES,CLAIMS)):
        ref='A'+str(i+1);section='H'+str(i+1)
        plans.append({'title':title,'brief':'Preserve the author’s position.','charts_needed':[],'author_refs':[ref],'section_keys':[section]})
        chapters.append({'title':title,'paragraphs':[text],'takeaway':'Consider a proportionate approach.','coverage':[{'author_ref':ref,'text_excerpt':text}],
            'claims':[{'text':text,'classification':'authorial','source_id':'','quote':''}],'charts':[],'tables':[],'formula_refs':[],'section_keys':[section]})
    checks=[{'criterion':key,'passed':key!='accuracy','evidence_blocks':['P0.0'] if key!='accuracy' else ['P1.0','P2.0','P3.0'],'reason':REJECTION if key=='accuracy' else 'Author intent and complete content are preserved.'} for key in criteria(contract)]
    return {'pipeline_version':2,'prompt_policy_version':2,'author_original':BRIEF,'author_source_hash':digest(BRIEF),'author_contract':contract,
        'document':{'chapters':chapters},'outline':{'title':config['title'],'chapters':plans},'sources':[{'id':'B1','role':'author','label':'Author’s original brief and intended message','text':BRIEF}],
        'warnings':[],'passes':1,'intent_audits':[],'financials':None,'charts':[],'next_step':'assemble','publication_assets':[],'publication_calculations':[],
        'quality_errors':['accuracy: '+REJECTION],'publication_review':{'checks':checks}}
