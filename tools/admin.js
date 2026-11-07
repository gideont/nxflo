(() => {
  'use strict';
  const api = '/bms_integration_hub/api';
  const $ = id => document.getElementById(id);
  let csrf = '', snapshot = null, sequence = 0;
  const number = value => new Intl.NumberFormat('en-CA', {maximumFractionDigits: 1}).format(value);
  async function request(path, options = {}) {
    const response = await fetch(api + path, {credentials: 'same-origin', ...options});
    const data = await response.json();
    if (!response.ok) { const error = new Error(data.error || 'Request failed. Please try again.'); error.status = response.status; throw error; }
    return data;
  }
  function status(message) { $('admin-status').classList.toggle('admin-status-quiet', message === 'Analytics updated.'); $('admin-status').textContent = message; $('admin-login-status').textContent = message; }
  function setBrowserWidth(enabled) {
    document.querySelector('.admin-page').classList.toggle('is-browser-width', enabled);
    $('admin-width').setAttribute('aria-pressed', String(enabled));
    if (snapshot) renderCharts(snapshot);
  }
  function lock() { setBrowserWidth(false); $('admin-width').hidden = true; $('admin-width-status').hidden = true; window.dispatchEvent(new Event('nxflo-session-ended')); document.querySelector('.admin-page').classList.add('is-login'); sequence++; $('admin-workspace').hidden = true; $('admin-logout').hidden = true; snapshot = null; }
  async function startLogin() {
    lock(); $('admin-session-retry').hidden=true; $('admin-login').hidden = false;
    try {
      const config = await request('/auth/config');
      if (!window.google?.accounts?.id) await new Promise((resolve, reject) => {
        const script = document.createElement('script'); script.src = 'https://accounts.google.com/gsi/client';
        script.onload = resolve; script.onerror = () => reject(new Error('Google sign-in could not load. Check your connection and reload.'));
        document.head.append(script);
      });
      google.accounts.id.initialize({client_id: config.client_id, nonce: config.nonce, auto_select: false, use_fedcm_for_prompt: true,
        callback: async result => {
          try {
            await request('/auth/google', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': config.csrf_token}, body: JSON.stringify({credential: result.credential})});
            await session();
          } catch (error) { status(error.message); }
        }});
      $('admin-google').replaceChildren();
      google.accounts.id.renderButton($('admin-google'), {theme: 'outline', size: 'large', shape: 'pill', text: 'continue_with', width: Math.min(320, $('admin-google').clientWidth)});
      $('admin-login-help').textContent = 'If One Tap does not appear, use the Google button.';
      google.accounts.id.prompt();
    } catch (error) { $('admin-login-help').textContent = error.message; }
  }
  async function session() {
    $('admin-session-retry').disabled=true;
    try {
      const me = await request('/me');
      $('admin-session-retry').hidden=true;
      if (!me.user.is_owner) { status('This account does not have owner access. Sign out to choose another Google account.'); lock(); document.querySelector('.admin-page').classList.remove('is-login'); $('admin-logout').hidden = false; $('admin-login').hidden = true; csrf = me.csrf_token; return; }
      csrf = me.csrf_token; document.querySelector('.admin-page').classList.remove('is-login'); $('admin-login').hidden = true; $('admin-workspace').hidden = false; $('admin-logout').hidden = false;
      $('admin-identity').textContent = 'Signed in as ' + me.user.email;
      window.dispatchEvent(new CustomEvent('nxflo-owner-session', {detail:{csrf}}));
      $('admin-width').hidden = false;
      $('admin-width').disabled = true;
      try {
        const preferences = await request('/admin/preferences');
        setBrowserWidth(preferences.browser_width === true);
      } catch (error) {
        $('admin-width-status').hidden = false;
        $('admin-width-status').textContent = 'Could not load your width preference. ' + error.message;
      } finally { $('admin-width').disabled = false; }
      restoreTab();
      await load();
    } catch (error) {
      if(error.status===401 || error.status===403) { status('Sign in to continue.'); await startLogin(); }
      else {
        document.querySelector('.admin-page').classList.remove('is-login');$('admin-login').hidden=true;
        status('Your session could not be checked. Retry when the connection recovers.');$('admin-session-retry').hidden=false;
      }
    } finally { $('admin-session-retry').disabled=false; }
  }
  const palette = ['#a6533a','#487858','#3d6d9e','#865ca5','#ac7c20','#a74f79','#367d83','#716346','#535da1','#9b5737','#537b2e','#9e4058','#5c6b77','#846f99','#8f722c','#326d63','#85604e','#5f778f','#963c72','#697245'];
  const pageName = path => ({'/':'Home','/csv-viewer.html':'CSV viewer','/pdf-combiner.html':'PDF merge'})[path] || path.slice(1).replace(/\.html$/, '').replaceAll('-', ' ').replace(/^./, c => c.toUpperCase());
  const escapeText = text => String(text).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  function attachChartHover(target, width, height, chartSeries, describe) {
    const svg = target.querySelector('svg');
    const tooltip = document.createElement('div');
    tooltip.className = 'admin-chart-tooltip';
    tooltip.hidden = true;
    tooltip.setAttribute('role', 'tooltip');
    const tooltipName = document.createElement('strong'), tooltipPath = document.createElement('span'), tooltipValue = document.createElement('span');
    tooltip.append(tooltipName, tooltipPath, tooltipValue);
    target.append(tooltip);
    const groups = chartSeries.map(s => s.group);
    function clearHover() {
      tooltip.hidden = true;
      groups.forEach(group => group.classList.remove('is-nearest'));
    }
    function showNearest(event) {
      const bounds = svg.getBoundingClientRect();
      const px = (event.clientX - bounds.left) * width / bounds.width;
      const py = (event.clientY - bounds.top) * height / bounds.height;
      let nearest = null;
      chartSeries.forEach(s => {
        s.points.forEach((point, i) => {
          const end = s.points[i + 1] || point;
          const dx = end.x - point.x, dy = end.y - point.y;
          const lengthSquared = dx * dx + dy * dy;
          const t = lengthSquared ? Math.max(0, Math.min(1, ((px - point.x) * dx + (py - point.y) * dy) / lengthSquared)) : 0;
          const distance = (px - point.x - t * dx) ** 2 + (py - point.y - t * dy) ** 2;
          if (!nearest || distance < nearest.distance) {
            nearest = {series: s, point: Math.abs(px - point.x) <= Math.abs(px - end.x) ? point : end, distance};
          }
        });
      });
      if (!nearest) { clearHover(); return; }
      const {series: selected, point} = nearest;
      groups.forEach(group => group.classList.toggle('is-nearest', group === selected.group));
      const [name, path, value] = describe(selected, point);
      tooltipName.textContent = name;
      tooltipPath.textContent = path;
      tooltipPath.hidden = !path;
      tooltipValue.textContent = value;
      tooltip.hidden = false;
      const box = target.getBoundingClientRect();
      const offsetX = event.clientX - box.left, offsetY = event.clientY - box.top;
      tooltip.style.left = `${Math.max(0, Math.min(offsetX + 12, box.width - tooltip.offsetWidth))}px`;
      tooltip.style.top = `${Math.max(0, offsetY - tooltip.offsetHeight - 8)}px`;
    }
    const interactionTarget = target.closest('.admin-panel');
    interactionTarget.onpointermove = showNearest;
    interactionTarget.onpointerdown = showNearest;
    interactionTarget.onpointerleave = clearHover;
    interactionTarget.onpointercancel = clearHover;
    interactionTarget.onkeydown = event => { if (event.key === 'Escape') clearHover(); };
  }
  function renderCharts(data) {
    const rows = data.daily;
    const target = $('views-chart');
    if (!target.clientWidth) return;
    const compact = matchMedia('(max-width:700px)').matches;
    const width = target.clientWidth, height = compact ? 110 : 155, left = compact ? 28 : 36, right = 8, top = 9, bottom = 23;
    const series = data.top_pages;
    const max = Math.max(2, Math.ceil(Math.max(0,...series.flatMap(s=>s.daily.map(r=>r.page_views||0)))/2)*2);
    const x = i => rows.length===1 ? (left+width-right)/2 : left + i*(width-left-right)/(rows.length-1);
    const y = v => height-bottom-v/max*(height-top-bottom);
    const axisNumber = v => v>=1000 ? new Intl.NumberFormat('en-CA',{notation:'compact',maximumFractionDigits:1}).format(v) : number(v);
    const grid = [0,max/2,max].map(v=>`<line x1="${left}" y1="${y(v)}" x2="${width-right}" y2="${y(v)}" stroke="#eae7de" stroke-dasharray="2 3"/><text x="${left-6}" y="${y(v)+3}" text-anchor="end">${axisNumber(v)}</text>`).join('');
    const indices = compact ? [0,rows.length-1] : [0,Math.floor((rows.length-1)/3),Math.floor(2*(rows.length-1)/3),rows.length-1];
    const labels = [...new Set(indices)].map(i=>`<text x="${x(i)}" y="${height-4}" text-anchor="${rows.length===1?'middle':i===0?'start':i===rows.length-1?'end':'middle'}">${rows[i].day.slice(5)}</text>`).join('');
    const visitorTarget = $('visitor-chart');
    if (visitorTarget.clientWidth) {
      const visitorWidth = visitorTarget.clientWidth;
      const visitorMax = Math.max(2,Math.ceil(Math.max(0,...rows.map(r=>r.visitors||0))/2)*2);
      const vx = i => rows.length===1 ? (left+visitorWidth-right)/2 : left+i*(visitorWidth-left-right)/(rows.length-1);
      const vy = value => height-bottom-value/visitorMax*(height-top-bottom);
      const visitorGrid = [0,visitorMax/2,visitorMax].map(v=>`<line x1="${left}" y1="${vy(v)}" x2="${visitorWidth-right}" y2="${vy(v)}" stroke="#eae7de" stroke-dasharray="2 3"/><text x="${left-6}" y="${vy(v)+3}" text-anchor="end">${axisNumber(v)}</text>`).join('');
      const visitorLabels = [...new Set(indices)].map(i=>`<text x="${vx(i)}" y="${height-4}" text-anchor="${rows.length===1?'middle':i===0?'start':i===rows.length-1?'end':'middle'}">${rows[i].day.slice(5)}</text>`).join('');
      const values=rows.map((r,i)=>({...r,i})).filter(r=>r.visitors!==null);
      const points=values.map(r=>`${vx(r.i)},${vy(r.visitors)}`).join(' ');
      const dots=values.map(r=>`<circle cx="${vx(r.i)}" cy="${vy(r.visitors)}" r="${values.length===1?3:2}" fill="#647c61"></circle>`).join('');
      visitorTarget.innerHTML=`<svg viewBox="0 0 ${visitorWidth} ${height}" role="img" aria-label="Daily visitors by date. Exact daily values in the table."><g font-size="10" fill="#76776b">${visitorGrid}${visitorLabels}</g><g data-visitors><polyline points="${points}" fill="none" stroke="#647c61" stroke-width="1.8" stroke-linejoin="round"/>${dots}</g></svg>`;
      attachChartHover(visitorTarget, visitorWidth, height, [{
        group: visitorTarget.querySelector('g[data-visitors]'),
        points: values.map(row => ({...row, x: vx(row.i), y: vy(row.visitors)}))
      }], (_, point) => ['Daily visitors', '', `${point.day} · ${number(point.visitors)} visitors`]);
    }
    const lines = series.map(s=>{
      const color = palette[Math.max(0,data.pages.indexOf(s.path))%palette.length];
      const values = s.daily.map((r,i)=>({...r,i})).filter(r=>r.page_views!==null);
      const points = values.map(r=>`${x(r.i)},${y(r.page_views)}`).join(' ');
      const dots = values.map(r=>`<circle cx="${x(r.i)}" cy="${y(r.page_views)}" r="${values.length===1?3:2}" fill="${color}" opacity="${values.length===1?1:.45}"></circle>`).join('');
      return `<g data-page="${escapeText(s.path)}"><polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linejoin="round"></polyline>${dots}</g>`;
    }).join('');
    target.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily page views for the top ${series.length} pages. Each colored line is one page. Exact values in the daily table."><g font-size="10" fill="#76776b">${grid}${labels}</g>${lines}</svg>`;
    const groups = [...target.querySelectorAll('g[data-page]')];
    attachChartHover(target, width, height, series.map((s, index) => ({
      ...s, group: groups[index],
      points: s.daily.map((row, i) => ({...row, x: x(i), y: y(row.page_views)})).filter(row => row.page_views !== null)
    })), (s, point) => [pageName(s.path), s.path, `${point.day} · ${number(point.page_views)} views`]);
    $('admin-page-legend').replaceChildren(...series.map((s,index)=>{
      const item=document.createElement('li'), swatch=document.createElement('span'), name=document.createElement('span'), total=document.createElement('strong');
      swatch.className='admin-line-key';swatch.style.background=palette[Math.max(0,data.pages.indexOf(s.path))%palette.length];swatch.setAttribute('aria-hidden','true');
      const rank=document.createElement('span');rank.className='admin-page-rank';rank.textContent=String(index+1);
      name.className='admin-page-name';name.textContent=pageName(s.path);name.title=s.path;
      total.textContent=number(s.total_views);total.title='Views in selected period';item.append(swatch,rank,name,total);return item;
    }));
    $('admin-top-note').textContent = series.length ? `Showing ${series.length} pages · Ranked by period views (up to ${data.top_pages_limit})` : 'No page views recorded in this period yet.';
  }
  async function load() {
    const current = ++sequence; $('admin-results').hidden = true; status('Loading analytics…');
    try {
      const data = await request('/admin/analytics?' + new URLSearchParams({months: $('admin-period').value}));
      if (current !== sequence) return;
      snapshot = data;
      $('admin-top-pages').value = String(data.top_pages_limit);
      const views = data.daily.reduce((sum,row)=>sum+(row.page_views||0),0);
      const dateLabel = value => new Date(value + 'T12:00:00').toLocaleDateString('en-CA', {month:'short',day:'numeric'});
      $('admin-coverage').textContent = `${dateLabel(data.start)}${data.start===data.end?'':' – '+dateLabel(data.end)}, ${data.end.slice(0,4)} · Vancouver time${views === 0 ? ' · No visits yet' : ''}`;
      $('admin-started').textContent = `Collecting since ${dateLabel(data.started)}, ${data.started.slice(0,4)}`;
      const today = data.daily[data.daily.length-1];
      $('admin-today-visitors').textContent = number(today.visitors);
      $('admin-today-views').textContent = today.page_views === null ? '—' : number(today.page_views);
      $('admin-results').hidden = false;
      renderCharts(data);
      const headers=['Date','Visitors','All views'].map(label=>{const th=document.createElement('th');th.scope='col';th.textContent=label;return th;});
      data.top_pages.forEach((series,index)=>{const th=document.createElement('th'),key=document.createElement('abbr');th.scope='col';th.setAttribute('aria-label',series.path);key.textContent='#'+(index+1);key.title=series.path;th.append(key);headers.push(th);});
      $('admin-daily-head').replaceChildren(...headers);
      $('admin-daily').replaceChildren(...data.daily.map((r,i)=>{
        const tr=document.createElement('tr');
        [r.day,r.visitors,r.page_views,...data.top_pages.map(s=>s.daily[i].page_views)].forEach((value,index)=>{const td=document.createElement('td');td.textContent=index===0?value:value===null?'Unavailable':number(value);tr.append(td);});return tr;
      }).reverse());
      $('admin-results').hidden = false; status('Analytics updated.');
    } catch(error) { if(current!==sequence)return; snapshot=null; status(error.message); if(error.status===401 || error.status===403) { lock(); await startLogin(); } }
  }
  $('admin-check-tracking').addEventListener('click', async () => {
    const output = $('admin-tracking-status'), button = $('admin-check-tracking');
    if (navigator.globalPrivacyControl === true || navigator.doNotTrack === '1') {
      output.textContent = `This browser opts out through ${navigator.globalPrivacyControl === true ? 'Global Privacy Control' : 'Do Not Track'}. Its page views are excluded. Incognito mode can have different privacy settings from your regular window.`;
      return;
    }
    button.disabled = true; output.textContent = 'Checking the collection endpoint…';
    try {
      const data = await request('/analytics/collect', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({probe:true}), signal:AbortSignal.timeout(8000)});
      output.textContent = data.collection_status === 'privacy_opt_out'
        ? 'A Do Not Track or Global Privacy Control request header opts this browser out. Its page views are excluded.'
        : data.collection_status === 'bot_filtered'
        ? 'The server recognizes this browser as automated traffic, so its page views are excluded.'
        : 'The collection endpoint is reachable and accepts this browser. No test page view was added. Browse a public page, then refresh analytics. Repeat in the same privacy window if that is where views are missing.';
    } catch (error) {
      output.textContent = 'The collection request failed or was blocked. A content blocker, tracking protection, or connection problem may be stopping page views. If you want this browser counted, check its site permissions for nxflo.com.';
    } finally { button.disabled = false; }
  });
  $('admin-width').addEventListener('click', async () => {
    const button = $('admin-width');
    const enabled = button.getAttribute('aria-pressed') !== 'true';
    button.disabled = true;
    try {
      const preferences = await request('/admin/preferences', {method:'PUT', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:JSON.stringify({browser_width:enabled})});
      setBrowserWidth(preferences.browser_width === true);
      $('admin-width-status').textContent = (preferences.browser_width ? 'Browser width' : 'Standard width') + ' saved for your account.';
    } catch (error) {
      $('admin-width-status').textContent = 'Could not save your width preference. ' + error.message;
    } finally { button.disabled = false; $('admin-width-status').hidden = false; }
  });
  $('admin-period').addEventListener('change', load); $('admin-refresh').addEventListener('click',load);
  $('admin-top-pages').addEventListener('change', async () => {
    const select = $('admin-top-pages'), previous = snapshot?.top_pages_limit || 8;
    select.disabled = true;
    try {
      await request('/admin/analytics/preferences', {method:'PUT',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({top_pages_limit:Number(select.value)})});
      await load();
    } catch(error) { select.value=String(previous);status('Could not save the page count: '+error.message); }
    finally { select.disabled=false; }
  });
  $('admin-export').addEventListener('click', () => {
    if(!snapshot)return;
    const cell = value => '"'+String(value??'').replaceAll('"','""')+'"';
    const csv = ['Date','Visitors','All page views',...snapshot.top_pages.map(s=>s.path)].map(cell).join(',')+'\n'+snapshot.daily.map((r,i)=>[r.day,r.visitors,r.page_views,...snapshot.top_pages.map(s=>s.daily[i].page_views)].map(cell).join(',')).join('\n');
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));const a=document.createElement('a');a.href=url;a.download='nxflo-daily-analytics.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  $('admin-logout').addEventListener('click', async () => {
    try { await request('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':csrf}}); window.google?.accounts.id.disableAutoSelect(); lock(); status('Signed out.'); await startLogin(); } catch(error){status(error.message);}
  });
  const tabs = [$('analytics-tab'),$('generator-tab'),$('account-tab')];
  function tab(index) { if(index!==1 && new URLSearchParams(location.search).has('job')) { const url=new URL(location.href);url.searchParams.delete('job');history.replaceState(null,'',url.pathname+url.search+url.hash); } try { localStorage.setItem('nxflo.admin.activeTab',tabs[index].id); } catch {} tabs.forEach((t,i)=>{t.setAttribute('aria-selected',String(i===index));t.tabIndex=i===index?0:-1;$(t.getAttribute('aria-controls')).hidden=i!==index;}); if(index===0 && snapshot) { renderCharts(snapshot); } window.dispatchEvent(new CustomEvent('nxflo-admin-tab', {detail:tabs[index].id})); }
  function restoreTab() {
    let selected='analytics-tab';
    try { selected=localStorage.getItem('nxflo.admin.activeTab') || selected; } catch {}
    if(new URLSearchParams(location.search).has('job'))selected='generator-tab';
    const index=tabs.findIndex(item=>item.id===selected);tab(index<0?0:index);
  }
  $('admin-session-retry').addEventListener('click',session);
  tabs.forEach((t,i)=> {t.addEventListener('click',()=>tab(i));t.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const n=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;tab(n);tabs[n].focus();}});});
  let resizeTimer;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if(snapshot) { renderCharts(snapshot); } }, 100); });
  session();
})();
