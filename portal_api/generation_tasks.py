"""Killable blocking operations with wall-clock deadlines and live parent monitoring."""
import json
import multiprocessing
import time
from .generation_errors import GenerationError,TransientGenerationError,RejectedGenerationError,RateLimitedGenerationError


def _execute(channel,function,args):
    try:channel.send(('ok',function(*args)))
    except GenerationError as error:channel.send(('rate_limited' if isinstance(error,RateLimitedGenerationError) else 'rejected' if isinstance(error,RejectedGenerationError) else 'transient' if isinstance(error,TransientGenerationError) else 'error',str(error)))
    except Exception as error:channel.send(('error','Operation failed ('+type(error).__name__+').'))
    finally:channel.close()


def run_task(function,args,*,timeout,check=lambda:None,pulse=lambda elapsed:None,pulse_interval=5):
    """A separate process also bounds DNS, trickled responses and stuck parsers."""
    check();context=multiprocessing.get_context('spawn');reader,writer=context.Pipe(duplex=False)
    process=context.Process(target=_execute,args=(writer,function,args),daemon=True)
    started=time.monotonic();deadline=started+timeout;next_pulse=started
    try:
        process.start();writer.close()
        while True:
            check();now=time.monotonic()
            if now>=deadline:raise TransientGenerationError('The operation exceeded its '+str(timeout)+'-second deadline.')
            if now>=next_pulse:pulse(int(now-started));next_pulse=now+pulse_interval
            if reader.poll(min(.25,max(.001,deadline-now))):
                try:kind,result=reader.recv()
                except EOFError:raise GenerationError('The request process ended without a result.')
                check()
                if time.monotonic()>=deadline:raise TransientGenerationError('The operation exceeded its '+str(timeout)+'-second deadline.')
                if kind=='transient':raise TransientGenerationError(result)
                if kind=='rate_limited':raise RateLimitedGenerationError(result)
                if kind=='rejected':raise RejectedGenerationError(result)
                if kind!='ok':raise GenerationError(result)
                return result
            if not process.is_alive():raise GenerationError('The request process ended without a result.')
    finally:
        writer.close();reader.close()
        if process.pid is not None:
            if process.is_alive():process.terminate()
            process.join(timeout=1)
            if process.is_alive():process.kill();process.join(timeout=1)
            process.close()


def monitored_call(connection,job_id,label,timeout,function,args,*,check,message):
    start=time.time();waiting={'label':label,'started_at':start,'deadline_at':start+timeout,'limit_seconds':timeout}
    connection.execute('UPDATE generator_jobs SET wait_state=? WHERE id=?',(json.dumps(waiting),job_id))
    try:
        def pulse(elapsed):message('Waiting for '+label+' · '+str(elapsed)+'s elapsed · '+str(timeout)+'s limit. No complete response yet.')
        result=run_task(function,args,timeout=timeout,check=check,pulse=pulse)
        message(label+' completed.')
        return result
    finally:connection.execute("UPDATE generator_jobs SET wait_state='{}' WHERE id=?",(job_id,))
