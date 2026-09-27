const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL,fileURLToPath} = require('node:url');
const {JSDOM} = require('jsdom');
const page=path.resolve(__dirname,'../image-review.htm');
const html=fs.readFileSync(page,'utf8'), script=fs.readFileSync(path.join(__dirname,'image-review.js'),'utf8');
for(const denied of [false,true]) {
 const dom=new JSDOM(html,{url:pathToFileURL(page).href,runScripts:'outside-only'}),w=dom.window,d=w.document;
 const saved=new Map();let blob,downloaded=false;
 Object.defineProperty(w,'localStorage',{value:{getItem(k){if(denied)throw Error('denied');return saved.get(k)||null},setItem(k,v){if(denied)throw Error('denied');saved.set(k,v)}}});
 w.Blob=class{constructor(parts){this.text=parts.join('')}};
 w.URL.createObjectURL=b=>{blob=b;return 'blob:review-test'};w.URL.revokeObjectURL=()=>{};
 w.HTMLAnchorElement.prototype.click=function(){downloaded=this.download==='exam-image-review.json'};
 w.HTMLDialogElement.prototype.showModal=function(){this.open=true};w.HTMLDialogElement.prototype.close=function(){this.open=false};
 w.eval(script);
 const cards=[...d.querySelectorAll('.review-item')], count=JSON.parse(d.querySelector('#review-data').textContent).length;
 assert.equal(cards.length,count);assert(count>0);
 for(const el of d.querySelectorAll('img[src],a[href],link[href],script[src]')) {const ref=el.getAttribute('src')||el.getAttribute('href');assert(fs.existsSync(fileURLToPath(new URL(ref,pathToFileURL(page)))),ref)}
 const first=cards[0],decision=first.querySelector('.decision'),note=first.querySelector('.note');
 decision.value='revise';decision.dispatchEvent(new w.Event('change'));note.value='检查箭头方向';note.dispatchEvent(new w.Event('input'));
 if(denied)assert(d.querySelector('#storage-status').textContent.includes('导出'));
 else {const result=JSON.parse(saved.get('exam-library:image-review:v1'));assert.equal(result[first.dataset.id].note,note.value);assert.equal(result[first.dataset.id].decision,'revise')}
 const state=d.querySelector('#state');state.value='revise';state.dispatchEvent(new w.Event('change'));assert.equal(cards.filter(c=>!c.hidden).length,1);
 state.value='all';state.dispatchEvent(new w.Event('change'));
 const category=d.querySelector('#category');category.value=first.dataset.category;category.dispatchEvent(new w.Event('change'));assert(cards.filter(c=>!c.hidden).every(c=>c.dataset.category===category.value));
 const search=d.querySelector('#search');search.value='unmatchable-review-test';search.dispatchEvent(new w.Event('input'));assert(cards.every(c=>c.hidden));assert.equal(d.querySelector('#empty').hidden,false);
 d.querySelector('#export').click();assert(downloaded);const output=JSON.parse(blob.text);assert.equal(output.images.length,count,'export includes hidden cards');assert.equal(output.pathBase,'data/sources/exam-library/');assert.equal(output.images[0].note,note.value);
 first.querySelector('.zoom').click();assert(d.querySelector('#zoom-dialog').open);assert.equal(d.querySelector('#zoom-image').src,first.querySelector('img').src);
 const scale=d.querySelector('#zoom-scale');scale.value='2';scale.dispatchEvent(new w.Event('change'));assert.equal(d.querySelector('#zoom-image').style.width,'200%');d.querySelector('#close-zoom').click();assert.equal(d.querySelector('#zoom-dialog').open,false);
 dom.window.close();console.log(`PASS image review ${count} pairs / storage ${denied?'denied':'available'} (DOM only)`);
}
