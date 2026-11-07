"""Keep OpenRouter wallet charges and BYOK provider charges distinct, then total them."""
import json
import math


def amount(value):return float(value) if type(value) in (int,float) and math.isfinite(value) and value>=0 else None


def usage_bill(result):
    usage=result.get('usage') or {};usage=usage if isinstance(usage,dict) else {}
    detail=usage.get('cost_details') or {}
    return {'generation_id':result.get('id'),'credit_cost':amount(usage.get('cost')),'provider_cost':amount(detail.get('upstream_inference_cost')),'is_byok':usage.get('is_byok') if type(usage.get('is_byok')) is bool else None,'model':result.get('model'),'service_tier':result.get('service_tier')}


def generation_bill(data):
    return {'generation_id':data.get('id'),'credit_cost':amount(data.get('total_cost',data.get('usage'))),'provider_cost':amount(data.get('upstream_inference_cost')),'is_byok':data.get('is_byok') if type(data.get('is_byok')) is bool else None,'model':data.get('model'),'service_tier':data.get('service_tier'),'web_search_engine':data.get('web_search_engine'),'input_tokens':data.get('native_tokens_prompt'),'output_tokens':data.get('native_tokens_completion')}


def total_bill(bill):
    credit=bill.get('credit_cost');provider=bill.get('provider_cost')
    if credit is None:return None
    if bill.get('is_byok') is True:return credit+provider if provider is not None else None
    if bill.get('is_byok') is False or provider==0:return credit
    return None


def record_bill(connection,job_id,key,bill):
    # Preserve policy and known fields while reconciling delayed provider metadata.
    row=connection.execute('SELECT billing FROM generator_calls WHERE job_id=? AND call_key=?',(job_id,key)).fetchone()
    previous=json.loads(row['billing']) if row and row['billing'] else {}
    merged={**previous,**{name:value for name,value in bill.items() if value is not None}}
    total=total_bill(merged)
    connection.execute('UPDATE generator_calls SET billing=?,cost=?,cost_known=? WHERE job_id=? AND call_key=?',(json.dumps(merged),total if total is not None else 0,int(total is not None),job_id,key))
    return merged
