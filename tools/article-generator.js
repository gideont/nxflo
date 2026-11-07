(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const endpoint = '/bms_integration_hub/api/admin/generator';
  const form = $('generator-form');
  const steps = [['collect','Collect sources'],['summarize','Summarize evidence'],['outline','Plan chapters & contents'],['draft','Draft chapters'],['review','Review evidence & gaps'],['rewrite','Refine the draft'],['polish','Final editorial polish'],['charts','Draw charts & graphs'],['assemble','Assemble the document'],['html_review','Preview HTML & continue'],['pdf','Export PDF'],['deliver','Ready for your review']];
  let csrf='', revision=0, config=null, configured=false, loaded=false, loading=false, active=null, pollTimer, saveTimer, saving=null, busy=false, uploading=0, parentId=null, defaults=null, watched=null, dirty=false;
  const checks=['toc','charts','images','graphics','web_search','advanced_models'];
  const numeric=['pages','review_passes','cost_pages','web_budget_usd'];
  const defaultModels={summary_model:'openai/gpt-6-luna',draft_model:'openai/gpt-6-luna',polish_model:'openai/gpt-6-luna'};
  const aiFields=['company','title','questions'];
  let pricing=null,observedSources=null,matrixSignature='';
  let timedJob=null,timingReceived=0;
  let providerSettings={openrouter:{configured:false},databricks:{configured:false,model:''}};
  const sourceSignature=current=>JSON.stringify([current.topic,current.youtube,current.web_search,current.document_intent,(current.documents || []).map(doc=>[doc.name,doc.text.length,doc.role || 'author'])]);
  const usd=value=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:4}).format(value);
  const assetKeys=['logo','documents','illustrations','teams'];
  function message(text) { $('generator-status').textContent=text; }
  function button(text, action) { const el=document.createElement('button');el.type='button';el.className='admin-button';el.textContent=text;el.addEventListener('click',action);return el; }
  async function request(path='', options={}) {
    const response=await fetch(endpoint+path,{credentials:'same-origin',...options,headers:{'X-CSRF-Token':csrf,...options.headers}});
    const data=await response.json();
    if(!response.ok) { const e=new Error(data.error || 'The request failed. Please try again.');e.status=response.status;throw e; }
    return data;
  }
  const json = (method, body) => ({method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  function values() {
    const result={...config,revision_parent:parentId || ''};
    for(const [key,value] of new FormData(form)) if(!assetKeys.includes(key)) result[key]=numeric.includes(key)?Number(value):value;
    for(const key of checks) result[key]=form.elements[key].checked;
    if(result.length_mode!=='target' && (!Number.isInteger(result.pages) || result.pages<1))result.pages=12;
    if(result.length_mode==='target' && (!Number.isInteger(result.cost_pages) || result.cost_pages<1))result.cost_pages=12;
    for(const [key,model] of Object.entries(defaultModels))result[key]=String(result[key] || model);
    for(const role of ['summary','draft','polish'])if(result[role+'_model']!=='openai/gpt-6-luna')result[role+'_service']='default';
    if(result.provider==='databricks'){result.web_search=false;result.advanced_models=false;}
    return result;
  }
  function modelChoices() {
    const choices=new Map();
    for(const role of ['summary','draft','polish'])for(const option of form.elements[role+'_model'].options) {
      if(!option.value)continue;
      const key=option.value+'|default';choices.set(key,{id:option.value,service:'default',label:option.textContent.replace(' · Standard / Flex',' Standard')});
      if(option.value==='openai/gpt-6-luna')choices.set(option.value+'|flex',{id:option.value,service:'flex',label:'GPT-6 Luna Flex · 50% off'});
    }
    return choices;
  }
  function commonSelection(value) {
    const choice=modelChoices().get(value);if(!choice)return;
    for(const role of ['summary','draft','polish']) {form.elements[role+'_model'].value=choice.id;form.elements[role+'_service'].value=choice.service;}
  }
  const topicLimit=2000000;
  let countedTopic=null,topicCharacters=0;
  function topicCount() {
    const text=form.elements.topic.value;
    if(text!==countedTopic) {
      countedTopic=text;topicCharacters=0;
      for(const character of text)topicCharacters++;
      let words=0;const tokens=/\S+/gu;while(tokens.exec(text))words++;
      $('generator-topic-count').textContent=words.toLocaleString()+' '+(words===1?'word':'words')+' · '+topicCharacters.toLocaleString()+' characters';
    }
    return topicCharacters;
  }
  let inlineSourceKey='',inlineShown=20;
  function renderInlineSources() {
    const sources=window.NxfloSources.extract(form.elements.topic.value,form.elements.youtube.value);
    const links=[...sources.youtube.map(url=>({url,type:'YouTube'})),...sources.references.map(url=>({url,type:'Reference'}))];
    const key=JSON.stringify(links);if(key!==inlineSourceKey){inlineSourceKey=key;inlineShown=20;}
    $('generator-source-summary').textContent=`Detected sources: ${sources.youtube.length} YouTube · ${sources.references.length} other ${sources.references.length===1?'reference':'references'}`;
    $('generator-inline-sources').replaceChildren(...links.slice(0,inlineShown).map(source=>{
      const item=document.createElement('li'),type=document.createElement('span'),link=document.createElement('a');
      type.textContent=source.type;link.textContent=source.url;link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';item.append(type,link);return item;
    }));
    if(!links.length){const empty=document.createElement('li');empty.textContent='Paste YouTube URLs, web/PDF links or DOI references anywhere in your brief. Repeated links appear once.';$('generator-inline-sources').append(empty);}
    $('generator-more-sources').hidden=inlineShown>=links.length;
    $('generator-more-sources').textContent='Show more sources ('+Math.min(inlineShown,links.length)+' of '+links.length+' shown)';
  }
  function ready() {
    const databricks=form.elements.provider.value==='databricks';
    configured=!!providerSettings[form.elements.provider.value]?.configured;
    $('generator-databricks-model').hidden=!databricks;$('generator-openrouter-model').hidden=databricks;$('generator-advanced-toggle').hidden=databricks;
    form.elements.databricks_model.required=databricks;form.elements.databricks_model.disabled=!databricks;
    form.elements.web_search.disabled=databricks;form.elements.web_budget_usd.disabled=databricks;
    if(databricks){form.elements.web_search.checked=false;form.elements.advanced_models.checked=false;}
    $('generator-provider-status').textContent=(databricks?'Databricks':'OpenRouter')+(configured?' is configured. ':' is not configured on the server. ')+(databricks?'Generation and AI form filling use your configured model. Supplied references and YouTube transcripts are still collected; paid web discovery is disabled.':'Generation uses the selected models. AI form filling uses GPT-6 Luna Flex.');
    const advanced=form.elements.advanced_models.checked;
    $('generator-advanced-models').hidden=!advanced;$('generator-common-model').disabled=advanced;
    if(!advanced)commonSelection($('generator-common-model').value);
    $('generator-page-count').hidden=form.elements.length_mode.value!=='target';
    $('generator-cost-pages').hidden=form.elements.length_mode.value==='target';
    form.elements.pages.required=form.elements.length_mode.value==='target';form.elements.pages.disabled=form.elements.length_mode.value!=='target';form.elements.cost_pages.required=form.elements.length_mode.value!=='target';form.elements.cost_pages.disabled=form.elements.length_mode.value==='target';
    for(const role of ['summary','draft','polish']) {
      const model=form.elements[role+'_model'].value || defaultModels[role+'_model'];
      $('generator-'+role+'-service').hidden=model!=='openai/gpt-6-luna';
      if(model!=='openai/gpt-6-luna')form.elements[role+'_service'].value='default';
    }
    const tooLong=topicCount()>topicLimit;
    $('generator-topic-limit').textContent=tooLong?'Over 2,000,000 characters. Your full pasted text is still here; shorten it before saving.':'Up to 2,000,000 characters. Full text is saved; AI processing is subject to the model’s context limits.';
    $('generator-topic-count').classList.toggle('is-over-limit',tooLong);
    form.elements.topic.setCustomValidity(tooLong?'Brief exceeds 2,000,000 characters. Your full text remains in the box; shorten it before saving.':form.elements.topic.value.trim()?'':'Add a topic or brief to enable generation.');
    const invalid=[];
    for(const field of form.querySelectorAll('input[name],select[name],textarea[name],input[data-team-field]')) {
      const bad=field.willValidate && !field.validity.valid;
      field.closest('label')?.classList.toggle('generator-missing',bad);
      if(bad){field.setAttribute('aria-invalid','true');invalid.push(field.name==='topic'?'topic / brief':field.name?field.name.replaceAll('_',' '):field.dataset.teamField==='email'?'team email':'team name');}else field.removeAttribute('aria-invalid');
      field.closest('label')?.classList.toggle('generator-ai-pending',aiFields.includes(field.name) && !field.value.trim());
    }
    renderInlineSources();
    renderCosts();
    const valid=!invalid.length && loaded && configured && !busy && !uploading && !active;
    $('generator-start').disabled=!valid;
    $('generator-save').disabled=!loaded || busy || !!uploading || tooLong || !!form.querySelector('input[data-team-field]:invalid');
    $('generator-revision').hidden=!parentId;form.elements.version.readOnly=!!parentId;
    if(parentId && !$('generator-revision-base').textContent)$('generator-revision-base').textContent='Your revision is linked to a previously generated document. Review feedback is saved automatically.';
    $('generator-version-help').textContent=parentId?'Assigned automatically when you submit this revision.':'Initial version. Feedback revisions receive the next version automatically.';
    $('generator-start').firstChild.textContent=parentId?'Generate revision ':'Start generate ';
    $('generator-clear-form').disabled=!loaded || !defaults || busy || !!uploading;
    $('generator-fill-form').disabled=!loaded || !form.elements.topic.value.trim() || tooLong || busy || !!uploading || !!active;
    $('generator-ready').textContent=busy?'Preparing document generation…':uploading?'Processing your uploads…':!configured?'Configure the selected provider on the server to enable generation.':invalid.length?'To enable generation, complete the highlighted fields: '+invalid.join(', ')+'.':'Ready. Blank metadata is filled using '+(databricks?'your Databricks model':'GPT-6 Luna Flex')+'. Uploaded source documents are not sent for metadata autofill.';
  }
  function renderCosts() {
    if(!config)return;
    const current=values();
    if(current.provider==='databricks'){
      renderMatrix(current);
      $('generator-pricing-status').textContent='Databricks workspace billing. Endpoint token rates are not configured; OpenRouter prices do not apply.';
      $('generator-model-rates').replaceChildren(...['Summarize evidence','Outline, draft & review','Final polish'].map(label=>{const row=document.createElement('tr'),name=document.createElement('th');name.scope='row';name.textContent=label+' · '+current.databricks_model;row.append(name);for(let i=0;i<2;i++){const cell=document.createElement('td');cell.textContent='Workspace rate';row.append(cell);}return row;}));
      $('generator-cost-total').textContent='Workspace billing';$('generator-cost-assumptions').textContent='USD estimate unavailable until Databricks endpoint input and output rates are supplied. Unknown rates are not treated as free. Paid OpenRouter web discovery is disabled for Databricks.';
      $('generator-pass-costs').replaceChildren();$('generator-cost-breakdown').replaceChildren();return;
    }
    if(!pricing)return;
    $('generator-pricing-status').textContent=(pricing.warning?pricing.warning+' ':'')+'OpenRouter prices · USD · checked '+new Date(pricing.checked_at).toLocaleString()+'.';
    renderMatrix(current);
    const roles=[['Author intent & evidence','summary_model'],['Plan, draft & review','draft_model'],['Polish & publication gate','polish_model']];
    $('generator-model-rates').replaceChildren(...roles.map(([label,key])=>{
      const row=document.createElement('tr'),name=document.createElement('th');name.scope='row';
      const stage=document.createElement('span'),model=document.createElement('small');stage.textContent=label;
      const price=Object.hasOwn(pricing.models,current[key])?pricing.models[current[key]]:null;const service=current[key.replace('_model','_service')];model.textContent=(price?.name || current[key] || 'Select a model')+(service==='flex'?' · Flex · 50% off':'');name.append(stage,model);row.append(name);
      for(const field of ['input','output']) {const cell=document.createElement('td');cell.textContent=price?usd(price[field]*(service==='flex'?.5:1)):'Unavailable';row.append(cell);}
      return row;
    }));
    const observed=observedSources?.key===sourceSignature(current)?observedSources.stats:null;
    const result=window.NxfloCosts.estimate(current,pricing,undefined,observed);
    $('generator-cost-total').textContent=result?'≈ '+usd(result.total):'Unavailable';
    $('generator-pass-costs').replaceChildren();$('generator-cost-breakdown').replaceChildren();
    if(!result){$('generator-cost-assumptions').textContent='Choose models with published token prices and a valid page assumption to calculate an estimate. Unknown model prices are never treated as zero.';return;}
    $('generator-cost-assumptions').textContent=`${result.pages} planning pages · approximately ${result.manuscriptTokens.toLocaleString()} draft tokens · ${result.sourceTokens.toLocaleString()} source tokens · ${result.passes} full review/rewrite ${result.passes===1?'cycle':'cycles'}. ${result.observed?"Uses collected source text and actual summary chunk counts.":"Source estimates include pasted/uploaded text, 6,000 tokens per video or reference link, and search results."} Research fees and Luna Flex notes are included when selected. The US$0.30 limit applies to web research only.${current.revision_parent?' Revision estimates also include the previous manuscript at the planned length and your feedback.':''}`;
    const baseline=window.NxfloCosts.estimate(current,pricing,3,observed);
    $('generator-pass-costs').replaceChildren(...[1,2,3,4].map(passes=>{
      const comparison=window.NxfloCosts.estimate(current,pricing,passes,observed),card=document.createElement('div');
      if(passes===current.review_passes)card.className='is-selected';
      const label=document.createElement('span'),value=document.createElement('strong'),difference=document.createElement('small');
      label.textContent=passes+' '+(passes===1?'pass':'passes');value.textContent=usd(comparison.total);
      difference.textContent=passes===3?'Comparison baseline':baseline.total>0?Math.round(Math.abs(comparison.total-baseline.total)/baseline.total*100)+'% '+(comparison.total<baseline.total?'less':'more')+' than 3':'No token charges';
      card.append(label,value,difference);return card;
    }));
    const rows=result.rows.map(item=>{
      const p=document.createElement('p');p.textContent=`${item.stage}: ${item.input.toLocaleString()} input + ${item.output.toLocaleString()} output tokens ≈ ${usd(item.cost)}`;return p;
    });
    const formula=document.createElement('p');formula.textContent='Cost = (input tokens × input rate + output tokens × output rate) ÷ 1,000,000. About 650 draft tokens per page; one chapter per three pages (2–12 chapters). Evidence notes assume about 250 tokens per source chunk (1,000–40,000 total); outline and per-chapter review outputs use 1,200 tokens per call. Repeated context and prompt allowances are included. Catalog long-context rates apply when a modeled call reaches a listed threshold.';
    $('generator-cost-breakdown').replaceChildren(...rows,formula);
  }
  function renderMatrix(current) {
    if(current.provider==='databricks'){
      matrixSignature='';const row=document.createElement('tr');row.className='is-selected';const name=document.createElement('th');name.scope='row';name.style.overflowWrap='anywhere';name.textContent=current.databricks_model || 'Configure a Databricks model';row.append(name);
      for(let i=0;i<2;i++){const cell=document.createElement('td');cell.textContent='Workspace';row.append(cell);}$('generator-price-matrix').replaceChildren(row);return;
    }
    const matrix=$('generator-price-matrix');const focused=matrix.contains(document.activeElement)?document.activeElement.closest('tr')?.dataset.model:null;
    const cost=(choice,field)=>Object.hasOwn(pricing.models,choice.id)?pricing.models[choice.id][field]*(choice.service==='flex'?.5:1):Infinity;
    const ranked=[...modelChoices()].sort(([,a],[,b])=>cost(a,'input')-cost(b,'input') || cost(a,'output')-cost(b,'output') || a.label.localeCompare(b.label));
    const signature=JSON.stringify([ranked.map(([key,choice])=>[key,choice.label,cost(choice,'input'),cost(choice,'output')]),['summary','draft','polish'].map(role=>[current[role+'_model'],current[role+'_service']])]);
    if(signature===matrixSignature)return;matrixSignature=signature;
    $('generator-price-matrix').replaceChildren(...ranked.map(([key,choice])=>{
      const row=document.createElement('tr'),name=document.createElement('th');name.scope='row';
      const selected=['summary','draft','polish'].some(role=>current[role+'_model']===choice.id && current[role+'_service']===choice.service);
      row.classList.toggle('is-selected',selected);row.dataset.model=key;
      const pick=button(choice.label,()=>{form.elements.advanced_models.checked=false;$('generator-common-model').value=key;commonSelection(key);changed();message(choice.label+' selected in the model dropdown for all stages.');});
      pick.setAttribute('aria-label','Use '+choice.label+' for all stages');pick.setAttribute('aria-pressed',String(selected));name.append(pick);row.append(name);
      row.addEventListener('click',event=>{if(!event.target.closest('button'))pick.click();});
      const price=Object.hasOwn(pricing.models,choice.id)?pricing.models[choice.id]:null;
      for(const field of ['input','output']){const cell=document.createElement('td');cell.textContent=price?usd(price[field]*(choice.service==='flex'?.5:1)):'Unavailable';row.append(cell);}
      return row;
    }));
    if(focused)[...matrix.children].find(row=>row.dataset.model===focused)?.querySelector('button')?.focus({preventScroll:true});
  }
  async function loadPrices(refresh=false) {
    $('generator-refresh-prices').disabled=true;
    try {
      pricing=await request('/pricing'+(refresh?'?refresh=1':''));
      $('generator-pricing-status').textContent=(pricing.warning?pricing.warning+' ':'')+'OpenRouter prices · USD · checked '+new Date(pricing.checked_at).toLocaleString()+'. Base rates shown; long-context tiers apply to estimates where relevant.';
      renderCosts();
    }catch(error){$('generator-pricing-status').textContent='Prices unavailable. '+error.message;}
    finally{$('generator-refresh-prices').disabled=false;}
  }
  function fileList() {
    $('generator-document-list').replaceChildren(...config.documents.map((doc,i)=>{
      const li=document.createElement('li'),name=document.createElement('span'),role=document.createElement('select');
      li.className='generator-source-row';name.textContent=doc.name+' · '+doc.text.length.toLocaleString()+' characters';
      role.className='generator-source-role';role.setAttribute('aria-label','Role for '+doc.name);
      role.replaceChildren(new Option('Author material','author'),new Option('Reference evidence','reference'));role.value=doc.role || 'author';
      role.addEventListener('change',()=>{doc.role=role.value;changed();});
      li.append(name,role,button('Remove',()=>{config.documents.splice(i,1);fileList();changed();}));return li;
    }));
    $('generator-image-list').replaceChildren(...config.illustrations.map((_,i)=>{
      const row=document.createElement('div'),name=document.createElement('span');name.textContent='Supporting image '+(i+1);row.append(name,button('Remove',()=>{config.illustrations.splice(i,1);fileList();changed();}));return row;
    }));
    $('generator-logo-preview').hidden=!config.logo;
    $('generator-logo-empty').hidden=!!config.logo;$('generator-logo-help').hidden=!!config.logo;
    $('generator-logo-drop').classList.toggle('has-logo',!!config.logo);
    $('generator-logo-drop').setAttribute('aria-label',config.logo?'Replace company logo':'Upload company logo');
    const logo=$('generator-logo-preview').querySelector('img');if(config.logo)logo.src=config.logo;else logo.removeAttribute('src');
  }
  function teamOptions(selected) {
    const select=$('generator-prepared-team');
    select.replaceChildren(new Option('No team attribution',''),...config.teams.map(team=>new Option(team.name || 'New team',team.id)));select.value=selected;
  }
  function renderTeams() {
    teamOptions(config.prepared_team);
    $('generator-team-list').replaceChildren(...config.teams.map(team=>{
      const row=document.createElement('div');row.className='generator-team-row';row.dataset.team=team.id;
      for(const [key,label] of [['name','Team name'],['email','Contact email']]){
        const wrap=document.createElement('label'),input=document.createElement('input');wrap.append(document.createTextNode(label));
        input.type=key==='email'?'email':'text';input.maxLength=key==='email'?254:200;input.required=true;input.value=team[key];input.dataset.teamField=key;input.autocomplete=key==='email'?'email':'organization';
        input.addEventListener('input',()=>{team[key]=input.value;if(key==='name')teamOptions(form.elements.prepared_team.value);});wrap.append(input);row.append(wrap);
      }
      row.append(button('Remove team',()=>{config.teams=config.teams.filter(item=>item.id!==team.id);config.prepared_team=form.elements.prepared_team.value===team.id?'':form.elements.prepared_team.value;renderTeams();changed();}));return row;
    }));
    $('generator-add-team').disabled=config.teams.length>=20;
  }
  $('generator-add-team').addEventListener('click',()=>{
    if(!loaded || config.teams.length>=20)return;
    const team={id:'team_'+crypto.randomUUID(),name:'',email:''};config.teams.push(team);config.prepared_team=team.id;renderTeams();$('generator-manage-teams').open=true;changed();$('generator-team-list').lastElementChild.querySelector('input').focus();
  });
  function populate(next) {
    config=structuredClone(next);parentId=config.revision_parent || null;
    for(const role of ['summary','draft','polish'])config[role+'_model']=String(config[role+'_model'] || defaultModels[role+'_model']).replace(/:batch$/,'');
    const configuredModel=providerSettings.databricks.model || '';
    form.elements.databricks_model.replaceChildren(new Option(configuredModel || 'Configure DATABRICKS_MODEL',configuredModel));
    if(!config.databricks_model)config.databricks_model=configuredModel;
    for(const [key,value] of Object.entries(config)) {
      const field=form.elements[key];if(!field || assetKeys.includes(key))continue;
      if(checks.includes(key))field.checked=value;else {if(key.endsWith('_model') && ![...field.options].some(option=>option.value===value))field.add(new Option(value+' · saved model',value));field.value=value;}
    }
    const common=$('generator-common-model');common.replaceChildren(...[...modelChoices()].map(([key,choice])=>new Option(choice.label,key)));
    common.value=form.elements.draft_model.value+'|'+(form.elements.draft_service.value || 'default');
    if(!common.value)common.selectedIndex=0;
    renderTeams();fileList();ready();
  }
  function renderJobs(jobs) {
    const content=jobs.map(job=>{
      const row=document.createElement('article');row.className='generator-job';
      const copy=document.createElement('div'),title=document.createElement('strong'),meta=document.createElement('small');
      title.textContent=job.title || 'Untitled document';meta.textContent='v'+job.version+' · '+job.status+' · '+new Date(job.created_at).toLocaleString();copy.append(title,meta);
      if(job.error) {const error=document.createElement('small');error.textContent=job.error;copy.append(error);}
      const actions=document.createElement('div');actions.className='generator-actions';
      if(['ready','needs_review'].includes(job.status)){for(const kind of ['pdf','html']){const link=document.createElement('a');link.className='admin-button';link.textContent='Download '+kind.toUpperCase();link.href=endpoint+'/jobs/'+job.id+'/download/'+kind;actions.append(link);}}
      if(['queued','running','awaiting_html_review','failed','cancelled','ready','needs_review'].includes(job.status))actions.append(button('View progress',()=>watch(job.id)));
      if(job.status==='awaiting_html_review')actions.append(button('Preview HTML',async()=>{await watch(job.id);$('generator-html-review').scrollIntoView({behavior:'smooth',block:'start'});}));
      if(job.can_resume)actions.append(button('Resume generation',()=>resume(job.id).catch(showError)));
      actions.append(button(['ready','needs_review'].includes(job.status)?'Revise document':'Use configuration',()=>loadVersion(job.id).catch(showError)));
      row.append(copy,actions);return row;
    });
    if(!content.length) { const p=document.createElement('p');p.textContent='No generated documents yet. Start your first document above.';content.push(p); }
    $('generator-jobs').replaceChildren(...content);
  }
  async function loadVersion(id) {
    if(busy || active) return message('Wait for the current generation to finish.');
    const job=await request('/jobs/'+id);
    const completed=['ready','needs_review'].includes(job.status),teams=config.teams;
    const selected=teams.some(team=>team.id===job.config.prepared_team)?job.config.prepared_team:'';
    populate({...job.config,teams,prepared_team:selected,revision_parent:completed?id:'',feedback:'',change_summary:''});history.replaceState(null,'','admin.html?job='+id);
    const parts=job.config.version.match(/^(\d+(?:\.\d+)*)\.(\d+)$/);
    if(completed)form.elements.version.value=parts?parts[1]+'.'+(Number(parts[2])+1):'1.1';
    $('generator-revision-base').textContent=completed?'Revising '+(job.config.title || 'document')+' · version '+job.config.version+'. Download and review the PDF, then enter your feedback below.':'';
    if(completed){clearTimeout(pollTimer);watched=id;workflow(job);}
    dirty=true;await save();message(completed?'Ready for your feedback. The next version will be assigned automatically. Earlier output is preserved.':'Configuration loaded.');
    (completed?$('generator-revision'):$('generator-editor')).scrollIntoView({behavior:'smooth',block:'start'});
    if(completed)form.elements.feedback.focus();
  }

  async function load(refresh=false) {
    if(loading || !csrf)return;
    loading=true;
    try {
      const data=await request();providerSettings=data.providers || {openrouter:{configured:data.configured},databricks:{configured:false,model:''}};configured=data.configured;defaults=data.defaults || defaults;
      if(!loaded) {revision=data.revision;loaded=true;populate(data.config);$('generator-save-state').textContent=revision?'Saved configuration':'New configuration';}
      $('generator-key-status').textContent=(providerSettings.databricks.configured?'Databricks configured. ':'Databricks not configured. ')+(providerSettings.openrouter.configured?'OpenRouter configured. ':'OpenRouter not configured. ')+(data.worker_online?'Generation worker online.':'Generation worker offline.');
      renderJobs(data.jobs || []);
      if(!pricing)await loadPrices();
      if(!refresh)message('Configuration loaded. Changes are saved automatically.');
      const running=(data.jobs || []).find(job=>['queued','running'].includes(job.status)) || (data.jobs || []).find(job=>job.status==='awaiting_html_review');
      if(running && (running.status==='awaiting_html_review'?watched!==running.id:active!==running.id))watch(running.id);
      const requested=new URLSearchParams(location.search).get('job');if(requested && !watched)watch(requested);
      ready();
    }catch(error){showError(error);}finally{loading=false;}
  }
  async function save() {
    clearTimeout(saveTimer);
    if(topicCount()>topicLimit)throw new Error('Brief exceeds 2,000,000 characters. Your full text remains in the box; shorten it before saving.');
    if(!loaded || uploading)return;
    if(saving) {await saving;if(dirty)return save();return;}
    config=values();const snapshot=structuredClone(config);dirty=false;
    $('generator-save-state').textContent='Saving…';
    saving=request('',json('PUT',{config:snapshot,revision}));
    try {const result=await saving;revision=result.revision;$('generator-save-state').textContent='Saved';}
    catch(error) {dirty=true;$('generator-save-state').textContent='Not saved';showError(error);throw error;}
    finally {saving=null;}
  }
  function changed() {
    if(!loaded)return;dirty=true;$('generator-save-state').textContent='Unsaved changes';ready();
    clearTimeout(saveTimer);if(!busy && topicCount()<=topicLimit && !form.querySelector('input[data-team-field]:invalid'))saveTimer=setTimeout(()=>save().catch(()=>{}),1000);
  }
  function showError(error) {message(error.message);if(error.status===401 || error.status===403){clearTimeout(pollTimer);active=null;csrf='';loaded=false;}}
  function renderTiming(){
    const job=timedJob,now=job?(job.server_time || Date.now()/1000)+(performance.now()-timingReceived)/1000:Date.now()/1000;
    if(job)renderStepTimes(job,now);
    const timing=window.NxfloTiming.estimate(job,now);$('generator-timing').hidden=!timing;if(!timing)return;
    $('generator-elapsed').textContent=window.NxfloTiming.duration(timing.elapsed);
    $('generator-timing').classList.toggle('is-overdue',timing.active && timing.overTarget);
    const minutes=n=>Math.max(1,Math.ceil(n/60)),clock=n=>new Date(n*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
    let remaining='—',finish='—',note='';
    if(timing.kind==='batch'){
      remaining='Provider queue · unknown';finish='Not available for Batch';
      note='Batch has no 10-minute guarantee. '+(timing.deadline?'This stage’s provider deadline: '+new Date(timing.deadline*1000).toLocaleString()+'. ':'')+'The whole-document finish time is not yet predictable.';
    }else if(timing.kind==='offline'){
      remaining='Waiting for worker';finish='Unavailable';note='Worker heartbeat missing. Saved progress is preserved.';
    }else if(timing.kind==='stopped'){
      remaining=['ready','needs_review'].includes(job.status)?'Complete':'Paused';finish=['ready','needs_review'].includes(job.status)?clock(Date.parse(job.updated_at)/1000):job.status==='awaiting_html_review'?'Continue after HTML review':'Resume to continue';note='Elapsed time includes provider queues and interruptions.';
    }else{
      remaining=minutes(timing.low)+'–'+minutes(timing.high)+' min'+(timing.kind==='flex'?' + possible queue':'');
      finish=timing.kind==='flex'?'Depends on Flex capacity':clock(now+timing.low)+'–'+clock(now+timing.high);
      note='Planning estimate based on source size, chapters and review passes; it updates with progress. '+(timing.kind==='flex'?'Flex has no guaranteed queue time. ':'')+(timing.overTarget?'The 10-minute target has been exceeded; work is still active.':'Target: 10 minutes. Provider response times can extend this.');
    }
    $('generator-remaining').textContent=remaining;$('generator-finish').textContent=finish;$('generator-timing-note').textContent=note;
  }
  setInterval(renderTiming,1000);
  function renderStepTimes(job,now){
    for(const li of $('generator-steps').children){
      const detail=window.NxfloTiming.step(job,li.dataset.step,now),time=li.querySelector('.generator-step-elapsed');
      if(time){time.hidden=!detail.active && !detail.complete && detail.elapsed===0;time.textContent='Elapsed '+window.NxfloTiming.duration(detail.elapsed);}
      const dot=li.querySelector('.generator-step-dot');
      if(detail.active && dot){
        dot.style.setProperty('--step-pct',(detail.percentage ?? 0)+'%');dot.textContent=detail.percentage==null?'…':detail.percentage+'%';
        if(detail.percentage!=null)dot.setAttribute('aria-valuenow',detail.percentage);else dot.removeAttribute('aria-valuenow');
        dot.setAttribute('aria-valuetext',detail.total!=null?detail.completed+' of '+detail.total+' '+detail.unit+' complete':'In progress; exact percentage unavailable');
        const count=li.querySelector('.generator-step-count');if(count){count.hidden=detail.total==null;count.textContent=detail.total==null?'':detail.completed+' / '+detail.total+' '+detail.unit;}
      }
    }
  }
  function renderChef(job){
    const active=['queued','running'].includes(job.status),done=['ready','needs_review'].includes(job.status),preparing=['collect','summarize','outline'].includes(job.step);
    const phase=done?'done':active && job.worker_online===false?'paused':active?(preparing?'preparing':'cooking'):['failed','cancelled','awaiting_html_review'].includes(job.status)?'paused':'idle';
    $('generator-chef').dataset.phase=phase;
    const title=phase==='done'?'All done!':phase==='preparing'?'Preparing the ingredients…':phase==='cooking'?'Cooking your document…':phase==='paused'?'Taking a little break':'Ready when you are';
    if($('generator-chef-title').textContent!==title)$('generator-chef-title').textContent=title;
    $('generator-chef-caption').textContent=done?'Your document is ready for your review.':phase==='paused'?'Your saved work is safe.':active?(steps.find(([key])=>key===job.step)?.[1] || 'Getting everything ready'):'A little care in every document.';
  }
  function workflow(job={status:'idle',step:'',events:[],message:'Start generation to follow the actual workflow.'}) {
    timedJob=job;timingReceived=performance.now();renderTiming();
    renderChef(job);
    if(job.source_metrics && job.config)observedSources={key:sourceSignature(job.config),stats:job.source_metrics};
    const complete=new Set(job.events.filter(event=>event.status==='complete').map(event=>event.step));
    const running=['queued','running'].includes(job.status),done=['ready','needs_review'].includes(job.status);
    document.querySelector('.generator-layout').classList.toggle('is-running',running);
    $('generator-workflow-status').textContent=(job.worker_online===false && running?'Worker heartbeat is missing; live progress is unavailable. ':'')+(job.message || job.error || job.status);
    const intentLabels={summarize:'Preserve intent & evidence',outline:'Plan structure & examples',review:'Review intent & accuracy',assemble:'Quality gate & document layout'};
    const reviewJump=$('generator-review-jump'),reviewFocused=document.activeElement===reviewJump;reviewJump.remove();
    $('generator-steps').replaceChildren(...steps.map(([key,label],i)=>{
      if(job.pipeline_version===2 || job.status==='idle')label=intentLabels[key] || label;
      const currentState=job.worker_online===false?'stalled':job.wait_state?.label || job.batch_wait || job.recovery?.retry_at?'waiting':job.status==='queued'?'queued':'running';
      const li=document.createElement('li');li.dataset.step=key;li.dataset.state=job.status==='awaiting_html_review' && key==='html_review'?'review':running && job.step===key?currentState:job.status==='failed' && job.step===key?'failed':complete.has(key)?'complete':'pending';
      const dot=document.createElement('span');dot.className='generator-step-dot';dot.setAttribute('aria-hidden','true');dot.textContent=complete.has(key)?'✓':String(i+1).padStart(2,'0');
      if(running && job.step===key){dot.classList.add('is-meter');dot.removeAttribute('aria-hidden');dot.setAttribute('role','progressbar');dot.setAttribute('aria-label',label+' progress');dot.setAttribute('aria-valuemin','0');dot.setAttribute('aria-valuemax','100');}
      const copy=document.createElement('div');copy.className='generator-step-copy';const name=document.createElement('strong'),state=document.createElement('small');name.textContent=label;
      const passes=job.events.filter(event=>event.step===key && event.status==='complete').length;
      state.textContent=li.dataset.state+(passes>1?' · '+passes:'');if(done && key==='rewrite' && !complete.has(key))state.textContent='Not needed';
      const elapsed=document.createElement('small');elapsed.className='generator-step-elapsed';elapsed.hidden=true;
      const count=document.createElement('small');count.className='generator-step-count';count.hidden=true;
      copy.append(name,state,elapsed,count);li.append(dot,copy);return li;
    }));
    $('generator-steps').querySelector('[data-step=html_review] .generator-step-copy').append(reviewJump);
    if(reviewFocused)reviewJump.focus({preventScroll:true});
    renderStepTimes(job,job.server_time || Date.now()/1000);
    const wait=job.wait_state || {};
    $('generator-wait-status').hidden=!running || (!wait.label && !job.batch_wait);
    $('generator-wait-status').textContent=wait.label?wait.label+' · '+Math.max(0,wait.elapsed_seconds || 0)+'s elapsed · '+wait.limit_seconds+'s maximum. Waiting for a complete response.':'';
    if(!wait.label && job.batch_wait){
      const batch=job.batch_wait,counts=batch.request_counts || {},now=job.server_time || Date.now()/1000;
      const elapsed=batch.created_at?' · '+Math.floor(Math.max(0,now-batch.created_at)/3600)+'h '+Math.floor(Math.max(0,now-batch.created_at)%3600/60)+'m elapsed':'';
      const deadline=batch.expires_at?' Provider deadline: '+new Date(batch.expires_at*1000).toLocaleString()+'.':'';
      const checked=batch.checked_at?' Last checked '+Math.max(0,Math.floor(now-batch.checked_at))+'s ago.':'';
      $('generator-wait-status').textContent='OpenRouter Batch · '+batch.stage+' · '+(batch.status || 'submitted')+(counts.total?' · '+(counts.completed || 0)+' / '+counts.total+' requests complete'+(counts.failed?' · '+counts.failed+' failed':''):'')+elapsed+'.'+deadline+checked+' Progress is checked automatically every minute. Each Batch stage can take up to 24 hours; you can close this page.';
    }
    $('generator-progress').hidden=job.status==='idle';$('generator-progress').max=steps.length;$('generator-progress').value=done?steps.length:Math.min(steps.length-1,complete.size);
    const reviewing=job.status==='awaiting_html_review';
    $('generator-html-review').hidden=!reviewing;$('generator-review-jump').hidden=!reviewing;
    if(reviewing){
      const url=endpoint+'/jobs/'+job.id+'/download/html';
      $('generator-html-open').href=url+'?view=1';$('generator-html-download').href=url;
      if($('generator-html-frame').getAttribute('src')!==url+'?view=1')$('generator-html-frame').src=url+'?view=1';
    }else{$('generator-html-frame').removeAttribute('src');$('generator-html-status').textContent='';}
    $('generator-result').hidden=!done;$('generator-cancel').hidden=!running;
    const recovery=job.recovery || {},retryWait=recovery.retry_at?Math.max(0,Math.ceil(recovery.retry_at-(job.server_time || Date.now()/1000))):0;
    $('generator-resume').hidden=!recovery.can_resume || (running && (!job.batch_wait || recovery.retry_at));
    $('generator-resume').textContent=running?'Check batch now':'Resume generation';
    $('generator-recovery-status').hidden=!recovery.blocked_reason && !recovery.retry_at && !['failed','cancelled'].includes(job.status);
    $('generator-recovery-status').textContent=recovery.blocked_reason || (recovery.retry_at?'Automatic recovery · attempt '+recovery.attempts+' of 3 · '+(retryWait?'retry in '+retryWait+'s.':'retry due now.')+' Completed stages and saved responses will be reused.':recovery.can_resume?'Resume continues this version from saved progress. Completed work and existing Batch requests are reused.':'');
    $('generator-cost-actual').textContent=job.id?(job.config?.provider==='databricks'?'Databricks usage is billed in your workspace; USD charges are not returned by this endpoint.':job.cost==null?'Model cost: not yet reported by OpenRouter.':'Reported usage cost so far (OpenRouter + BYOK): '+usd(Number(job.cost)))+(job.unreported_calls?' · Some completed charges have not been reported.':'')+(job.warnings?.length?' · '+job.warnings.length+' review/source warnings.':''):'';
    const budget=job.web_budget;
    $('generator-web-spend').textContent=budget?'Web research: '+usd(budget.reported)+' reported · '+usd(budget.limit)+' limit for new research'+(budget.historical?' · Earlier native-search charges predate this limit.':budget.reserved?' · '+usd(budget.reserved)+' reserved as a conservative maximum; this is not a charge.':''):'';
    $('generator-billing-details').hidden=!job.billing?.length;
    $('generator-billing-rows').replaceChildren(...(job.billing || []).map(row=>{const p=document.createElement('p');p.textContent=job.config?.provider==='databricks'?row.stage+': Databricks workspace billing'+(row.input_tokens!=null?' · '+row.input_tokens+' input tokens · '+row.output_tokens+' output tokens':''):row.stage+': OpenRouter '+(row.credit_cost==null?'not reported':usd(row.credit_cost))+' · BYOK provider '+(row.is_byok===false?'not applicable':row.provider_cost==null?'not reported':usd(row.provider_cost))+' · Total '+(row.total==null?'not yet verified':usd(row.total))+(row.generation_id?' · Billing reference '+row.generation_id:'');p.style.overflowWrap='anywhere';return p;}));
    $('generator-warnings').replaceChildren(...(job.warnings || []).map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));
    if(done){$('generator-download-pdf').href=endpoint+'/jobs/'+job.id+'/download/pdf';$('generator-download-html').href=endpoint+'/jobs/'+job.id+'/download/html';}
  }
  function watch(id) {
    clearTimeout(pollTimer);watched=id;
    const poll=async()=>{
      try {
        const job=await request('/jobs/'+id);if(watched!==id)return;
        active=['queued','running'].includes(job.status)?id:null;workflow(job);ready();
        if(active)pollTimer=setTimeout(poll,2000);else {await load(true);message(job.message || job.error || 'Document generation '+job.status+'.');}
      }catch(error){showError(error);if(csrf && watched===id)pollTimer=setTimeout(poll,5000);}
    };return poll();
  }
  $('generator-revise-current').addEventListener('click',()=>{if(watched)loadVersion(watched).catch(showError);});
  $('generator-approve-html').addEventListener('click',async()=>{
    if(!watched)return;
    const id=watched,button=$('generator-approve-html');button.disabled=true;
    try{await request('/jobs/'+id+'/approve-html',json('POST',{}));watch(id);message('HTML approved. Continuing to PDF export.');}
    catch(error){$('generator-html-status').textContent=error.message;showError(error);}
    finally{button.disabled=false;}
  });
  async function resume(id) {
    $('generator-resume').disabled=true;
    try{await request('/jobs/'+id+'/resume',json('POST',{}));watch(id);message('Continuing from saved progress. Existing requests and completed responses are reused.');}
    finally{$('generator-resume').disabled=false;}
  }
  $('generator-resume').addEventListener('click',()=>{if(watched)resume(watched).catch(showError);});
  $('generator-cancel').addEventListener('click',async()=>{
    if(!active || !confirm('Cancel this generation? Provider requests already submitted may still be charged.'))return;
    try{await request('/jobs/'+active+'/cancel',json('POST',{}));watch(active);}catch(error){showError(error);}
  });
  async function image(file) {
    if(!['image/png','image/jpeg','image/webp'].includes(file.type) || file.size>2*1024*1024)throw new Error('Choose a PNG, JPEG or WebP image under 2 MB.');
    return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Image could not be read'));reader.readAsDataURL(file);});
  }
  async function upload(action,input) {
    if(!loaded)return;clearTimeout(saveTimer);uploading++;ready();
    try{await action();dirty=true;fileList();message('Upload ready. Saving configuration…');}
    catch(error){showError(error);}finally{uploading--;input.value='';ready();if(dirty)save().catch(()=>{});}
  }
  $('generator-more-sources').addEventListener('click',()=>{inlineShown+=20;renderInlineSources();});
  $('generator-common-model').addEventListener('change',()=>{commonSelection($('generator-common-model').value);changed();});
  form.elements.document_intent.addEventListener('change',()=>{
    const labels={research_report:'Research report',product_concept:'White paper',technical_paper:'Technical paper'};
    if(labels[form.elements.document_intent.value])form.elements.report_type.value=labels[form.elements.document_intent.value];
    changed();
  });
  form.addEventListener('input',changed);form.addEventListener('change',changed);
  $('generator-save').addEventListener('click',()=>save().then(()=>message('Configuration saved.')).catch(()=>{}));
  async function fillBlankMetadata() {
    if(dirty || saving)await save();
    const input=values();
    if(!aiFields.some(key=>!input[key].trim()) && input.release_date && input.version){if(dirty || saving)await save();return [];}
    message('AI is filling blank details from your typed brief. Existing entries will be preserved…');
    const metadataInput=Object.fromEntries(['provider','databricks_model','document_intent','company','title','topic','report_type','credits','questions','release_date','version'].map(key=>[key,input[key]]));
    const result=await request('/autofill',json('POST',{config:metadataInput}));
    if(form.elements.topic.value.trim()!==input.topic.trim())throw new Error('Your brief changed while AI was working. Try again to use the updated brief.');
    const applied=[];
    for(const [key,value] of Object.entries(result.updates))if(form.elements[key] && !form.elements[key].value.trim()){form.elements[key].value=value;applied.push(key);}
    dirty=true;await save();return applied;
  }
  $('generator-fill-form').addEventListener('click',async()=>{
    if(!loaded || !form.elements.topic.value.trim() || busy || uploading || active)return;
    busy=true;clearTimeout(saveTimer);ready();$('generator-fill-form').textContent='Filling…';
    $('generator-fill-status').textContent='AI is filling blank details from your brief. You can keep editing; existing entries will be preserved.';
    try {
      const applied=await fillBlankMetadata();
      const status=applied.length?'Blank details filled and saved. Review the form below and fine-tune anything before generating.':'The form already has its details filled. You can fine-tune them directly, or clear a field and use AI again.';
      $('generator-fill-status').textContent=status;message(status);
    }catch(error){$('generator-fill-status').textContent=error.message;showError(error);}
    finally{busy=false;$('generator-fill-form').textContent='Fill form with AI';ready();}
  });
  $('generator-clear-form').addEventListener('click',async()=>{
    if(!loaded || !defaults || busy || uploading || !confirm('Clear document details, research text, source uploads and supporting images? Your company name, logo, website, team contacts, previous documents and any running generation will be kept.'))return;
    busy=true;clearTimeout(saveTimer);ready();
    try{
      if(saving)await saving;
      const identity=values();form.reset();populate({...structuredClone(defaults),provider:identity.provider,databricks_model:identity.databricks_model,company:identity.company,logo:identity.logo,website:identity.website,teams:identity.teams,prepared_team:identity.prepared_team,title:'',credits:'',topic:'',questions:'',release_date:'',version:'',youtube:'',documents:[],illustrations:[]});
      parentId=null;dirty=true;await save();$('generator-fill-status').textContent='Form cleared. Enter a new topic and brief, then use AI to fill the details.';message('Form cleared and saved. Company branding, team contacts and previous documents are preserved.');form.elements.topic.focus();
    }catch(error){showError(error);}finally{busy=false;ready();}
  });
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(!form.reportValidity() || active || uploading || busy)return;
    busy=true;clearTimeout(saveTimer);ready();message('Saving configuration and starting document generation…');
    try{
      await save();await fillBlankMetadata();
      const result=await request('/jobs',json('POST',{config:values(),parent_id:parentId}));
      form.elements.version.value=result.version;dirty=true;save().catch(showError);active=result.id;watch(result.id);history.replaceState(null,'','admin.html?job='+result.id);message('Generation queued. You can leave this page and return to follow progress.');
    }catch(error){showError(error);}finally{busy=false;ready();}
  });
  $('generator-logo').addEventListener('change',event=>upload(async()=>{const file=event.target.files[0];if(file)config.logo=await image(file);},event.target));
  const logoDrop=$('generator-logo-drop');
  logoDrop.addEventListener('click',()=>$('generator-logo').click());
  for(const name of ['dragenter','dragover'])logoDrop.addEventListener(name,event=>{event.preventDefault();logoDrop.classList.add('is-dragging');});
  for(const name of ['dragleave','drop'])logoDrop.addEventListener(name,event=>{event.preventDefault();logoDrop.classList.remove('is-dragging');});
  logoDrop.addEventListener('drop',event=>upload(async()=>{
    const files=[...(event.dataTransfer?.files || [])];if(files.length!==1)throw new Error('Drop one company logo at a time.');
    config.logo=await image(files[0]);
  },$('generator-logo')));
  $('generator-illustrations').addEventListener('change',event=>upload(async()=>{const files=[...event.target.files];if(files.length+config.illustrations.length>4)throw new Error('Use at most four supporting images.');const results=await Promise.all(files.map(image));config.illustrations.push(...results);},event.target));
  $('generator-documents').addEventListener('change',event=>upload(async()=>{
    const files=[...event.target.files];if(files.length+config.documents.length>10)throw new Error('Use at most ten source documents.');
    for(const file of files){if(file.size>8*1024*1024)throw new Error('Documents must be under 8 MB.');const body=new FormData();body.append('file',file);const doc=await request('/extract',{method:'POST',body});config.documents.push(doc);}
  },event.target));
  $('generator-refresh-prices').addEventListener('click',()=>loadPrices(true));
  $('generator-refresh').addEventListener('click',()=>load(true));
  window.addEventListener('nxflo-admin-tab',event=>{if(event.detail==='generator-tab')load();});
  window.addEventListener('nxflo-owner-session',event=>{csrf=event.detail.csrf;});
  window.addEventListener('nxflo-session-ended',()=>{csrf='';loaded=false;config=null;active=null;watched=null;timedJob=null;renderTiming();$('generator-editor').hidden=false;$('generator-logo-preview').querySelector('img').removeAttribute('src');$('generator-logo-preview').hidden=true;$('generator-logo-empty').hidden=false;$('generator-logo-help').hidden=false;logoDrop.classList.remove('has-logo');logoDrop.setAttribute('aria-label','Upload company logo');clearTimeout(pollTimer);clearTimeout(saveTimer);form.reset();$('generator-jobs').replaceChildren();$('generator-html-review').hidden=true;$('generator-review-jump').hidden=true;$('generator-html-frame').removeAttribute('src');});
  window.addEventListener('beforeunload',event=>{if(dirty || saving || uploading){event.preventDefault();event.returnValue='';}});
  workflow();

})();
