/* Local link detection only: this module makes no network requests. */
((root)=>{
  'use strict';
  let cachedTopic=null,cachedManual=null,cached=null;
  function extract(topic,manual='') {
    topic=String(topic || '');manual=String(manual || '');
    if(topic===cachedTopic && manual===cachedManual)return cached;
    const sources={youtube:[],references:[]},seen=new Set();
    const pattern=/https?:\/\/[^\s<>"'`]+|\b(?:www\.|youtube\.com\/|youtu\.be\/)[^\s<>"'`]+|\b10\.\d{4,9}\/[^\s<>"'`]+/giu;
    for(const text of [topic,manual])for(const match of String(text || '').matchAll(pattern)) {
      let value=match[0].replace(/&amp;/gi,'&').replace(/[.,;:!?，。；：！？*]+$/u,'');
      for(const [left,right] of [['(',')'],['[',']'],['{','}']]) {
        const extra=value.split(right).length-value.split(left).length;let trailing=0;
        if(extra>0){while(value[value.length-1-trailing]===right)trailing++;if(trailing)value=value.slice(0,-Math.min(extra,trailing));}
      }
      if(/^(?:www\.|youtube\.com\/|youtu\.be\/)/i.test(value))value='https://'+value;
      else if(/^10\.\d{4,9}\//i.test(value))value='https://doi.org/'+value;
      try {
        const url=new URL(value);if(!['http:','https:'].includes(url.protocol) || !url.hostname || url.username || url.password)continue;
        const host=url.hostname.toLowerCase(),path=url.pathname.split('/').filter(Boolean);let video='';
        if(['youtu.be','www.youtu.be'].includes(host))video=path[0] || '';
        else if(['youtube.com','www.youtube.com','m.youtube.com','music.youtube.com','youtube-nocookie.com','www.youtube-nocookie.com'].includes(host)) {
          if(path[0]==='watch')video=url.searchParams.get('v') || '';
          else if(['shorts','live','embed'].includes(path[0]))video=path[1] || '';
        }
        const isVideo=/^[A-Za-z0-9_-]{11}$/.test(video),canonical=isVideo?'https://www.youtube.com/watch?v='+video:url.href;
        if(!seen.has(canonical)){seen.add(canonical);sources[isVideo?'youtube':'references'].push(canonical);}
      }catch {}
    }
    cachedTopic=topic;cachedManual=manual;cached=sources;return sources;
  }
  root.NxfloSources={extract};if(typeof module!=='undefined' && module.exports)module.exports={extract};
})(typeof globalThis!=='undefined'?globalThis:this);
