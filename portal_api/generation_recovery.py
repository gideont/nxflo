"""Recovery decisions shared by the API and durable worker."""
import json
import time
from . import db
from .generation_errors import TransientGenerationError

RETRY_DELAYS=(30,120,300)


def recovery_info(connection,row):
    saved=json.loads(row['recovery'])
    provider='Databricks workspace' if json.loads(row['config']).get('provider')=='databricks' else 'OpenRouter'
    uncertain=connection.execute("SELECT stage FROM generator_calls WHERE job_id=? AND status='submitting' AND remote_id IS NULL LIMIT 1",(row['id'],)).fetchone()
    blocked=('A '+uncertain['stage']+' request has an unknown provider outcome. Check its '+provider+' activity before submitting it again; automatic recovery is paused to prevent duplicate charges.') if uncertain else ''
    if any(str(value).endswith(':batch') for key,value in json.loads(row['config']).items() if key.endswith('_model')):
        blocked='Batch generation has been retired. Use this configuration to start a new document with Databricks or a synchronous OpenRouter model.'
    if not blocked:
        for call in connection.execute("SELECT result FROM generator_calls WHERE job_id=? AND status='submitted'",(row['id'],)):
            status=json.loads(call['result'] or '{}').get('status')
            if status in ('failed','expired','cancelled'):
                blocked='The provider ended the existing Batch as '+status+'. Its results and billing must be reconciled before submitting a replacement Batch.'
                break
    return {**saved,'can_resume':row['status'] in ('failed','cancelled','queued') and not blocked,'blocked_reason':blocked,
            'retry_at':row['next_run_at'] if row['status']=='queued' and saved.get('attempts') else None}


def recover_failure(connection,job_id,error,message):
    """Retry only transient operations whose previous submission is accounted for."""
    with db.transaction(connection):
        row=connection.execute('SELECT * FROM generator_jobs WHERE id=?',(job_id,)).fetchone()
        if row['status']=='cancelled':return
        info=recovery_info(connection,row);attempts=info.get('attempts',0)
        if isinstance(error,TransientGenerationError) and not info['blocked_reason'] and attempts<len(RETRY_DELAYS):
            delay=RETRY_DELAYS[attempts]
            saved={'attempts':attempts+1,'last_error':message}
            text='Temporary interruption. Automatic retry '+str(attempts+1)+' of '+str(len(RETRY_DELAYS))+' in '+str(delay)+' seconds; saved work will be reused.'
            connection.execute("UPDATE generator_jobs SET status='queued',error='',message=?,recovery=?,next_run_at=?,updated_at=? WHERE id=?",(text,json.dumps(saved),time.time()+delay,db.now(),job_id))
        else:
            text=message+(' '+info['blocked_reason'] if info['blocked_reason'] else ' Saved work is preserved. Use Resume generation to try this step again.')
            connection.execute("UPDATE generator_jobs SET status='failed',error=?,message=?,updated_at=? WHERE id=?",(text,text,db.now(),job_id))
