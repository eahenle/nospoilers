// Execute the shipped UI code with lightweight DOM and transport fixtures.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

function harness() {
  class Element {
    constructor() { this.children=[]; this.handlers={}; this.value=''; this.options=[]; this.dataset={}; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children=nodes; }
    setAttribute() {}
    addEventListener(name, fn) { this.handlers[name]=fn; }
    remove() {}
  }
  const elements=new Map();
  const get=id=>{ if(!elements.has(id))elements.set(id,new Element()); return elements.get(id); };
  const posts=[], pending=[], timers=[];
  const context=vm.createContext({document:{getElementById:get,createElement:()=>new Element(),querySelectorAll:()=>[]},
    localStorage:{getItem:()=> 'demo',setItem(){}},setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout(){},
    fetch:async(path,options)=>{ if(options.method==='POST')posts.push(JSON.parse(options.body)); return new Promise(resolve=>pending.push({path,resolve})); }});
  vm.runInContext(fs.readFileSync(new URL('../nospoilers/static/app.js',import.meta.url),'utf8'),context);
  return {context,posts,get,pending,timers};
}

test('a retained demo row cannot write a reaction after switching to personal mode',async()=>{
  const {context,posts}=harness();
  const row=vm.runInContext("movieRow({id:'fixture:shared',title:'Demo title',year:2000},true)",context);
  vm.runInContext("mode='real'",context);
  row.children.at(-1).handlers.click();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(posts.length,0,'stale row submitted a reaction in the new mode');
});

test('mode changes immediately remove history controls while refresh is pending',async()=>{
  const {context,get}=harness();
  get('history-list').append({old:'demo row'});
  get('mode').value='real';
  get('mode').handlers.change();
  assert.equal(get('history-list').children.length,0);
});


test('a current row still submits its originating mode and selected reaction',async()=>{
  const {context,posts}=harness();
  const row=vm.runInContext("movieRow({id:'fixture:shared',title:'Demo title',year:2000,rating:'liked'},true)",context);
  row.children.at(-1).handlers.click();
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(posts,[{mode:'demo',id:'fixture:shared',rating:'liked',notes:''}]);
});

test('an old-mode reaction completion does not clear a new-mode pick',async()=>{
  const {context,pending}=harness();
  const row=vm.runInContext("movieRow({id:'fixture:shared',title:'Demo title',year:2000},true)",context);
  row.children.at(-1).handlers.click();
  vm.runInContext("mode='real';current={id:'fixture:shared'}",context);
  pending.find(r=>r.path==='/api/reaction').resolve({ok:true,json:async()=>({ok:true})});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(vm.runInContext('current.id',context),'fixture:shared');
  assert.equal(pending.length,2,'stale completion must not refresh or load new-mode history');
});


test('a pending search cannot rebind results after a programmatic mode change',async()=>{
  const {context,get,pending,timers}=harness();
  vm.runInContext("mode='real'",context);
  get('search').value='real title';
  get('search').handlers.input();
  timers.at(-1)();
  vm.runInContext("mode='demo'",context);
  pending.find(r=>r.path.startsWith('/api/search')).resolve({ok:true,json:async()=>({movies:[{id:'fixture:shared',title:'Real title',year:2000}]})});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(get('search-results').children.length,0,'old-mode results became new-mode reaction rows');
});
