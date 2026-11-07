"use strict";
/** @typedef {'planned'|'in_progress'|'completed'|'on_hold'} ProjectStatus */
/** @typedef {{id:number,name:string,customer:string,site_code:string,status:ProjectStatus,health:string,start_date:string|null,rfs_date:string|null,notes:string,updated_at:string}} Project */
/** @typedef {{id:number,project_id:number,title:string,group_name:string,owner_name:string,status:ProjectStatus,effort_md:number,start_date:string|null,end_date:string|null,notes:string}} Task */
/** @typedef {{projects:Project[],tasks:Task[],permissions:string[],updated_at:string|null}} WorkspaceData */
/** Replaceable API adapter; production never falls back to illustrative records. */
class WorkspaceAdapter {
    constructor(request) { this.request = request; }
    /** @returns {Promise<WorkspaceData>} */
    load() { return this.request('/workspace'); }
    saveProject(record, id) { return this.request('/workspace/projects' + (id ? '/' + id : ''), id ? 'PATCH' : 'POST', record); }
    saveTask(record, projectId, id) { return this.request('/workspace/' + (id ? 'tasks/' + id : 'projects/' + projectId + '/tasks'), id ? 'PATCH' : 'POST', record); }
}
window.createBMSWorkspace = function({api, state, esc, byId, on, openDialog, selectView, message}) {
    const adapter = new WorkspaceAdapter(api);
    const DAY = 86400000;
    const statusLabels = {planned:'Planned / Upcoming',in_progress:'In progress',completed:'Completed',on_hold:'On hold',on_track:'On track',watch:'Watch / Risk',delayed:'Delayed'};
    const tones = {completed:['#0eac73','#e9f9f2'],on_track:['#0eac73','#e9f9f2'],planned:['#2375f6','#edf5ff'],in_progress:['#2375f6','#edf5ff'],on_hold:['#8796ad','#eff2f7'],watch:['#e7a315','#fff7e4'],delayed:['#e35868','#fff0f2']};
    const icon = name => `<svg class="hub-icon" aria-hidden="true"><use href="/bms_integration_hub/icons.svg#${name}"></use></svg>`;
    const color = key => `--tone:${(tones[key] || tones.planned)[0]};--tint:${(tones[key] || tones.planned)[1]}`;
    const badge = key => `<span class="health-badge" style="${color(key)}">${esc(statusLabels[key] || key)}</span>`;
    const day = value => value ? Date.parse(value.slice(0,10) + 'T00:00:00Z') : null;
    const fmt = value => value ? new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(value)) : 'Not scheduled';
    const iso = value => new Date(value).toISOString().slice(0,10);
    const today = () => day(new Date().toISOString());
    const empty = (title, copy, glyph='folders') => `<div class="empty-state"><span class="hub-empty-icon">${icon(glyph)}</span><h2>${esc(title)}</h2><p>${esc(copy)}</p></div>`;
    const option = (value,label,selected) => `<option value="${esc(value)}" ${String(value)===String(selected)?'selected':''}>${esc(label)}</option>`;
    const options = (map, selected) => Object.entries(map).map(([v,l])=>option(v,l,selected)).join('');
    const s = {data:null,filter:'',customer:'',health:'',query:'',from:'',to:'',sort:'rfs_date',direction:1,rfsMode:'timeline',rfsOffset:0,rfsYears:5,projectId:null,taskScale:'weekly',taskOffset:0,collapsed:new Set(),initialized:false};
    const content = () => byId('workspace-content');
    function stored(key,fallback) {try{return localStorage.getItem(key) ?? fallback;}catch{return fallback;}}
    function persist(key,value) {try{localStorage.setItem(key,value);}catch{ /* Browser storage may be unavailable. */ }}
    const sidebarLimits = () => ({min:180,max:Math.min(420,window.innerWidth - (matchMedia('(max-width:900px)').matches ? 54 : 600))});
    function setSidebarWidth(value, save=false) {
        const {min,max}=sidebarLimits();
        const width=Math.round(Math.max(min,Math.min(max,Number.isFinite(value)?value:240)));
        byId('workspace').style.setProperty('--sidebar-width',width+'px');
        const handle=byId('sidebar-resizer');
        handle.setAttribute('aria-valuenow',String(width));
        handle.setAttribute('aria-valuemin',String(min));
        handle.setAttribute('aria-valuemax',String(max));
        handle.setAttribute('aria-valuetext',width+' pixels');
        if(save)persist('bms.sidebar.width',String(width));
        return width;
    }
    function initializeSidebarResize() {
        const handle=byId('sidebar-resizer'), workspace=byId('workspace');
        let drag=null;
        handle.addEventListener('pointerdown',e=>{
            if(e.button!==0 || !e.isPrimary)return;
            e.preventDefault();
            drag={id:e.pointerId,x:e.clientX,width:byId('workspace-nav').getBoundingClientRect().width};
            workspace.classList.add('sidebar-resizing');
            handle.setPointerCapture(e.pointerId);
            handle.focus({preventScroll:true});
        });
        handle.addEventListener('pointermove',e=>{
            if(drag?.id===e.pointerId)setSidebarWidth(drag.width+e.clientX-drag.x);
        });
        const finish=e=>{
            if(drag?.id!==e.pointerId)return;
            persist('bms.sidebar.width',handle.getAttribute('aria-valuenow'));
            drag=null;workspace.classList.remove('sidebar-resizing');
            if(handle.hasPointerCapture(e.pointerId))handle.releasePointerCapture(e.pointerId);
        };
        handle.addEventListener('pointerup',finish);
        handle.addEventListener('pointercancel',finish);
        handle.addEventListener('lostpointercapture',finish);
        handle.addEventListener('keydown',e=>{
            const width=Number(handle.getAttribute('aria-valuenow'));
            const {min,max}=sidebarLimits();
            const targets={ArrowLeft:width-10,ArrowRight:width+10,Home:min,End:max};
            if(Object.hasOwn(targets,e.key)){e.preventDefault();setSidebarWidth(targets[e.key],true);}
        });
        handle.addEventListener('dblclick',()=>setSidebarWidth(240,true));
    }
    function applySidebar() {
        setSidebarWidth(Number(stored('bms.sidebar.width','240')));
        const small = matchMedia('(max-width:900px)').matches;
        const collapsed = small ? !byId('workspace').classList.contains('sidebar-mobile-expanded') : stored('bms.sidebar.collapsed','false') === 'true';
        byId('workspace').classList.toggle('sidebar-collapsed',collapsed);
        byId('sidebar-toggle').innerHTML=icon(collapsed?'panel-left-open':'panel-left-close');
        byId('sidebar-toggle').setAttribute('aria-expanded',String(!collapsed));
        byId('sidebar-toggle').setAttribute('aria-label',collapsed?'Expand sidebar':'Collapse sidebar');
    }
    function initialize() {
        byId('user-avatar').textContent = state.user.display_name.split(/\s+/).map(x=>x[0]).slice(0,2).join('').toUpperCase();
        if(s.initialized) return;
        s.initialized=true;
        document.querySelectorAll('[data-icon]').forEach(el=>el.innerHTML=icon(el.dataset.icon));
        on(byId('sidebar-toggle'),'click',()=>{
            if(matchMedia('(max-width:900px)').matches) byId('workspace').classList.toggle('sidebar-mobile-expanded');
            else persist('bms.sidebar.collapsed',String(!byId('workspace').classList.contains('sidebar-collapsed')));
            applySidebar();
        });
        initializeSidebarResize();
        window.addEventListener('resize',applySidebar);applySidebar();
        on(byId('global-search-form'),'submit',async e=>{e.preventDefault();if(state.user.status==='approved') await search(byId('global-search').value);});
        on(byId('notifications'),'click',notifications);
        on(byId('show-profile'),'click',profile);
        document.addEventListener('click',e=>{if(!e.target.closest('.profile-menu')) document.querySelector('.profile-menu').open=false;});
    }
    function heading(title,subtitle,actions='') {return `<div class="dashboard-heading"><div><p class="overline">Integration workspace</p><h1>${esc(title)}</h1><p class="muted" style="font-size:11px;margin:4px 0 0">${esc(subtitle)}</p></div><div class="heading-actions">${actions}</div></div>`;}
    function panelTitle(title,subtitle,glyph) {return `<div class="panel-title"><span class="panel-icon">${icon(glyph)}</span><div><h2>${esc(title)}</h2><p>${esc(subtitle)}</p></div></div>`;}
    async function load() {s.data=await adapter.load(); if(!s.data.projects.some(p=>p.id===s.projectId)) s.projectId=s.data.projects[0]?.id || null;updateNotifications();}
    async function render(view) {
        initialize(); document.querySelector('.profile-menu').open=false;
        byId('workspace').classList.remove('sidebar-mobile-expanded');applySidebar();
        content().innerHTML='<div class="loading-skeleton" role="status" aria-label="Loading workspace"></div><div class="loading-skeleton large"></div>';
        try {
            await load();
            if(view==='home') home();
            else if(view==='projects') projects();
            else if(view==='tasks') tasksPage();
            else if(view==='settings') settings();
            else modulePage(view);
        } catch(error) {
            content().innerHTML=empty('Workspace could not load','Please retry. Your data has not been changed.','refresh-cw')+'<button id="retry-workspace" class="secondary-button">Retry</button>';
            on(byId('retry-workspace'),'click',()=>render(view)); throw error;
        }
    }
    function kpis() {
        const cards=[['completed','Completed Projects','Delivered integrations','check'],['planned','Planned / Upcoming','Upcoming implementation','calendar-days'],['in_progress','In Progress','Active implementation','clock'],['on_hold','On Hold','Awaiting next steps','pause'],['watch','Watch / Risk','Projects needing attention','triangle-alert']];
        return `<div class="kpi-grid">${cards.map(([key,label,hint,glyph])=>{const count=s.data.projects.filter(p=>key==='watch'?['watch','delayed'].includes(p.health):p.status===key).length;return `<button class="kpi-card" data-kpi="${key}" style="${color(key)}"><span class="kpi-icon">${icon(glyph)}</span><span class="kpi-copy"><span class="kpi-value">${count}</span><span class="kpi-label">${label}</span><span class="kpi-hint">${hint}</span></span></button>`;}).join('')}</div>`;
    }
    function newProjectButton() {return state.user.is_owner?`<button id="new-project" class="primary-button" type="button">${icon('plus')} New project</button>`:'';}
    function home() {
        content().innerHTML=heading('Project overview','Your sites, delivery milestones and implementation work.',`<button id="refresh-dashboard" class="secondary-button" aria-label="Refresh dashboard">${icon('refresh-cw')}</button>${newProjectButton()}`)+kpis()+rfsPanel()+taskPanel();
        bindNewProject();on(byId('refresh-dashboard'),'click',()=>render('home'));
        content().querySelectorAll('[data-kpi]').forEach(el=>on(el,'click',()=>{s.filter=el.dataset.kpi;return selectView('projects');}));
        bindRfs();bindTasks();
    }
    function filteredProjects() {
        return s.data.projects.filter(p=>(!s.filter||(s.filter==='watch'?['watch','delayed'].includes(p.health):p.status===s.filter))&&(!s.customer||p.customer===s.customer)&&(!s.health||p.health===s.health)&&(!s.query||[p.name,p.site_code,p.customer].join(' ').toLowerCase().includes(s.query.toLowerCase()))&&(!s.from||(p.rfs_date&&p.rfs_date>=s.from))&&(!s.to||(p.rfs_date&&p.rfs_date<=s.to)))
            .sort((a,b)=>{const av=a[s.sort],bv=b[s.sort];if(!av)return bv?1:0;if(!bv)return -1;return String(av).localeCompare(String(bv))*s.direction;});
    }
    function rfsPanel() {
        const customers=[...new Set(s.data.projects.map(p=>p.customer).filter(Boolean))].sort();
        return `<section class="hub-panel" aria-label="RFS Dates"><div class="panel-heading">${panelTitle('RFS Dates','Planned RFS dates for all sites · '+(s.data.updated_at?'Updated '+fmt(s.data.updated_at):'No project updates yet'),'calendar-days')}<div class="panel-controls"><div class="segment" aria-label="RFS view">${['timeline','table'].map(v=>`<button data-rfs-mode="${v}" aria-pressed="${s.rfsMode===v}">${icon(v==='timeline'?'chart-no-axes-column':'table-2')}${v==='timeline'?'Timeline':'Table'}</button>`).join('')}</div></div></div><div class="hub-filters"><label>Project / site<input id="rfs-query" type="search" placeholder="Find a site…" value="${esc(s.query)}"></label><label>Customer<select id="rfs-customer">${option('','All customers',s.customer)}${customers.map(c=>option(c,c,s.customer)).join('')}</select></label><label>Status<select id="rfs-health">${option('','All statuses',s.health)}${options(Object.fromEntries(Object.entries(statusLabels).filter(([k])=>['on_track','in_progress','watch','on_hold','delayed'].includes(k))),s.health)}</select></label><label>RFS from<input id="rfs-from" type="date" value="${esc(s.from)}"></label><label>RFS to<input id="rfs-to" type="date" value="${esc(s.to)}"></label></div><div id="rfs-results"></div></section>`;
    }
    function rfsWindow() {
        const dates=s.data.projects.flatMap(p=>[day(p.start_date),day(p.rfs_date)]).filter(v=>v!==null);
        const year=new Date(dates.length?Math.min(...dates):today()).getUTCFullYear()+s.rfsOffset*s.rfsYears;
        return {start:Date.UTC(year,0,1),end:Date.UTC(year+s.rfsYears,0,1),ticks:Array.from({length:s.rfsYears},(_,i)=>String(year+i))};
    }
    function timelineHead(w) {return `<th class="timeline-head" scope="col"><div class="timeline-labels">${w.ticks.map(t=>`<span>${esc(t)}</span>`).join('')}</div></th>`;}
    function bar(start,end,key,w,label,title,id,task=false) {
        const a=day(start), b=day(end);
        if(a===null||b===null) return '<span class="unscheduled">Dates not set</span>';
        if(b<w.start||a>w.end)return '<span class="unscheduled">Outside displayed range</span>';
        const left=Math.max(0,(a-w.start)/(w.end-w.start)*100),right=Math.min(100,((b+DAY-w.start)/(w.end-w.start))*100);
        return `<button type="button" class="timeline-bar ${key}" ${task?'data-task':'data-project'}="${id}" style="${color(key)};left:${left}%;width:${Math.max(.6,right-left)}%" title="${esc(title)}" aria-label="${esc(title)}"><span>${esc(label)}</span></button>`;
    }
    function track(w,html) {
        const now=(today()-w.start)/(w.end-w.start)*100;
        return `<td class="timeline-track" style="--tick:${100/w.ticks.length}%">${now>=0&&now<=100?`<span class="today-marker" style="left:${now}%" title="Today"></span>`:''}${html}</td>`;
    }
    function drawRfs() {
        const rows=filteredProjects(),w=rfsWindow();
        const controls=s.rfsMode==='timeline'?`<div class="panel-controls"><button class="icon-button" id="rfs-prev" aria-label="Previous RFS period">${icon('chevron-left')}</button><span class="range-label">${w.ticks[0]} – ${w.ticks.at(-1)}</span><button class="icon-button" id="rfs-next" aria-label="Next RFS period">${icon('chevron-right')}</button><label><span class="sr-only">RFS date range</span><select id="rfs-range">${[1,2,5].map(n=>option(n,`${n} year${n>1?'s':''}`,s.rfsYears)).join('')}</select></label></div>`:'';
        byId('rfs-results').innerHTML=rows.length?`<div class="schedule-scroll" tabindex="0" role="region" aria-label="Site schedules, scroll horizontally"><table class="schedule-table"><thead><tr>${[['site_code','Site'],['customer','Customer'],['rfs_date','Planned RFS Date'],['health','Status'],['notes','Notes']].map(([key,label],i)=>`<th scope="col" ${i===0?'class="sticky-cell"':''} aria-sort="${s.sort===key?(s.direction===1?'ascending':'descending'):'none'}"><button data-sort="${key}">${label}${icon('chevrons-up-down')}</button></th>`).join('')}${s.rfsMode==='timeline'?timelineHead(w):''}</tr></thead><tbody>${rows.map(p=>`<tr><td class="sticky-cell"><button class="cell-link" data-project="${p.id}" title="${esc(p.name)}">${esc(p.site_code||p.name)}</button></td><td>${esc(p.customer||'Not set')}</td><td>${fmt(p.rfs_date)}</td><td>${badge(p.health)}</td><td title="${esc(p.notes)}">${esc(p.notes||'—')}</td>${s.rfsMode==='timeline'?track(w,bar(p.start_date||p.rfs_date,p.rfs_date,p.health,w,fmt(p.rfs_date),`${p.name}: ${fmt(p.start_date)} – ${fmt(p.rfs_date)}`,p.id)):''}</tr>`).join('')}</tbody></table></div><div class="table-footer"><span>${rows.length} assigned project${rows.length===1?'':'s'} · Dates in UTC</span>${controls}</div>`:empty(s.data.projects.length?'No sites match your filters':'No projects yet',s.data.projects.length?'Try another customer, status or date range.':state.user.is_owner?'Create your first project to start tracking RFS dates and implementation tasks.':'Your assigned projects will appear here once your administrator grants access.','calendar-days');
        byId('rfs-results').querySelectorAll('[data-sort]').forEach(el=>on(el,'click',()=>{s.direction=s.sort===el.dataset.sort?-s.direction:1;s.sort=el.dataset.sort;drawRfs();}));
        if(byId('rfs-prev')){on(byId('rfs-prev'),'click',()=>{s.rfsOffset--;drawRfs();});on(byId('rfs-next'),'click',()=>{s.rfsOffset++;drawRfs();});on(byId('rfs-range'),'change',e=>{s.rfsYears=Number(e.target.value);s.rfsOffset=0;drawRfs();});}
        bindProjectLinks(byId('rfs-results'));
    }
    function bindRfs() {
        drawRfs();
        [['rfs-query','query'],['rfs-customer','customer'],['rfs-health','health'],['rfs-from','from'],['rfs-to','to']].forEach(([id,key])=>on(byId(id),id==='rfs-query'?'input':'change',e=>{s[key]=e.target.value;drawRfs();}));
        content().querySelectorAll('[data-rfs-mode]').forEach(el=>on(el,'click',()=>{s.rfsMode=el.dataset.rfsMode;content().querySelectorAll('[data-rfs-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b===el)));drawRfs();}));
    }
    function projectSelector(){return `<label><span class="sr-only">Select project</span><select id="task-project">${s.data.projects.length?s.data.projects.map(p=>option(p.id,p.name,s.projectId)).join(''):option('','No projects','')}</select></label>`;}
    function taskPanel() {
        return `<section class="hub-panel" aria-label="Project Tasks & Timeline"><div class="panel-heading">${panelTitle('Project Tasks & Timeline','Implementation work, from collection to delivery.','list-checks')}<div class="panel-controls">${projectSelector()}${s.data.permissions.includes('tasks.create')&&s.projectId?`<button id="new-task" class="secondary-button">${icon('plus')} Add task</button>`:''}</div></div><div id="task-results"></div></section>`;
    }
    function taskWindow(tasks) {
        const dates=tasks.map(t=>day(t.start_date)).filter(x=>x!==null);
        const base=dates.length?Math.min(...dates):today();
        const length={daily:21,weekly:112,monthly:365}[s.taskScale];
        const start=(Math.floor(base/DAY)-3)*DAY+s.taskOffset*length*DAY, end=start+length*DAY;
        const n={daily:21,weekly:16,monthly:12}[s.taskScale];
        const ticks=Array.from({length:n},(_,i)=>new Intl.DateTimeFormat('en-GB',{...(s.taskScale==='monthly'?{month:'short',year:'2-digit'}:{day:'numeric',month:'short'}),timeZone:'UTC'}).format(new Date(start+(end-start)*i/n)));
        return {start,end,ticks};
    }
    function drawTasks() {
        const tasks=s.data.tasks.filter(t=>t.project_id===s.projectId), w=taskWindow(tasks);
        const allowed=s.data.permissions.includes('tasks.view');
        const controls=`<div class="panel-controls" style="margin-bottom:12px"><button id="task-prev" class="icon-button" aria-label="Previous task period">${icon('chevron-left')}</button><span class="range-label">${fmt(iso(w.start))} – ${fmt(iso(w.end))}</span><button id="task-next" class="icon-button" aria-label="Next task period">${icon('chevron-right')}</button><button id="task-today" class="secondary-button">Today</button><label><span class="sr-only">Timeline scale</span><select id="task-scale">${options({daily:'Daily',weekly:'Weekly',monthly:'Monthly'},s.taskScale)}</select></label></div>`;
        let rows='';
        const groups=[...new Set(tasks.map(t=>t.group_name))];
        groups.forEach((group,index)=>{
            const entries=tasks.filter(t=>t.group_name===group), collapsed=s.collapsed.has(s.projectId+':'+group);
            rows+=`<tr class="task-group"><td class="sticky-cell"><button class="group-toggle" data-group="${index}" aria-expanded="${!collapsed}">${icon(collapsed?'chevron-right':'chevron-down')}${esc(group)}</button></td><td>${entries.length} tasks</td><td></td><td>${entries.reduce((n,t)=>n+t.effort_md,0)}</td>${track(w,'')}</tr>`;
            if(!collapsed) rows+=entries.map(t=>`<tr><td class="sticky-cell task-name"><button class="cell-link" data-task="${t.id}">${esc(t.title)}</button></td><td>${esc(t.owner_name||'Unassigned')}</td><td>${badge(t.status)}</td><td>${t.effort_md}</td>${track(w,bar(t.start_date,t.end_date,t.status,w,'',`${t.title} · ${t.owner_name||'Unassigned'} · ${fmt(t.start_date)} – ${fmt(t.end_date)} · ${t.effort_md} MD`,t.id,true))}</tr>`).join('');
        });
        byId('task-results').innerHTML=!allowed?empty('Task access is not enabled','Your administrator can enable task viewing for your role.','list-checks'):!tasks.length?empty('No implementation tasks yet',s.projectId?'Add tasks with a group, owner and planned dates to build the project timeline.':'Select or create a project to track implementation work.','list-checks'):controls+`<div class="schedule-scroll" role="region" tabindex="0" aria-label="Task Gantt chart, scroll horizontally"><table class="schedule-table task-table"><thead><tr><th class="sticky-cell" scope="col">Task</th><th scope="col">Owner</th><th scope="col">Status</th><th scope="col">Effort (MD)</th>${timelineHead(w)}</tr></thead><tbody>${rows}</tbody></table></div><div class="table-footer"><span>${tasks.length} tasks · ${tasks.reduce((n,t)=>n+t.effort_md,0)} man-days planned</span><div class="legend">${['completed','in_progress','planned','on_hold'].map(k=>`<span style="${color(k)}">${statusLabels[k]}</span>`).join('')}<span style="--tone:#e76577">Today</span></div></div>`;
        if(byId('task-prev')) {
            on(byId('task-prev'),'click',()=>{s.taskOffset--;drawTasks();});on(byId('task-next'),'click',()=>{s.taskOffset++;drawTasks();});
            on(byId('task-today'),'click',()=>{s.taskOffset=0;const w0=taskWindow(tasks);s.taskOffset=Math.floor((today()-w0.start)/(w0.end-w0.start));drawTasks();});
            on(byId('task-scale'),'change',e=>{s.taskScale=e.target.value;s.taskOffset=0;drawTasks();});
            byId('task-results').querySelectorAll('[data-group]').forEach(el=>on(el,'click',()=>{const key=s.projectId+':'+groups[Number(el.dataset.group)];s.collapsed.has(key)?s.collapsed.delete(key):s.collapsed.add(key);drawTasks();}));
            bindTaskLinks(byId('task-results'));
        }
    }
    function bindTasks() {
        drawTasks();on(byId('task-project'),'change',e=>{s.projectId=Number(e.target.value);s.taskOffset=0;drawTasks();});
        if(byId('new-task'))on(byId('new-task'),'click',()=>taskEditor());
    }
    function bindNewProject(){if(byId('new-project'))on(byId('new-project'),'click',()=>projectEditor());}
    function projects() {
        content().innerHTML=heading('Projects',s.filter?`Filtered: ${statusLabels[s.filter]}`:'All integration projects assigned to your account.',newProjectButton())+(s.filter?'<button id="clear-project-filter" class="secondary-button" style="margin-bottom:14px">Show all projects</button>':'')+rfsPanel();
        bindNewProject();bindRfs();if(byId('clear-project-filter'))on(byId('clear-project-filter'),'click',()=>{s.filter='';projects();});
    }
    function tasksPage() {content().innerHTML=heading('Tasks','Plan, assign and track implementation work.')+taskPanel();bindTasks();}
    function bindProjectLinks(root){root.querySelectorAll('[data-project]').forEach(el=>on(el,'click',()=>projectDetail(Number(el.dataset.project))));}
    function bindTaskLinks(root){root.querySelectorAll('[data-task]').forEach(el=>on(el,'click',()=>taskDetail(Number(el.dataset.task))));}
    async function projectDetail(id) {
        await load(); const p=s.data.projects.find(p=>p.id===id);if(!p){message('This project is no longer available.',true);return;}
        s.projectId=id;
        content().innerHTML=heading(p.name,`${p.site_code||'Site not set'} · ${p.customer||'Customer not set'}`,`<button id="back-projects" class="secondary-button">All projects</button>${s.data.permissions.includes('planning.edit')?'<button id="edit-project" class="primary-button">Edit project</button>':''}`)+`<section class="hub-panel"><dl class="project-summary-grid">${[['Delivery status',badge(p.status)],['Project health',badge(p.health)],['Planned RFS',fmt(p.rfs_date)],['Planned start',fmt(p.start_date)],['Customer',esc(p.customer||'Not set')],['Site',esc(p.site_code||'Not set')]].map(([label,value])=>`<div><dt>${label}</dt><dd>${value}</dd></div>`).join('')}</dl><h2 style="margin-top:22px">Project notes</h2><p style="white-space:pre-wrap;overflow-wrap:anywhere">${esc(p.notes||'No project notes yet.')}</p></section>`+taskPanel();
        on(byId('back-projects'),'click',()=>selectView('projects'));if(byId('edit-project'))on(byId('edit-project'),'click',()=>projectEditor(p));bindTasks();
    }
    function input(label,name,value='',type='text',max=200) {return `<label>${label}<input name="${name}" type="${type}" value="${esc(value||'')}" ${type==='text'?`maxlength="${max}"`:''} ${['name','title','group_name'].includes(name)?'required':''}></label>`;}
    function projectEditor(p) {
        openDialog(`<h2 id="edit-dialog-title">${p?'Edit project':'New integration project'}</h2><p class="muted">Record the site, delivery health and current RFS plan.</p><form id="project-edit-form"><div class="hub-form-grid">${input('Project name','name',p?.name,'text',120)}${input('Customer','customer',p?.customer,'text',120)}${input('Site code','site_code',p?.site_code,'text',80)}<label>Delivery status<select name="status">${options(Object.fromEntries(Object.entries(statusLabels).filter(([k])=>['planned','in_progress','completed','on_hold'].includes(k))),p?.status||'planned')}</select></label><label>Project health<select name="health">${options(Object.fromEntries(Object.entries(statusLabels).filter(([k])=>['on_track','in_progress','watch','on_hold','delayed'].includes(k))),p?.health||'on_track')}</select></label>${input('Planned start','start_date',p?.start_date,'date')}${input('Planned RFS date','rfs_date',p?.rfs_date,'date')}<label class="full">Notes<textarea name="notes" maxlength="4000" rows="3">${esc(p?.notes||'')}</textarea></label></div><div class="form-actions"><button class="secondary-button" type="button" data-close>Cancel</button><button class="primary-button" type="submit">Save project</button></div></form>`);
        on(byId('project-edit-form'),'submit',async e=>{e.preventDefault();e.submitter.disabled=true;try{const values=Object.fromEntries(new FormData(e.target));await adapter.saveProject(values,p?.id);byId('edit-dialog').close();await render(state.view);message('Project saved.');}finally{e.submitter.disabled=false;}});
    }
    function taskDetail(id) {
        const t=s.data.tasks.find(t=>t.id===id);if(!t)return;
        openDialog(`<h2 id="edit-dialog-title">${esc(t.title)}</h2><p>${badge(t.status)}</p><p class="muted">${esc(t.group_name)} · ${esc(t.owner_name||'Unassigned')} · ${t.effort_md} MD</p><p>${fmt(t.start_date)} – ${fmt(t.end_date)}</p><p class="detail-copy">${esc(t.notes||'No task notes yet.')}</p><div class="form-actions"><button type="button" class="secondary-button" data-close>Close</button>${s.data.permissions.includes('tasks.edit')?'<button id="edit-task" class="primary-button">Edit task</button>':''}</div>`);
        if(byId('edit-task'))on(byId('edit-task'),'click',()=>{byId('edit-dialog').close();taskEditor(t);});
    }
    function taskEditor(t) {
        openDialog(`<h2 id="edit-dialog-title">${t?'Edit task':'New implementation task'}</h2><form id="task-edit-form"><div class="hub-form-grid">${input('Task title','title',t?.title)}${input('Task group','group_name',t?.group_name||'Implementation','text',120)}${input('Owner / team','owner_name',t?.owner_name)}<label>Status<select name="status">${options(Object.fromEntries(Object.entries(statusLabels).filter(([k])=>['planned','in_progress','completed','on_hold'].includes(k))),t?.status||'planned')}</select></label>${input('Planned start','start_date',t?.start_date,'date')}${input('Planned end','end_date',t?.end_date,'date')}<label>Effort (man-days)<input type="number" name="effort_md" min="0" max="100000" step="0.25" value="${t?.effort_md||0}" required></label><label class="full">Notes<textarea name="notes" maxlength="4000" rows="3">${esc(t?.notes||'')}</textarea></label></div><div class="form-actions"><button type="button" class="secondary-button" data-close>Cancel</button><button type="submit" class="primary-button">Save task</button></div></form>`);
        on(byId('task-edit-form'),'submit',async e=>{e.preventDefault();e.submitter.disabled=true;try{const values=Object.fromEntries(new FormData(e.target));values.effort_md=Number(values.effort_md);await adapter.saveTask(values,t?.project_id||s.projectId,t?.id);byId('edit-dialog').close();await render(state.view);message('Task saved.');}finally{e.submitter.disabled=false;}});
    }
    function settings() {
        content().innerHTML=heading('Settings','Your workspace preferences and account.')+`<div class="settings-grid"><button id="profile-card" class="settings-card">${icon('user')}<h2>My profile</h2><span>View your identity, role and project access.</span></button><button id="sidebar-card" class="settings-card">${icon('panel-left-close')}<h2>Sidebar preference</h2><span>Toggle the sidebar. Your preference is saved on this browser.</span></button>${state.user.is_owner?'<button id="admin-card" class="settings-card">'+icon('settings')+'<h2>Access management</h2><span>Approve users, assign projects, edit the permission matrix and review access history. Owner only.</span></button>':''}</div>`;
        on(byId('profile-card'),'click',profile);on(byId('sidebar-card'),'click',()=>byId('sidebar-toggle').click());if(byId('admin-card'))on(byId('admin-card'),'click',()=>selectView('users'));
    }
    function profile() {
        document.querySelector('.profile-menu').open=false;
        openDialog(`<h2 id="edit-dialog-title">My profile</h2><p><strong>${esc(state.user.display_name)}</strong></p><p class="muted">${esc(state.user.email)}</p><p>Role: ${esc(state.user.is_owner?'Portal owner':state.user.role_name||'Not assigned')}</p><p>Status: ${esc(state.user.status)}</p><p>Created: ${fmt(state.user.created_at)}</p><p>Last login: ${fmt(state.user.last_login_at)}</p><p class="field-note">Your profile is managed through your verified Google account.</p><div class="form-actions"><button type="button" class="primary-button" data-close>Close</button></div>`);
    }
    async function search(query) {
        await load();const q=query.trim().toLowerCase();
        const projects=q?s.data.projects.filter(p=>[p.name,p.customer,p.site_code].join(' ').toLowerCase().includes(q)):[];
        const tasks=q?s.data.tasks.filter(t=>[t.title,t.owner_name,t.group_name].join(' ').toLowerCase().includes(q)):[];
        content().innerHTML=heading('Search',q?`${projects.length+tasks.length} results for “${query.trim()}”`:'Enter a project, site or task in the search field.')+`<div class="search-results">${projects.map(p=>`<button class="search-result" data-project="${p.id}"><span>${esc(p.name)}<small>Project · ${esc(p.site_code||'No site code')} · ${esc(p.customer)}</small></span>${icon('arrow-up-right')}</button>`).join('')}${tasks.map(t=>`<button class="search-result" data-task="${t.id}"><span>${esc(t.title)}<small>Task · ${esc(s.data.projects.find(p=>p.id===t.project_id)?.name||'')}</small></span>${icon('arrow-up-right')}</button>`).join('')}</div>`+(!projects.length&&!tasks.length?empty('No matching results','Search only includes projects and tasks you are permitted to view.','search'):'');
        bindProjectLinks(content());bindTaskLinks(content());
    }
    function alerts() {
        if(!s.data)return [];
        return s.data.projects.filter(p=>p.status!=='completed'&&(['watch','delayed'].includes(p.health)||(p.rfs_date&&day(p.rfs_date)<today()))).map(p=>({id:`p${p.id}:${p.updated_at}`,project:p,text:`${p.site_code||p.name} · ${['watch','delayed'].includes(p.health)?statusLabels[p.health]:'RFS date has passed'}`}));
    }
    function updateNotifications() {const seen=stored('bms.notifications.'+state.user.id,'');const count=alerts().filter(a=>!seen.split('|').includes(a.id)).length;byId('notification-count').textContent=String(count);byId('notification-count').hidden=!count;}
    async function notifications() {
        if(state.user.status!=='approved')return;
        await load();const items=alerts();
        openDialog(`<h2 id="edit-dialog-title">Notifications</h2><p class="muted">Project risks and RFS dates requiring attention.</p>${items.length?`<div class="search-results">${items.map(a=>`<button class="search-result" data-alert-project="${a.project.id}">${esc(a.text)}${icon('arrow-up-right')}</button>`).join('')}</div>`:'<p>You’re all caught up. There are no project alerts.</p>'}<div class="form-actions"><button type="button" class="primary-button" data-close>Close</button></div>`);
        byId('edit-dialog-content').querySelectorAll('[data-alert-project]').forEach(el=>on(el,'click',()=>{byId('edit-dialog').close();return projectDetail(Number(el.dataset.alertProject));}));
        persist('bms.notifications.'+state.user.id,items.map(a=>a.id).join('|'));updateNotifications();
    }
    function modulePage(view) {
        const names={requirements:'Requirements',architecture:'Architecture',monitoring:'Monitoring'};
        const permitted=s.data.permissions.includes(view+'.view');
        content().innerHTML=heading(names[view]||'Workspace','Project workspace')+`<section class="hub-panel">${empty(permitted?`${names[view]} workspace`:'Access is not enabled',permitted?'This workspace is reserved for the next project phase. Your project directory, RFS schedules and tasks are available now.':'Ask your administrator to enable this area for your role.',view==='architecture'?'network':view==='monitoring'?'activity':'clipboard-list')}<button id="go-projects" class="secondary-button">Open projects</button></section>`;
        on(byId('go-projects'),'click',()=>selectView('projects'));
    }
    return {initialize,render,reset(){s.data=null;s.projectId=null;s.filter='';s.customer='';s.health='';s.query='';s.from='';s.to='';s.collapsed.clear();updateNotifications();}};
};
