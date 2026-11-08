/* Locally paginated print layout; the source document remains unchanged. */
'use strict';
window.PagedConfig={auto:false};
window.addEventListener('DOMContentLoaded',async()=>{
  const status=document.createElement('p');status.textContent='Preparing page preview…';status.setAttribute('role','status');document.body.prepend(status);
  try{
    status.remove();
    await window.PagedPolyfill.preview();
    const style=document.createElement('style');
    style.textContent=`@media screen{html,body{background:#e8e9ed!important;overflow-x:hidden}.preview-toolbar{position:fixed;top:0;left:0;right:0;z-index:30;display:flex;align-items:center;justify-content:center;gap:12px;flex-wrap:wrap;padding:10px;background:#fff;border-bottom:1px solid #cbd1d9;font:14px/1.5 Arial,sans-serif}.preview-toolbar button,.preview-toolbar select{min-height:44px;padding:6px 12px;border:1px solid #aebac4;border-radius:5px;background:white;color:#152a45;font:inherit}.preview-toolbar button:focus-visible,.preview-toolbar select:focus-visible{outline:3px solid #5469db;outline-offset:2px}.pagedjs_pages{display:block!important;padding:18px 10px!important;box-sizing:border-box}.preview-sheet{overflow:auto;position:relative;margin:0 auto 26px;background:white;box-shadow:0 3px 13px #152a4530}.preview-sheet>.pagedjs_page{position:absolute;top:0;left:0;margin:0!important;transform-origin:top left}.preview-page-label{text-align:center;font:12px/1.5 Arial,sans-serif;color:#43536b;margin:0 0 8px}.preview-sheet{scroll-margin-top:90px}}`;
    document.head.append(style);
    const pages=[...document.querySelectorAll('.pagedjs_page')];
    const toolbar=document.createElement('nav');toolbar.className='preview-toolbar';toolbar.setAttribute('aria-label','Document pages');
    const previous=document.createElement('button');previous.textContent='Previous';
    const next=document.createElement('button');next.textContent='Next';
    const select=document.createElement('select');select.setAttribute('aria-label','Go to page');
    pages.forEach((page,index)=>{
      const option=document.createElement('option');option.value=index;option.textContent=`Page ${index+1} of ${pages.length}`;select.append(option);
      const label=document.createElement('p');label.className='preview-page-label';label.textContent=`Page ${index+1} of ${pages.length}`;
      const sheet=document.createElement('section');sheet.className='preview-sheet';sheet.setAttribute('aria-label',`Page ${index+1}`);
      page.before(label,sheet);sheet.append(page);
    });
    const zoom=document.createElement('select');zoom.setAttribute('aria-label','Page zoom');[['fit','Fit page'],['1','100%'],['1.25','125%']].forEach(([value,label])=>{const option=document.createElement('option');option.value=value;option.textContent=label;zoom.append(option);});
    toolbar.append(previous,select,next,zoom);document.body.prepend(toolbar);
    const sheets=[...document.querySelectorAll('.preview-sheet')];
    function fit(){document.body.style.setProperty('padding-top',toolbar.offsetHeight+'px','important');const available=Math.max(200,document.documentElement.clientWidth-20);pages.forEach((page,i)=>{const width=page.offsetWidth,height=page.offsetHeight,scale=zoom.value==='fit'?Math.min(1,available/width):Number(zoom.value);page.style.transform=`scale(${scale})`;sheets[i].style.width=`${Math.min(available,width*scale)}px`;sheets[i].style.height=`${height*scale}px`;});}
    function go(index){index=Math.max(0,Math.min(pages.length-1,index));select.value=index;window.scrollTo({top:window.scrollY+sheets[index].getBoundingClientRect().top-toolbar.offsetHeight-20});previous.disabled=index===0;next.disabled=index===pages.length-1;}
    previous.onclick=()=>go(Number(select.value)-1);next.onclick=()=>go(Number(select.value)+1);select.onchange=()=>go(Number(select.value));
    let scrollPending=false;window.addEventListener('scroll',()=>{if(scrollPending)return;scrollPending=true;requestAnimationFrame(()=>{const index=sheets.findIndex(sheet=>sheet.getBoundingClientRect().bottom>toolbar.offsetHeight+10);if(index>=0){select.value=index;previous.disabled=index===0;next.disabled=index===pages.length-1;}scrollPending=false;});},{passive:true});
    zoom.onchange=fit;
    new ResizeObserver(fit).observe(document.documentElement);fit();previous.disabled=true;
    document.body.dataset.pagination='ready';
  }catch(error){status.textContent='Page preview could not load. Download the HTML to review the document.';document.body.prepend(status);document.body.dataset.pagination='failed';}
});
