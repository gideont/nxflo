(function(root){
  'use strict';
  const order=['collect','summarize','outline','draft','review','rewrite','polish','charts','assemble','html_review','pdf','deliver'];
  const seconds=value=>Number.isFinite(value)?Math.max(0,value):0;
  function duration(value){
    const n=Math.floor(seconds(value)),h=Math.floor(n/3600),m=Math.floor(n%3600/60),s=String(n%60).padStart(2,'0');
    return h?`${h}h ${String(m).padStart(2,'0')}m ${s}s`:`${m}m ${s}s`;
  }
  function estimate(job,now=Date.now()/1000){
    if(!job?.id)return null;
    const events=job.events || [],active=['queued','running'].includes(job.status),start=Date.parse(job.created_at)/1000;
    const finished=Date.parse(job.updated_at)/1000,end=active?now:Number.isFinite(finished)?finished:now;
    const elapsed=seconds(end-start),config=job.config || {},stage=order.indexOf(job.step);
    const terminal={elapsed,active,overTarget:elapsed>600};
    if(!active)return {...terminal,kind:'stopped'};
    const batch=job.batch_wait || ['summary','draft','polish'].some(role=>String(config[role+'_model']).endsWith(':batch'));
    if(batch)return {...terminal,kind:'batch',deadline:job.batch_wait?.expires_at || null};
    if(job.worker_online===false)return {...terminal,kind:'offline'};
    const chapters=job.chapter_count || Math.max(2,Math.min(12,Math.ceil((config.pages || config.cost_pages || 12)/3)));
    const chunks=job.source_metrics?.summary_chunks || Math.max(1,Math.ceil(((config.topic || '').length+(config.documents || []).reduce((n,d)=>n+(d.text || '').length,0))/24000));
    const passes=config.review_passes || 1,reviewed=events.filter(e=>e.step==='review' && e.status==='complete').length;
    const weights={collect:90,summarize:chunks*12,outline:20,draft:chapters*35,review:chapters*12*Math.max(1,passes-reviewed),rewrite:chapters*30*Math.max(1,passes-reviewed),polish:chapters*25,charts:4,assemble:4,html_review:0,pdf:15,deliver:1};
    const starts=events.filter(e=>e.step===job.step && ['started','resumed'].includes(e.status));
    const began=starts.length?Date.parse(starts.at(-1).at)/1000:now;
    let remaining=order.slice(Math.max(0,stage)).reduce((n,key)=>n+weights[key],0);
    remaining-=Math.min(weights[job.step] || 0,seconds(now-began));
    remaining=Math.max(15,remaining)+seconds((job.recovery?.retry_at || 0)-now);
    const flex=config.provider!=='databricks' && ['summary','draft','polish'].some(role=>config[role+'_service']==='flex');
    return {...terminal,kind:flex?'flex':'estimate',low:Math.max(15,Math.round(remaining*.65)),high:Math.max(30,Math.round(remaining*1.5))};
  }
  function step(job,key,now=Date.now()/1000){
    const events=(job.events || []).filter(event=>event.step===key),active=['queued','running'].includes(job.status) && job.step===key;
    let elapsed=0,opened=null;
    for(const event of events){
      const at=Date.parse(event.at)/1000;
      if(!Number.isFinite(at))continue;
      if(event.status==='started')opened=at;
      if(event.status==='complete' && opened!=null){elapsed+=seconds(at-opened);opened=null;}
    }
    const complete=events.some(event=>event.status==='complete') && !active;
    const end=active?now:Date.parse(job.updated_at)/1000;
    if(opened!=null)elapsed+=seconds(end-opened);
    else if(active && !events.some(event=>event.status==='started' && Number.isFinite(Date.parse(event.at))))elapsed+=seconds(now-Date.parse(job.created_at)/1000);
    const progress=job.step_progress?.step===key?job.step_progress:null;
    const batch=active && job.batch_wait?.request_counts;
    const total=Number(batch?.total ?? progress?.total),count=Number(batch?.completed ?? progress?.completed);
    const known=active && Number.isFinite(total) && total>0 && Number.isFinite(count);
    return {active,complete,elapsed,percentage:complete?100:known?Math.min(100,Math.max(0,Math.floor(count/total*100))):null,completed:known?Math.min(total,Math.max(0,count)):null,total:known?total:null,unit:progress?.unit || 'requests'};
  }
  const api={estimate,duration,step};root.NxfloTiming=api;
  if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
