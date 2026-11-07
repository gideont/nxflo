"""One non-native search with a conservative, reserved per-document spending bound."""
from decimal import Decimal, ROUND_CEILING
from .generation_errors import GenerationError

MAX_WEB_BUDGET=0.30
WEB_MODEL='openai/gpt-6-luna'
SEARCH_FEE=Decimal('0.001')  # Parallel Turbo, one request, <= 5 results.
MAX_INPUT_PRICE=Decimal('0.25')  # USD / million; includes published cache-write tiers.
MAX_OUTPUT_PRICE=Decimal('0.75')
OUTPUT_TOKENS=1800
POLICY_VERSION=1


def web_plan(catalog,budget):
    try:limit=Decimal(str(budget))
    except ArithmeticError:raise GenerationError('Invalid web research spending limit.')
    if not limit.is_finite() or not 0<=limit<=Decimal(str(MAX_WEB_BUDGET)):raise GenerationError('Web research limit must be between US$0 and US$0.30.')
    if limit==0:raise GenerationError('Web research is disabled by the US$0 spending limit.')
    row=next((item for item in catalog.get('data',[]) if item.get('id')==WEB_MODEL),None)
    if not row or type(row.get('context_length')) is not int or not 0<row['context_length']<=10000000:raise GenerationError('Web research skipped: current model context limits could not be verified.')
    pricing=row.get('pricing');overrides=pricing.get('overrides',[]) if isinstance(pricing,dict) else None
    if not isinstance(pricing,dict) or not isinstance(overrides,list) or any(not isinstance(tier,dict) for tier in overrides):raise GenerationError('Web research skipped: current pricing could not be verified.')
    prices=[pricing,*overrides]
    try:
        base=row['pricing'];Decimal(base['prompt']);Decimal(base['completion'])
        for price in prices:
            if Decimal(str(price.get('request',0)))!=0:raise ValueError()
            for name in ('prompt','input_cache_read','input_cache_write','input_cache_write_1h','completion'):
                if price.get(name) is None:continue
                value=Decimal(str(price[name]))*1000000
                ceiling=MAX_OUTPUT_PRICE if name=='completion' else MAX_INPUT_PRICE
                if not value.is_finite() or not 0<=value<=ceiling:raise ValueError()
    except (KeyError,ValueError,TypeError,ArithmeticError):raise GenerationError('Web research skipped: current prices exceed the permitted rate ceilings or could not be verified.')
    # Reserve for the FULL model context at capped rates, capped output, one search,
    # plus 10% headroom for platform/BYOK fees. Never rely on a timeout as a cost cap.
    reserve=(((Decimal(row['context_length'])*MAX_INPUT_PRICE+OUTPUT_TOKENS*MAX_OUTPUT_PRICE)/1000000+SEARCH_FEE)*Decimal('1.10')).quantize(Decimal('0.000001'),rounding=ROUND_CEILING)
    if reserve>limit:raise GenerationError('Web research skipped: its conservative maximum of US$'+str(reserve)+' exceeds your US$'+str(limit)+' limit.')
    return {'version':POLICY_VERSION,'engine':'parallel','mode':'turbo','max_results':5,'output_tokens':OUTPUT_TOKENS,'context_limit':row['context_length'],'reserved_usd':float(reserve),'search_fee_usd':float(SEARCH_FEE),'limit_usd':float(limit),'max_price':{'prompt':float(MAX_INPUT_PRICE),'completion':float(MAX_OUTPUT_PRICE)}}
