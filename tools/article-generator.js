(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const endpoint = '/bms_integration_hub/api/admin/generator';
  const form = $('generator-form');
  const steps = [['collect','Collect sources'],['summarize','Summarize evidence'],['outline','Plan chapters & contents'],['draft','Draft chapters'],['review','Review evidence & gaps'],['rewrite','Refine the draft'],['polish','Final editorial polish'],['charts','Draw charts & graphs'],['assemble','Assemble the document'],['html_review','Preview HTML & continue'],['pdf','Export PDF'],['deliver','Ready for your review']];
  let csrf='', revision=0, config=null, configured=false, loaded=false, loading=false, active=null, pollTimer, saveTimer, saving=null, busy=false, uploading=0, parentId=null, defaults=null, watched=null, dirty=false;
  const checks=['toc','charts','images','graphics','advanced_models','version_override'];
  const numeric=['pages','review_passes','cost_pages'];
  const defaultModels={summary_model:'openai/gpt-6-luna',draft_model:'openai/gpt-6-luna',polish_model:'openai/gpt-6-luna'};
  const aiFields=['company','title'];
  let focusedJob=null,libraryDocuments=[],expandedDocumentId=null,failureKey='';
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
    const result={...config,revision_parent:parentId || '',youtube:'',documents:[],questions:'',web_search:false,web_budget_usd:0};
    for(const [key,value] of new FormData(form)) if(!assetKeys.includes(key)) result[key]=numeric.includes(key)?Number(value):value;
    for(const key of checks) result[key]=form.elements[key].checked;
    if(result.length_mode!=='target' && (!Number.isInteger(result.pages) || result.pages<1))result.pages=12;
    if(result.length_mode==='target' && (!Number.isInteger(result.cost_pages) || result.cost_pages<1))result.cost_pages=12;
    for(const [key,model] of Object.entries(defaultModels))result[key]=String(result[key] || model);
    for(const role of ['summary','draft','polish'])if(result[role+'_model']!=='openai/gpt-6-luna')result[role+'_service']='default';
    if(!result.version_override && !parentId)result.version='1.0';
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
    const sources=window.NxfloSources.extract(form.elements.topic.value,'');
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
    if(databricks)form.elements.advanced_models.checked=false;
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
    $('generator-revision').hidden=!parentId;form.elements.version.readOnly=!form.elements.version_override.checked;
    if(!form.elements.version_override.checked && !parentId)form.elements.version.value='1.0';
    $('generator-version-display').textContent=form.elements.version.value || '1.0';
    $('generator-version-mode').textContent=form.elements.version_override.checked?'manual override':'automatic';
    if(parentId && !$('generator-revision-base').textContent)$('generator-revision-base').textContent='Your revision is linked to a previously generated document. Review feedback is saved automatically.';
    $('generator-version-help').textContent=parentId?'The next available version adds 0.1. Expand and enable the override to assign a version yourself.':'Starts at 1.0. Each revision adds 0.1 automatically. Enable the override to assign a version yourself.';
    $('generator-start').firstChild.textContent=parentId?'Generate revision ':'Start generate ';
    $('generator-clear-form').disabled=!loaded || !defaults || busy || !!uploading;
    $('generator-new-document').disabled=$('generator-clear-form').disabled;
    $('generator-fill-form').disabled=!loaded || !form.elements.topic.value.trim() || tooLong || busy || !!uploading || !!active;
    $('generator-ready').textContent=busy?'Preparing document generation…':uploading?'Processing your uploads…':!configured?'Configure the selected provider on the server to enable generation.':invalid.length?'To enable generation, complete the highlighted fields: '+invalid.join(', ')+'.':'Ready. Blank metadata is filled using '+(databricks?'your Databricks model':'GPT-6 Luna Flex')+'. Uploaded source documents are not sent for metadata autofill.';
  }
  function renderCosts() {
    if(!config)return;
    const current=values();
    if(!pricing)return;
    const plan=window.NxfloCosts.planning(current,pricing),costConfig=plan?.config || (current.provider==='databricks'?{...current,summary_model:current.databricks_model,draft_model:current.databricks_model,polish_model:current.databricks_model,summary_service:'default',draft_service:'default',polish_service:'default'}:current),proxy=current.provider==='databricks';
    $('generator-pricing-status').textContent=(pricing.warning?pricing.warning+' ':'')+(proxy?'Databricks planning estimate using same-model reference rates':'OpenRouter prices')+' · USD · checked '+new Date(pricing.checked_at).toLocaleString()+'.';
    renderMatrix(current);
    const roles=[['Author intent & evidence','summary_model'],['Plan, draft & review','draft_model'],['Polish & publication gate','polish_model']];
    $('generator-model-rates').replaceChildren(...roles.map(([label,key])=>{
      const row=document.createElement('tr'),name=document.createElement('th');name.scope='row';
      const stage=document.createElement('span'),model=document.createElement('small');stage.textContent=label;
      const price=Object.hasOwn(pricing.models,costConfig[key])?pricing.models[costConfig[key]]:null;const service=costConfig[key.replace('_model','_service')];model.textContent=(price?.name || costConfig[key] || 'Select a model')+(service==='flex'?' · Flex · 50% off':'')+(proxy?' · reference estimate':'');name.append(stage,model);row.append(name);
      for(const field of ['input','output']) {const cell=document.createElement('td');cell.textContent=price?usd(price[field]*(service==='flex'?.5:1)):'Unavailable';row.append(cell);}
      return row;
    }));
    const observed=observedSources?.key===sourceSignature(current)?observedSources.stats:null;
    const result=window.NxfloCosts.estimate(current,pricing,undefined,observed);
    $('generator-cost-total').textContent=result?'≈ '+usd(result.total):'Unavailable';
    $('generator-pass-costs').replaceChildren();$('generator-cost-breakdown').replaceChildren();
    if(!result){$('generator-cost-assumptions').textContent=(proxy?'No published reference rate matches this Databricks model. ':'')+'Choose models with published token prices and a valid page assumption to calculate an estimate. Unknown model prices are never treated as zero.';return;}
    $('generator-cost-assumptions').textContent=`${result.pages} planning pages · approximately ${result.manuscriptTokens.toLocaleString()} draft tokens · ${result.sourceTokens.toLocaleString()} source tokens · ${result.passes} full review/rewrite ${result.passes===1?'cycle':'cycles'}. ${result.observed?"Uses collected source text and actual summary chunk counts.":"Source estimates include pasted/uploaded text, 6,000 tokens per video or reference link, and search results."} ${proxy?'':'Research fees and Luna Flex notes are included when selected. The US$0.30 limit applies to web research only.'}${current.revision_parent?' Revision estimates also include the previous manuscript at the planned length and your feedback.':''}`;
    if(proxy)$('generator-cost-assumptions').textContent+=' Same-model reference rates are assumed comparable across hosts for this planning estimate. Actual Databricks billing may differ; no Flex discount or paid web discovery is assumed.';
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
      matrixSignature='';const row=document.createElement('tr');row.className='is-selected';const name=document.createElement('th');name.scope='row';name.style.overflowWrap='anywhere';
      const plan=window.NxfloCosts.planning(current,pricing),price=plan?pricing.models[plan.reference]:null;
      name.textContent=(current.databricks_model || 'Configure a Databricks model')+(price?' · same-model reference':'');row.append(name);
      for(const field of ['input','output']){const cell=document.createElement('td');cell.textContent=price?usd(price[field]):'Unavailable';row.append(cell);}$('generator-price-matrix').replaceChildren(row);return;
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
  function documentLink(label,id,kind,view=false) {
    const link=document.createElement('a');link.className='admin-button';link.textContent=label;
    link.href=endpoint+'/jobs/'+id+'/download/'+kind+(view?'?view=1':'');
    if(view){link.target='_blank';link.rel='noopener';}return link;
  }
  function openProgress(id) { return watch(id).then(()=>$('generator-workflow').scrollIntoView({behavior:'smooth',block:'start'})); }
  function libraryActions(version) {
    const actions=document.createElement('div');actions.className='generator-actions';
    if(version.pdf_job_id)actions.append(documentLink('Download PDF',version.pdf_job_id,'pdf'));
    if(version.html_job_id)actions.append(documentLink('Download HTML',version.html_job_id,'html'));
    if(version.status==='awaiting_html_review'){
      actions.append(documentLink('Preview HTML',version.job_id,'html',true));
      const proceed=button('Continue to PDF',()=>approveHtml(version.job_id,proceed));actions.append(proceed);
    }
    if(version.can_resume)actions.append(button('Resume',()=>resume(version.job_id).catch(showError)));
    actions.append(button('View progress',()=>openProgress(version.job_id).catch(showError)));
    if(version.pdf_job_id)actions.append(button('Revise document',()=>loadVersion(version.pdf_job_id).catch(showError)));
    actions.append(button('Use configuration',()=>loadVersion(version.job_id,true).catch(showError)));
    return actions;
  }
  function renderLibrary(documents=libraryDocuments) {
    const existing=$('generator-jobs');
    if(existing.querySelector('.generator-library-document'))expandedDocumentId=existing.querySelector('.generator-library-versions[open]')?.closest('[data-document]').dataset.document || null;
    libraryDocuments=documents;
    const term=$('generator-library-search').value.trim().toLocaleLowerCase();
    const visible=documents.filter(doc=>(doc.versions.length || ['queued','running'].includes(doc.latest.status) || doc.latest.job_id===watched || $('generator-library-unfinished').checked) && doc.title.toLocaleLowerCase().includes(term));
    const content=visible.map(doc=>{
      const card=document.createElement('article');card.className='generator-library-document';card.dataset.document=doc.id;
      const heading=document.createElement('div');heading.className='generator-library-heading';
      const copy=document.createElement('div'),title=document.createElement('h4'),titleButton=button(doc.title,()=>{history.open=!history.open;});titleButton.className='generator-document-title';title.append(titleButton);
      const meta=document.createElement('p');meta.className='generator-library-meta';
      const latest=document.createElement('span');latest.textContent='Latest v'+doc.latest.version;
      const status=document.createElement('span');status.className='generator-library-status';status.dataset.status=doc.latest.status;status.textContent=doc.latest.status_label;
      const updated=document.createElement('time');updated.dateTime=doc.updated_at;updated.textContent='Updated '+new Date(doc.updated_at).toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric'});updated.title=new Date(doc.updated_at).toLocaleString();
      meta.append(latest,status,updated);copy.append(title,meta);
      if(doc.latest_downloadable && doc.latest_downloadable.id!==doc.latest.id){const saved=document.createElement('span');saved.textContent='Latest downloadable: v'+doc.latest_downloadable.version;meta.append(saved);}
      const selected=doc.latest.status==='awaiting_html_review'?doc.latest:doc.latest_downloadable;
      const open=selected?(selected.status==='awaiting_html_review'?documentLink('Open Document',selected.job_id,'html',true):documentLink('Open Document',selected.pdf_job_id,'pdf',true)):button('Open Document',()=>openProgress(doc.latest.job_id).catch(showError));
      open.classList.add('generator-primary');heading.append(copy,open);
      const history=document.createElement('details');history.className='generator-library-versions';history.open=expandedDocumentId===doc.id;
      const summary=document.createElement('summary');summary.textContent='Version history';history.append(summary);
      titleButton.setAttribute('aria-expanded',String(history.open));
      history.addEventListener('toggle',()=>{
        if(!history.isConnected)return;
        titleButton.setAttribute('aria-expanded',String(history.open));
        if(history.open){expandedDocumentId=doc.id;for(const other of $('generator-jobs').querySelectorAll('details'))if(other!==history)other.open=false;}
        else if(expandedDocumentId===doc.id)expandedDocumentId=null;
      });
      if(doc.current_work){const work=document.createElement('section');work.className='generator-library-current';const label=document.createElement('strong');label.textContent='Current document · v'+doc.current_work.version+' · '+doc.current_work.status_label;work.append(label);
        if(doc.current_work.notice){const note=document.createElement('p');note.textContent=doc.current_work.notice;work.append(note);}work.append(libraryActions(doc.current_work));history.append(work);}
      for(const version of doc.versions){const row=document.createElement('section');row.className='generator-library-version';row.dataset.version=version.id;
        const name=document.createElement('strong');name.textContent='v'+version.version+(version.is_current?' · Current version':'');
        const detail=document.createElement('p');detail.className='generator-help';detail.textContent=version.status_label+' · '+new Date(version.updated_at).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'});row.append(name,detail,libraryActions(version));history.append(row);
      }
      if(!doc.versions.length){const empty=document.createElement('p');empty.className='generator-help';empty.textContent='No saved versions yet. Your first version will appear here when its document is ready for review.';history.append(empty);}
      card.append(heading,history);return card;
    });
    if(!content.length){const empty=document.createElement('p');empty.textContent=term?'No documents match your search.':'No documents yet. Start your first document above.';content.push(empty);}
    $('generator-jobs').replaceChildren(...content);$('generator-library-count').textContent=visible.length+' of '+documents.length+' documents';
  }
  async function loadVersion(id,configurationOnly=false) {
    if(busy || active) return message('Wait for the current generation to finish.');
    const job=await request('/jobs/'+id);
    const completed=!configurationOnly && ['ready','needs_review'].includes(job.status),teams=config.teams;
    const selected=teams.some(team=>team.id===job.config.prepared_team)?job.config.prepared_team:'';
    populate({...job.config,teams,prepared_team:selected,revision_parent:completed?id:'',feedback:'',change_summary:'',version_override:false});history.replaceState(null,'','admin.html?job='+id);
    const libraryDocument=libraryDocuments.find(doc=>doc.id===job.document_id);
    if(completed)form.elements.version.value=libraryDocument?.next_version || (Number.isFinite(Number(job.config.version))?(Number(job.config.version)+0.1).toFixed(Math.max(1,(job.config.version.split('.')[1] || '').length)):'1.1');
    ready();$('generator-version-settings').open=false;
    $('generator-revision-base').textContent=completed?'Revising '+(job.config.title || 'document')+' · version '+job.config.version+'. Download and review the PDF, then enter your feedback below.':'';
    if(completed){clearTimeout(pollTimer);watched=id;workflow(job);}
    dirty=true;await save();message(completed?'Ready for your feedback. The next version will be assigned automatically. Earlier output is preserved.':'Configuration loaded.');
    (completed?$('generator-revision'):$('generator-editor')).scrollIntoView({behavior:'smooth',block:'start'});
    $('generator-configuration').open=true;
    if(completed)form.elements.feedback.focus();
  }

  async function load(refresh=false) {
    if(loading || !csrf)return;
    loading=true;
    try {
      const data=await request();providerSettings=data.providers || {openrouter:{configured:data.configured},databricks:{configured:false,model:''}};configured=data.configured;defaults=data.defaults || defaults;
      if(!loaded) {revision=data.revision;loaded=true;populate(data.config);$('generator-save-state').textContent=revision?'Saved configuration':'New configuration';}
      $('generator-key-status').textContent=(providerSettings.databricks.configured?'Databricks configured. ':'Databricks not configured. ')+(providerSettings.openrouter.configured?'OpenRouter configured. ':'OpenRouter not configured. ')+(data.worker_online?'Generation worker online.':'Generation worker offline.');
      renderLibrary(data.documents || []);
      if(!pricing)await loadPrices();
      if(!refresh)message('Configuration loaded. Changes are saved automatically.');
      const running=(data.jobs || []).find(job=>['queued','running'].includes(job.status)) || (new URLSearchParams(location.search).get('new')==='1'?null:(data.jobs || []).find(job=>job.status==='awaiting_html_review'));
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
    const percent=window.NxfloTiming.overall(job);$('generator-progress').value=percent/100*steps.length;$('generator-progress').setAttribute('aria-valuetext',percent+'% of workflow complete');$('generator-progress-percent').textContent=percent+'%';$('generator-progress-panel').style.setProperty('--generation-progress',percent+'%');
    $('generator-progress-panel').classList.toggle('is-active',['queued','running'].includes(job.status) && job.worker_online!==false);
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
  function renderFailure(job) {
    const panel=$('generator-failure');panel.hidden=job.status!=='failed';
    if(panel.hidden){failureKey='';return;}
    const failure=job.failure_details || {summary:job.error || job.message,chapters:[],issues:job.quality_errors || [],highlights:[],next_action:'Saved work is preserved.',error:job.error};
    const key=JSON.stringify([job.id,failure]);if(key===failureKey)return;failureKey=key;
    $('generator-failure-summary').textContent=failure.summary;
    $('generator-failure-highlights').replaceChildren(...(failure.highlights || []).map(text=>{const p=document.createElement('p');p.className='generator-failure-issue';p.textContent=text;return p;}));
    const groups=(failure.chapters || []).map(chapter=>{
      const group=document.createElement('div'),title=document.createElement('h5');title.textContent='Chapter '+chapter.number+(chapter.title?' · '+chapter.title:'');group.append(title);
      for(const issue of chapter.issues){const p=document.createElement('p');p.className='generator-failure-issue';p.textContent=issue;group.append(p);}return group;
    });
    if(failure.issues?.length){const group=document.createElement('div'),heading=document.createElement('h5');heading.textContent='Whole-document checks';group.append(heading);for(const issue of failure.issues){const p=document.createElement('p');p.className='generator-failure-issue';p.textContent=issue;group.append(p);}groups.push(group);}
    $('generator-failure-chapters').replaceChildren(...groups);$('generator-failure-original').textContent=failure.error || job.error || '';
    $('generator-failure-action').textContent=failure.next_action;$('generator-failure-more').open=false;
  }
  function workflow(job={status:'idle',step:'',events:[],message:'Start generation to follow the actual workflow.'}) {
    timedJob=job;timingReceived=performance.now();renderTiming();
    renderChef(job);
    if(job.source_metrics && job.config)observedSources={key:sourceSignature(job.config),stats:job.source_metrics};
    const complete=new Set(job.events.filter(event=>event.status==='complete').map(event=>event.step));
    const running=['queued','running'].includes(job.status),done=['ready','needs_review'].includes(job.status);
    document.querySelector('.generator-layout').classList.toggle('is-running',running);
    const freshSetup=new URLSearchParams(location.search).get('new')==='1';
    document.querySelector('.generator-layout').classList.toggle('is-focused',!!job.id && !freshSetup);
    if(job.id && focusedJob!==job.id){if(!freshSetup)$('generator-configuration').open=false;focusedJob=job.id;}
    $('generator-configuration-context').textContent=freshSetup?'New document · v1.0':job.id?(job.config?.title || 'Document')+' · v'+(job.config?.version || '1.0'):'Set up your document';
    $('generator-workflow-status').textContent=(job.worker_online===false && running?'Worker heartbeat is missing; live progress is unavailable. ':'')+(job.status==='failed'?(job.failure_details?.summary || job.error || job.message || 'Generation failed'):(job.message || job.status));
    const intentLabels={summarize:'Preserve intent & evidence',outline:'Plan structure & examples',review:'Review intent & accuracy',assemble:'Quality gate & document layout'};
    const failurePanel=$('generator-failure');failurePanel.remove();
    const reviewJump=$('generator-review-jump'),reviewActions=$('generator-review-actions'),reviewFocused=reviewActions.contains(document.activeElement)?document.activeElement:null;reviewActions.remove();
    const resumeButton=$('generator-resume'),resumeFocused=document.activeElement===resumeButton;resumeButton.remove();
    $('generator-steps').replaceChildren(...steps.map(([key,label],i)=>{
      if(job.pipeline_version===2 || job.status==='idle')label=intentLabels[key] || label;
      const currentState=job.worker_online===false?'stalled':job.wait_state?.label || job.batch_wait || job.recovery?.retry_at?'waiting':job.status==='queued'?'queued':'running';
      const li=document.createElement('li');li.tabIndex=-1;li.dataset.step=key;li.dataset.state=job.status==='awaiting_html_review' && key==='html_review'?'review':running && job.step===key?currentState:job.status==='failed' && job.step===key?'failed':complete.has(key)?'complete':'pending';
      const dot=document.createElement('span');dot.className='generator-step-dot';dot.setAttribute('aria-hidden','true');dot.textContent=complete.has(key)?'✓':String(i+1).padStart(2,'0');
      if(running && job.step===key){dot.classList.add('is-meter');dot.removeAttribute('aria-hidden');dot.setAttribute('role','progressbar');dot.setAttribute('aria-label',label+' progress');dot.setAttribute('aria-valuemin','0');dot.setAttribute('aria-valuemax','100');}
      const copy=document.createElement('div');copy.className='generator-step-copy';const name=document.createElement('strong'),state=document.createElement('small');name.textContent=label;
      const passes=job.events.filter(event=>event.step===key && event.status==='complete').length;
      state.textContent=li.dataset.state+(passes>1?' · '+passes:'');if(done && key==='rewrite' && !complete.has(key))state.textContent='Not needed';
      const elapsed=document.createElement('small');elapsed.className='generator-step-elapsed';elapsed.hidden=true;
      const count=document.createElement('small');count.className='generator-step-count';count.hidden=true;
      copy.append(name,state,elapsed,count);li.append(dot,copy);return li;
    }));
    const reviewStep=$('generator-steps').querySelector('[data-step=html_review]');reviewStep.querySelector('.generator-step-copy').append(reviewActions);reviewStep.classList.toggle('has-review',job.status==='awaiting_html_review');
    if(reviewFocused)reviewFocused.focus({preventScroll:true});
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
    $('generator-progress-panel').hidden=job.status==='idle';$('generator-progress').hidden=job.status==='idle';$('generator-progress').max=steps.length;
    const reviewing=job.status==='awaiting_html_review';
    reviewActions.hidden=!reviewing;reviewJump.hidden=!reviewing;
    $('generator-html-status').hidden=!reviewing;
    if(reviewing){reviewJump.href=endpoint+'/jobs/'+job.id+'/download/html?view=1';}
    else $('generator-html-status').textContent='';
    $('generator-result').hidden=!done;$('generator-cancel').hidden=!running;
    const recovery=job.recovery || {},retryWait=recovery.retry_at?Math.max(0,Math.ceil(recovery.retry_at-(job.server_time || Date.now()/1000))):0;
    resumeButton.hidden=!recovery.can_resume || (running && (!job.batch_wait || recovery.retry_at));
    resumeButton.textContent=running?'Check batch now':'Resume';
    resumeButton.setAttribute('aria-label',running?'Check batch now':'Resume generation');
    const resumeStep=$('generator-steps').querySelector('[data-step="'+job.step+'"]');
    if(!resumeButton.hidden && resumeStep){resumeStep.querySelector('.generator-step-copy').append(resumeButton);resumeStep.classList.add('has-resume');}
    else $('generator-cancel').before(resumeButton);
    if(resumeFocused && !resumeButton.hidden)resumeButton.focus({preventScroll:true});
    const failedStep=$('generator-steps').querySelector('[data-step="'+job.step+'"] .generator-step-copy');
    if(job.status==='failed' && failedStep)failedStep.append(failurePanel);else $('generator-steps').after(failurePanel);
    renderFailure(job);
    $('generator-recovery-status').hidden=!recovery.blocked_reason && !recovery.retry_at && !['failed','cancelled'].includes(job.status);
    $('generator-recovery-status').textContent=recovery.blocked_reason || (recovery.retry_at?'Automatic recovery · attempt '+recovery.attempts+' of 3 · '+(retryWait?'retry in '+retryWait+'s.':'retry due now.')+' Completed stages and saved responses will be reused.':recovery.can_resume?'Resume continues this version from saved progress. Completed work and existing Batch requests are reused.':'');
    $('generator-cost-actual').textContent=job.id?(job.config?.provider==='databricks'?'Databricks usage is billed in your workspace; USD charges are not returned by this endpoint.':job.cost==null?'Model cost: not yet reported by OpenRouter.':'Reported usage cost so far (OpenRouter + BYOK): '+usd(Number(job.cost)))+(job.unreported_calls?' · Some completed charges have not been reported.':'')+(job.warnings?.length?' · '+job.warnings.length+' review/source warnings.':''):'';
    const budget=job.web_budget;
    $('generator-web-spend').hidden=!budget || (!budget.reported && !budget.reserved && !budget.historical);
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
  const approvingHtml=new Set();
  async function approveHtml(id,button) {
    if(!id || approvingHtml.has(id))return;
    approvingHtml.add(id);button.disabled=true;
    try{await request('/jobs/'+id+'/approve-html',json('POST',{}));await watch(id);await load(true);message('HTML approved. Continuing to PDF export.');}
    catch(error){$('generator-html-status').textContent=error.message;showError(error);}
    finally{approvingHtml.delete(id);button.disabled=false;}
  }
  $('generator-approve-html').addEventListener('click',()=>approveHtml(watched,$('generator-approve-html')));
  async function resume(id) {
    $('generator-resume').disabled=true;
    try{await request('/jobs/'+id+'/resume',json('POST',{}));await watch(id);await load(true);message('Continuing from saved progress. Existing requests and completed responses are reused.');}
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
  async function resetDocument(startFresh=false) {
    if(!loaded || !defaults || busy || uploading)return;
    if(!startFresh && !confirm('Clear document details, research text, source uploads and supporting images? Your company name, logo, website, team contacts, previous documents and any running generation will be kept.'))return;
    busy=true;clearTimeout(saveTimer);ready();
    try{
      if(saving)await saving;
      const identity=values();form.reset();populate({...structuredClone(defaults),provider:identity.provider,databricks_model:identity.databricks_model,company:identity.company,logo:identity.logo,website:identity.website,teams:identity.teams,prepared_team:identity.prepared_team,color:identity.color,accent:identity.accent,title:'',credits:'',topic:'',questions:'',release_date:'',version:'1.0',version_override:false,youtube:'',documents:[],illustrations:[]});
      parentId=null;
      if(startFresh){
        const url=new URL(location.href);url.searchParams.delete('job');url.searchParams.set('new','1');history.replaceState(null,'',url.pathname+url.search+url.hash);
        if(!active){clearTimeout(pollTimer);watched=null;focusedJob=null;workflow();}
        else focusedJob=watched;
        $('generator-configuration-context').textContent='New document · v1.0';
      }else focusedJob=null;
      document.querySelector('.generator-layout').classList.remove('is-focused');$('generator-configuration').open=true;dirty=true;await save();
      $('generator-fill-status').textContent='Form cleared. Enter a new topic and brief, then use AI to fill the details.';
      message('New document ready. Company branding, team contacts and previous documents are preserved.'+(active?' Your current generation continues in the background.':''));form.elements.topic.focus();
    }catch(error){showError(error);}finally{busy=false;ready();}
  }
  $('generator-clear-form').addEventListener('click',()=>resetDocument());
  $('generator-new-document').addEventListener('click',()=>resetDocument(true));
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(!form.reportValidity() || active || uploading || busy)return;
    busy=true;clearTimeout(saveTimer);ready();message('Saving configuration and starting document generation…');
    try{
      await save();await fillBlankMetadata();
      const result=await request('/jobs',json('POST',{config:values(),parent_id:parentId}));
      form.elements.version.value=result.version;dirty=true;save().catch(showError);active=result.id;history.replaceState(null,'','admin.html?job='+result.id);await watch(result.id);await load(true);
      const first=$('generator-steps').querySelector('[data-step=collect]');
      $('generator-workflow').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});first?.focus({preventScroll:true});
      message('Generation queued. You can leave this page and return to follow progress.');
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
  $('generator-refresh-prices').addEventListener('click',()=>loadPrices(true));
  $('generator-refresh').addEventListener('click',()=>load(true));
  $('generator-library-search').addEventListener('input',()=>renderLibrary());
  $('generator-library-unfinished').addEventListener('change',()=>renderLibrary());
  window.addEventListener('nxflo-admin-tab',event=>{if(event.detail==='generator-tab')load();});
  window.addEventListener('nxflo-owner-session',event=>{csrf=event.detail.csrf;});
  window.addEventListener('nxflo-session-ended',()=>{csrf='';loaded=false;config=null;active=null;watched=null;timedJob=null;renderTiming();$('generator-editor').hidden=false;$('generator-logo-preview').querySelector('img').removeAttribute('src');$('generator-logo-preview').hidden=true;$('generator-logo-empty').hidden=false;$('generator-logo-help').hidden=false;logoDrop.classList.remove('has-logo');logoDrop.setAttribute('aria-label','Upload company logo');clearTimeout(pollTimer);clearTimeout(saveTimer);form.reset();libraryDocuments=[];expandedDocumentId=null;$('generator-library-search').value='';$('generator-library-unfinished').checked=false;$('generator-library-count').textContent='';$('generator-jobs').replaceChildren();$('generator-review-actions').hidden=true;$('generator-review-jump').hidden=true;$('generator-html-status').hidden=true;$('generator-failure').hidden=true;failureKey='';});
  window.addEventListener('beforeunload',event=>{if(dirty || saving || uploading){event.preventDefault();event.returnValue='';}});
  workflow();

})();
