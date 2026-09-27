/* Run with node; EXAM_DOM_MODULE may point to a temporary jsdom install. No browser engine. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const {JSDOM} = require(process.env.EXAM_DOM_MODULE || 'jsdom');
const root = path.resolve(__dirname,'..');
const code = fs.readFileSync(path.join(__dirname,'catalog.js'),'utf8');
let checks = 0;
function verify(value, message) { assert.ok(value,message); checks++; }
function setup(rel='index.htm',records=[],broken=false) {
  const file = path.join(root,rel);
  const dom = new JSDOM(fs.readFileSync(file,'utf8'), {url:pathToFileURL(file).href,runScripts:'outside-only'});
  let stored=JSON.stringify(records);
  Object.defineProperty(dom.window,'localStorage',{value: {getItem(){if(broken) throw new Error('denied'); return stored;},removeItem(){if(broken)throw new Error('denied');stored=null;},setItem(k,v){stored=v;}}});
  dom.window.eval(code);
  return dom;
}
function shown(doc){return [...doc.querySelectorAll('article.paper')].filter(x=>!x.hidden);}
function input(win,id,value,type='input'){const elem=win.document.getElementById(id);elem.value=value;elem.dispatchEvent(new win.Event(type,{bubbles:true}));}
async function main(){
  let dom=setup(),w=dom.window,d=w.document;
  verify(d.querySelectorAll('article.paper').length===335,'All 335 documents in homepage');
  verify(shown(d).length===30,'Initial progressive list of 30');
  d.getElementById('load-more').click();verify(shown(d).length===60,'Load more adds 30');
  input(w,'catalog-search','2023 408');verify(shown(d).length===2,'Global compound query includes both 408 versions');
  verify(shown(d).every(x=>x.dataset.year==='2023'&&x.dataset.category==='cs408'),'Search intersections correct');
  input(w,'filter-kind','answers','change');verify(shown(d).length===1,'Question vs answer filter');
  input(w,'catalog-search','nonexistent 试卷');verify(shown(d).length===0&&!d.getElementById('no-results').hidden,'Empty state');
  d.getElementById('empty-reset').click();await new Promise(r=>setTimeout(r,5));verify(shown(d).length===30&&d.getElementById('catalog-search')===d.activeElement,'Empty reset and focus');
  input(w,'filter-category','math3','change');verify(shown(d).length===30&&shown(d).every(x=>x.dataset.category==='math3'),'Category filter');
  input(w,'filter-year','2009','change');verify(shown(d).length===2,'Existing 2009 math docs preserved');
  verify(shown(d).every(x=>x.querySelector('.versions a').href.includes('math3-2009-2019-htm')),'No duplicate old math 2009');
  input(w,'catalog-search','<img onerror=alert(1)>');verify(!d.querySelector('#no-results img'),'No input HTML injection');
  dom.window.close();
  dom=setup('kaoyan/index.htm');d=dom.window.document;
  verify(d.querySelectorAll('article.paper').length===44,'Category scoped documents');
  verify(d.querySelectorAll('.subject-link[aria-current=page]').length===1,'Single active category');
  dom.window.close();
  const docs=JSON.parse(fs.readFileSync(path.join(root,'documents.json'),'utf8'));
  const good=docs.find(x=>x.category==='cs408');
  const url=new URL(good.reflow,pathToFileURL(path.join(root,'index.htm'))).href;
  dom=setup('index.htm',[
    {url,title:'<img onerror=alert(1)>',category:'cs408',mode:'reflow',progress:.42,updatedAt:2000},
    {url:'https://evil.invalid/steal',title:'Bad external',updatedAt:9999},
    {url:'file:///etc/passwd',title:'Bad local',updatedAt:10000},
    {url:'javascript:alert(1)',title:'Bad JS',updatedAt:10001}
  ]);d=dom.window.document;
  verify(d.querySelectorAll('.recent-card').length===1,'Only known reader links accepted');
  verify(d.querySelector('.recent-card').href.endsWith('#resume'),'Resume only explicit link');
  verify(d.querySelector('.recent-card strong').textContent==='<img onerror=alert(1)>'&&!d.querySelector('.recent-card img'),'Recent labels safely inserted');
  verify(d.querySelector('.recent-card p').textContent.includes('42%'),'Progress schema 0..1');
  d.getElementById('clear-recent').click();verify(d.querySelectorAll('.recent-card').length===0&&!d.getElementById('recent-empty').hidden,'Clear recent and empty state');
  dom.window.close();
  dom=setup('index.htm',[],true);d=dom.window.document;
  verify(d.getElementById('recent-empty').textContent.includes('无法保存'),'Storage failure explained');
  input(dom.window,'catalog-search','2014 408');verify(shown(d).length===1,'Filters usable with blocked storage');
  dom.window.close();
  for (const rel of ['math3/svg.htm','math3/latex.htm','cs408/latex.htm','politics/latex.htm']) {
    dom=setup(rel);d=dom.window.document;
    verify([...d.querySelectorAll('.paper')].every(c=>c.querySelector('.cover-link').href===c.querySelectorAll('.versions a')[rel.includes('latex')?1:0].href),'Special version route '+rel);
    dom.window.close();
  }
  console.log(JSON.stringify({checks,passed:true,engine:'jsdom (DOM only, no layout/browser)',documents:docs.length},null,2));
}
main().catch(e=>{console.error(e);process.exit(1);});
