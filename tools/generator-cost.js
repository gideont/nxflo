/* Transparent planning calculator; no model calls or document transfers. */
((root) => {
  'use strict';
  function rate(model, inputTokens, service='default') {
    let input=model.input,output=model.output;
    for(const tier of [...(model.tiers || [])].sort((a,b)=>a.min_prompt_tokens-b.min_prompt_tokens)) {
      if(inputTokens>=Number(tier.min_prompt_tokens)) {
        if(tier.prompt!=null && Number.isFinite(Number(tier.prompt)) && Number(tier.prompt)>=0)input=Number(tier.prompt)*1e6;
        if(tier.completion!=null && Number.isFinite(Number(tier.completion)) && Number(tier.completion)>=0)output=Number(tier.completion)*1e6;
      }
    }
    if(service==='flex'){input/=2;output/=2;}
    return {input,output};
  }
  function estimate(config, prices, passes=Number(config.review_passes), observed=null) {
    const pages=Number(config.length_mode==='target'?config.pages:(config.cost_pages ?? 12));
    if(!Number.isInteger(pages) || pages<1 || pages>60 || !Number.isInteger(passes) || passes<1 || passes>4)return null;
    const ids=[config.summary_model,config.draft_model,config.polish_model];
    if(ids.some(id=>!prices?.models || !Object.hasOwn(prices.models,id)))return null;
    const links=root.NxfloSources?root.NxfloSources.extract(config.topic,config.youtube):null;
    const videos=links?links.youtube.length:String(config.youtube || '').split('\n').filter(line=>line.trim()).length;
    const references=links?links.references.length:0,web=config.web_search && Number(config.web_budget_usd ?? .30)>0;
    const source=observed?Math.ceil(observed.source_characters/4):Math.ceil(((config.documents || []).reduce((total,doc)=>total+doc.text.length,0)+String(config.topic || '').length+String(config.questions || '').length)/4)+videos*6000+references*6000+(web?6000:0);
    const chunks=observed?.summary_chunks ?? Math.max(1,Math.ceil(String(config.topic || '').length/24000)+(config.documents || []).reduce((total,doc)=>total+Math.ceil(doc.text.length/24000),0)+videos+references+(web?1:0));
    const notes=Math.max(1000,Math.min(40000,chunks*250));
    const manuscript=Math.ceil(pages*650),chapters=Math.max(2,Math.min(12,Math.ceil(pages/3)));
    const feedback=Math.ceil(String(config.feedback || '').length/4),revisionContext=config.revision_parent?manuscript:0;
    const rows=[];
    function add(stage,model,input,output,calls=1,service='default') {
      const rates=rate(prices.models[model],input,service);
      rows.push({stage,model,input:input*calls,output:output*calls,cost:calls*(input*rates.input+output*rates.output)/1e6});
    }
    add('Summarize evidence',ids[0],Math.ceil(source/chunks)+500,Math.ceil(notes/chunks),chunks,config.summary_service);
    add('Outline',ids[1],notes+1000+feedback+(revisionContext?chapters*30:0),1200,1,config.draft_service);
    add('Draft chapters',ids[1],notes+2200+revisionContext+feedback,Math.ceil(manuscript/chapters),chapters,config.draft_service);
    add('Review',ids[1],Math.ceil(manuscript/chapters)+notes+1000+feedback,1200,passes*chapters,config.draft_service);
    add('Rewrite',ids[1],Math.ceil(manuscript/chapters)+notes+2200,Math.ceil(manuscript/chapters),passes*chapters,config.draft_service);
    add('Final polish',ids[2],Math.ceil(manuscript/chapters)+1000+feedback,Math.ceil(manuscript/chapters),chapters,config.polish_service);
    if(web){
      const research=prices.models['openai/gpt-6-luna'];
      if(!research && !observed?.web_cost_known)return null;
      const rates=research?rate(research,12000,'flex'):null;
      const cost=observed?.web_cost_known?observed.web_cost:(12000*rates.input+1800*rates.output)/1e6+.001;
      rows.push({stage:observed?.web_cost_known?'Web research (reported charges)':'Web research (one search + Luna Flex notes)',model:'openai/gpt-6-luna',input:12000,output:1800,cost});
    }
    return {observed:!!observed,total:rows.reduce((sum,row)=>sum+row.cost,0),rows,pages,sourceTokens:source,manuscriptTokens:manuscript,chapters,passes};
  }
  const api={estimate,rate};root.NxfloCosts=api;
  if(typeof module!=='undefined' && module.exports)module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
