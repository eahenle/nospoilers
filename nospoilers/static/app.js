'use strict';
const $ = id => document.getElementById(id);
let mode = localStorage.getItem('nospoilers-mode') === 'demo' ? 'demo' : 'real';
let state = null, current = null, activeView = 'tonight', searchTimer, searchGeneration=0;
$('mode').value = mode;
const el = (tag, text, cls) => { const n=document.createElement(tag); if(text!==undefined) n.textContent=text; if(cls)n.className=cls; return n; };
function notice(message, error=false){$('notice').textContent=message;$('notice').className=error?'error':'';$('notice').hidden=!message;}
async function api(path,data){
  const response=await fetch(path,{method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),cache:'no-store'});
  if(!response.ok)throw new Error('The request could not be completed. Check your settings and try again.');
  return response.json();
}
async function safely(action){try{await action();}catch(_){notice('The request could not be completed. Check your settings and try again.',true);}}
function navigate(view){
  activeView=view;for(const n of document.querySelectorAll('.view'))n.hidden=n.id!=='view-'+view;
  for(const n of document.querySelectorAll('.nav'))n.classList.toggle('active',n.dataset.view===view);
  $('section-name').textContent={tonight:'YOUR NEXT GOOD EVENING',history:'YOUR TASTE, OVER TIME',setup:'A PLACE TO BEGIN'}[view];
  if(view==='history')safely(loadHistory);if(view==='setup')safely(loadDiagnostics);
}
for(const b of document.querySelectorAll('[data-view]'))b.addEventListener('click',()=>navigate(b.dataset.view));
function clearPick(){current=null;$('pick-empty').hidden=false;$('pick-result').hidden=true;$('pick-abstain').hidden=true;$('feedback').hidden=true;$('another').hidden=true;$('pick').textContent='Pick for me ↗';$('feedback-note').value='';}
function addDefinition(parent,key,value){const row=el('div');row.append(el('dt',key),el('dd',value));parent.append(row);}
async function refresh(){
  const requestedMode=mode;
  const result=await api('/api/state?mode='+requestedMode);
  if(requestedMode!==mode)return;
  state=result;$('history-count').textContent=state.watched_count;
  $('demo-banner').hidden=mode!=='demo';
  const c=state.constraints;
  $('max-runtime').value=c.max_runtime??'';$('region').value=c.region??'US';$('providers').value=(c.providers??[]).join(', ');
  const access=(c.access_types??['included']).join(',');
  // Preserve imported/custom access settings by offering their exact value.
  if(![...$('access').options].some(o=>o.value===access))$('access').append(new Option(access,access));
  $('access').value=access;$('mood').value=c.mood??'';$('show-runtime').checked=c.show_runtime!==false;$('show-availability').checked=c.show_availability!==false;
  $('settings-summary').replaceChildren();
  for(const [k,v] of [['Runtime',c.max_runtime?'Up to '+c.max_runtime+' min':'Any length'],['Catalog',c.providers?.length?c.providers.join(', '):'Unrestricted'],['Region',c.region??'US'],['Mood',{calm:'Calm',bright:'Bright',absorbing:'Absorbing'}[c.mood]??'Open to anything']])addDefinition($('settings-summary'),k,v);
  $('taste-message').textContent=state.personalized?`${state.rated_count} recorded reactions. Compatible private features are helping shape your next pick.`:state.rated_count?'Unpersonalized for now: your rated movies need compatible private features.':'Unpersonalized for now. A few reactions to movies you’ve seen are a good place to start.';
  $('pick-caption').textContent=state.catalog_count?'No trailers. No rabbit holes. No spoilers.':'Your catalog is empty. Start with the fictional demo in Setup.';
}
$('mode').addEventListener('change',()=>safely(async()=>{mode=$('mode').value;localStorage.setItem('nospoilers-mode',mode);clearPick();$('search').value='';$('search-results').replaceChildren();searchGeneration++;notice('');await refresh();if(activeView==='history')await loadHistory();}));
$('settings-toggle').addEventListener('click',()=>{const hidden=!$('settings-form').hidden;$('settings-form').hidden=hidden;$('settings-toggle').setAttribute('aria-expanded',String(!hidden));});
$('empty-settings').addEventListener('click',()=>{$('settings-form').hidden=false;$('settings-toggle').setAttribute('aria-expanded','true');$('max-runtime').focus();});
$('settings-form').addEventListener('submit',e=>{e.preventDefault();safely(async()=>{
  const constraints={max_runtime:$('max-runtime').value?Number($('max-runtime').value):null,region:$('region').value.toUpperCase(),providers:$('providers').value.split(',').map(x=>x.trim()).filter(Boolean),access_types:$('access').value.split(','),mood:$('mood').value||null,show_runtime:$('show-runtime').checked,show_availability:$('show-availability').checked};
  await api('/api/settings',{mode,constraints});clearPick();await refresh();$('settings-form').hidden=true;$('settings-toggle').setAttribute('aria-expanded','false');notice('Defaults saved. Your next pick will use these settings.');
});});
async function pick(another=false){
  $('pick').disabled=true;$('another').disabled=true;notice('');
  try{
    const requestedMode=mode;
    const response=await api(another?'/api/another':'/api/pick',another?{mode,id:current.id}:{mode});
    if(requestedMode!==mode)return;
    $('pick-empty').hidden=true;
    if(!response.movie){current=null;$('pick-result').hidden=true;$('pick-abstain').hidden=false;$('empty-message').textContent=response.message;$('feedback').hidden=true;$('another').hidden=true;return;}
    current=response.movie;$('feedback-note').value='';$('pick-result').hidden=false;$('pick-abstain').hidden=true;$('another').hidden=false;$('feedback').hidden=false;
    $('movie-title').textContent=current.title;$('movie-meta').textContent=[current.year,state.constraints.show_runtime!==false&&current.runtime?current.runtime+' min':null].filter(Boolean).join(' · ');
    $('watch-links').replaceChildren();
    if(state.constraints.show_availability!==false){
      for(const offer of current.availability){const a=el('a',offer.provider+' · '+offer.access_type+' ↗','watch-link');a.href=offer.url;a.target='_blank';a.rel='noopener noreferrer';$('watch-links').append(a);}
      $('availability-note').textContent=current.availability.length?'Availability checked within the last 7 days.':mode==='demo'?'Fictional title. No real streaming availability.':'Availability unknown. No verified watch link.';
    }else $('availability-note').textContent='';
    $('pick').textContent='Pick for me ↗';
  }finally{$('pick').disabled=false;$('another').disabled=false;}
}
$('pick').addEventListener('click',()=>safely(()=>pick()));$('another').addEventListener('click',()=>safely(()=>pick(true)));
$('reset').addEventListener('click',()=>safely(async()=>{await api('/api/reset',{mode});clearPick();notice('This session’s skips were reset. Your ratings are unchanged.');}));
for(const b of document.querySelectorAll('[data-reaction]'))b.addEventListener('click',()=>safely(async()=>{if(!current)return;await api('/api/reaction',{mode,id:current.id,rating:b.dataset.reaction==='unrated'?null:b.dataset.reaction,notes:$('feedback-note').value});clearPick();await refresh();notice('Saved to your watched history. Ready when you are.');}));
const ratingOptions=[['','Seen, unrated'],['liked','Liked'],['neutral','Neutral'],['disliked','Disliked']];
function ratingSelect(rating){const s=el('select');s.setAttribute('aria-label','Reaction');for(const [v,t] of ratingOptions){const o=el('option',t);o.value=v;s.append(o);}s.value=rating??'';return s;}
function movieRow(m,existing){const box=el('article',undefined,'history-item');box.append(el('h3',m.title),el('p',String(m.year)));const select=ratingSelect(m.rating);select.setAttribute('aria-label','Reaction to '+m.title);const notes=el('input');notes.maxLength=2000;notes.placeholder='Private note (optional)';notes.value=m.notes??'';notes.setAttribute('aria-label','Private note for '+m.title);const button=el('button',existing?'Update reaction':'Mark watched','secondary');button.addEventListener('click',()=>safely(async()=>{button.disabled=true;try{await api('/api/reaction',{mode,id:m.id,rating:select.value||null,notes:notes.value});if(current?.id===m.id)clearPick();await refresh();await loadHistory();if(!existing){box.remove();}notice('Reaction saved. Each title has one current rating.');}finally{button.disabled=false;}}));box.append(select,notes,button);return box;}
async function loadHistory(){const requestedMode=mode;const response=await api('/api/history?mode='+mode);if(requestedMode!==mode)return;$('history-list').replaceChildren();$('rated-total').textContent='('+response.history.length+')';if(!response.history.length)$('history-list').append(el('p','A clean slate. Add a movie you’ve already seen.','muted'));for(const m of response.history)$('history-list').append(movieRow(m,true));}
$('search').addEventListener('input',()=>{clearTimeout(searchTimer);const generation=++searchGeneration;searchTimer=setTimeout(()=>safely(async()=>{const q=$('search').value.trim();if(!q){$('search-results').replaceChildren();return;}const response=await api('/api/search?mode='+mode+'&q='+encodeURIComponent(q));if(generation!==searchGeneration)return;$('search-results').replaceChildren();if(!response.movies.length)$('search-results').append(el('p','No matching title in this catalog. Import it using the tools in Setup.','muted'));for(const m of response.movies)$('search-results').append(movieRow(m,false));}),180);});
$('load-demo').addEventListener('click',()=>safely(async()=>{await api('/api/demo',{});mode='demo';$('mode').value=mode;localStorage.setItem('nospoilers-mode',mode);clearPick();await refresh();navigate('tonight');notice('Fictional demo loaded. No ratings were added.');}));
$('load-history').addEventListener('click',()=>safely(async()=>{await api('/api/demo',{});await api('/api/demo-history',{});mode='demo';$('mode').value=mode;localStorage.setItem('nospoilers-mode',mode);clearPick();await refresh();notice('Three synthetic reactions added to the separate demo profile.');}));
async function loadDiagnostics(){const d=await api('/api/diagnostics');$('diagnostics').replaceChildren();for(const [k,v] of [['Backend',d.backend],['Schema',d.schema_version],['Reference fallback',d.fallback_enabled?'Enabled':'Disabled'],['Fallback uses',d.fallback_count],['Last selection',d.last_selection_ms===null?'No picks yet':d.last_selection_ms+' ms'],['Extraction',d.extraction]])addDefinition($('diagnostics'),k,String(v));}
safely(refresh);
