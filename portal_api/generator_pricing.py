"""Public catalog prices only. No credentials or document content leave the server."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import requests

SOURCE='https://openrouter.ai/api/v1/models'
SNAPSHOT=Path(__file__).with_name('model_pricing.json')


def catalog(data):
    models={}
    for row in data.get('data',[]):
        if 'text' not in row.get('architecture',{}).get('output_modalities',[]): continue
        pricing=row.get('pricing',{})
        try:
            input_rate=float(pricing['prompt'])*1000000
            output_rate=float(pricing['completion'])*1000000
        except (KeyError,ValueError,TypeError): continue
        if not all(math.isfinite(x) and x>=0 for x in (input_rate,output_rate)): continue
        models[row['id']]={'name':row['name'],'input':input_rate,'output':output_rate,'tiers':pricing.get('overrides',[])}
    if not models: raise ValueError('Catalog contains no usable text model prices')
    return {'models':models,'checked_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'source':SOURCE,'currency':'USD'}


def read_prices(refresh=False):
    saved=json.loads(SNAPSHOT.read_text())
    if refresh:
        try:
            response=requests.get(SOURCE,timeout=(5,12));response.raise_for_status()
            return catalog(response.json())
        except (requests.RequestException,ValueError,KeyError,TypeError):
            saved['warning']='Live prices could not be refreshed. Showing the bundled dated snapshot.'
    return saved
