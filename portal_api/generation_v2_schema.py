"""Explicit author contracts, prose provenance and calculator-input schemas."""
from .generation_schema import object_schema,STRING,STRINGS,CHART
from .generation_finance import COMMON,DRIVERS

PROOF=object_schema({'author_ref':STRING,'text_excerpt':STRING})
EVIDENCE=object_schema({'source_id':STRING,'quote':STRING})
TABLE=object_schema({'title':STRING,'columns':STRINGS,'rows':{'type':'array','items':STRINGS},'classification':{'type':'string','enum':['authorial','empirical']},'evidence':{'type':'array','items':EVIDENCE}})
CLAIM=object_schema({'text':STRING,'classification':{'type':'string','enum':['authorial','empirical']},'source_id':STRING,'quote':STRING})
CHAPTER=object_schema({'title':STRING,'paragraphs':STRINGS,'takeaway':STRING,'charts':{'type':'array','items':CHART},'tables':{'type':'array','items':TABLE},'section_keys':STRINGS,'coverage':{'type':'array','items':PROOF},'claims':{'type':'array','items':CLAIM},'formula_refs':STRINGS})
PLAN=object_schema({'title':STRING,'brief':STRING,'charts_needed':STRINGS,'section_keys':STRINGS,'author_refs':STRINGS})


def scenario_plan_schema():
    cases=[]
    for kind,drivers in DRIVERS.items():
        inputs=object_schema({key:({'type':'integer'} if key=='monetization_month' else {'type':'number'}) for key in COMMON+drivers})
        scenario=object_schema({'case':{'type':'string','enum':['conservative','base','optimistic']},'inputs':inputs})
        cases.append(object_schema({'id':STRING,'title':STRING,'kind':{'type':'string','enum':[kind]},'currency':STRING,'months':{'type':'integer'},'assumption_note':STRING,
                                    'participants':{'type':'array','items':object_schema({'name':STRING,'cash_contribution':{'type':'number'},'profit_share':{'type':'number'}})},
                                    'scenarios':{'type':'array','items':scenario}}))
    return object_schema({'groups':{'type':'array','items':{'anyOf':cases}}})


def schema(stage):
    if stage=='author-intent':
        return object_schema({'items':{'type':'array','items':object_schema({'role':{'type':'string','enum':['thesis','audience','argument','example','message']},'label':STRING,'quote':STRING})}})
    if stage in ('financial-plan','financial-plan-repair'):return scenario_plan_schema()
    if stage=='outline':return object_schema({'title':STRING,'chapters':{'type':'array','minItems':1,'maxItems':24,'items':PLAN}})
    if stage.startswith('publication-quality'):
        return object_schema({'checks':{'type':'array','items':object_schema({'criterion':STRING,'passed':{'type':'boolean'},'evidence':STRING,'reason':STRING})}})
    if stage in ('draft','polish') or stage.startswith(('rewrite-','intent-repair-')):return CHAPTER
    return None
