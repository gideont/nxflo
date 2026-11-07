"""Strict provider schemas for each structured document-generation stage."""
def object_schema(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
STRING={'type':'string'}
STRINGS={'type':'array','items':STRING}
CHART=object_schema({'kind':{'type':'string','enum':['bar','line']},'title':STRING,'labels':STRINGS,'values':{'type':'array','items':{'type':'number'}},'unit':STRING,'source_id':STRING,'evidence':STRINGS})
CHAPTER=object_schema({'title':STRING,'paragraphs':STRINGS,'takeaway':STRING,'charts':{'type':'array','items':CHART}})

def response_schema(stage,config):
    if config.get('_pipeline_version')==2:
        from .generation_v2_schema import schema
        structured=schema(stage)
        if structured:return {'type':'json_schema','json_schema':{'name':'intent_document','strict':True,'schema':structured}}
    if stage=='outline':
        count=max(2,min(12,(config['pages']+2)//3)) if config['length_mode']=='target' else None
        schema=object_schema({'title':STRING,'chapters':{'type':'array','minItems':count or 2,'maxItems':count or 12,'items':object_schema({'title':STRING,'brief':STRING,'charts_needed':STRINGS})}})
        name='outline'
    elif stage.startswith('review-'):
        schema=object_schema({'major_issues':STRINGS,'minor_notes':STRINGS});name='review'
    elif stage=='draft' or stage=='polish' or stage.startswith('rewrite-'):
        schema=CHAPTER;name='chapter'
    else:schema=object_schema({'notes':STRING});name='notes'
    return {'type':'json_schema','json_schema':{'name':name,'strict':True,'schema':schema}}
