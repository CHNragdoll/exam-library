/* node reader.test.cjs; jsdom is a temporary test-only dependency, never shipped. */
const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const base = path.resolve(__dirname, '../..');
const script = fs.readFileSync(path.join(__dirname, 'reader.js'), 'utf8');
const readerCss = fs.readFileSync(path.join(__dirname, 'reader.css'), 'utf8');
const files = [
 ['english-exams-reflow-latex/kaoyan/papers/2014-01.htm','reflow'],
 ['english-exams-reflow-latex/cet6/papers/2015-12-01.htm','reflow'],
 ['math3-latex-2009-2019/papers/2019-answers.htm','reflow'],
 ['politics-answers-latex-2009-2023/papers/2019-answers.htm','reflow'],
 ['cs408-original/papers/2023-questions.htm','svg']
];
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
async function fixture(relative, mode, {denied=false,resume=false,previous=false,badUrl=false,embedded=false,compare=false}={}) {
 const file = path.join(base, relative);
 const url = new URL(`file://${file}`).href;
 const dom = new JSDOM(fs.readFileSync(file,'utf8'), {url:url+(embedded?'?exam-embed=1':'')+(resume?'#resume':''),runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window,d=w.document,m=d.querySelector('main');
 const map = new Map();
 if(previous)map.set('exam-library:recent:v1',JSON.stringify([{url,progress:.5,scrollY:4000,updatedAt:Date.now()}]));
 Object.defineProperty(w,'localStorage',{value:{getItem(k){if(denied)throw Error('denied');return map.get(k)||null},setItem(k,v){if(denied)throw Error('denied');map.set(k,v)}}});
 let scroll=0;Object.defineProperty(w,'scrollY',{get:()=>scroll});w.scrollTo=o=>{scroll=o.top;w.dispatchEvent(new w.Event('scroll'))};
 m.getBoundingClientRect=()=>({top:200-scroll,height:10000});
 d.querySelectorAll('#exam-reader-config').forEach(n=>n.remove());
 const c=d.createElement('script');c.id='exam-reader-config';c.type='application/json';
 c.textContent=JSON.stringify({title:'试卷测试',category:relative.includes('/cet6/')?'cet6':'kaoyan',documentId:relative.includes('2015-12-02.htm')?'cet6:2015-12-02':'test',categoryLabel:'考研英语',mode,libraryHref:'../../exam-library/index.htm',categoryHref:'../index.htm',alternateHref:badUrl?'javascript:alert(1)':'other.htm'});
 d.body.append(c);
 const textBefore=m.textContent, formula=d.querySelector('[data-toggle-source]'), svgCount=m.querySelectorAll('svg').length, imageCount=m.querySelectorAll('img').length;
 w.eval(script);w.dispatchEvent(new w.Event('load'));await wait(20);
 assert.equal(m.textContent,textBefore,'exam text unchanged');assert.equal(m.querySelectorAll('svg').length,svgCount,'formulas unchanged');assert.equal(m.querySelectorAll('img').length,imageCount,'figures unchanged');
 if(relative.includes('cet6/papers/2015-12-01.htm')) {
  const note=m.querySelector('.reader-answer-sheet-note');
  assert(note && note.textContent.includes('答题卡1'),'answer-sheet note starts its own paragraph');
  assert(!note.previousElementSibling.textContent.includes('注意：'),'note no longer trails directions');
  const first=[...m.querySelectorAll('.reader-listening-question')].find(row=>row.querySelector('.question')?.textContent.trim()==='1.');
  assert(first && first.querySelector('ul.options'),'bare listening number shares a row with A/B options');
 }
 if(relative.includes('cet6/papers/2015-12-02.htm')) {
  const caption=m.querySelector('p.reader-cartoon-followup');
  assert(caption && caption.textContent.includes('We just don’t have much useful information.'),'cartoon reply is centered below figure');
  assert(!caption.textContent.includes('注意：'),'answer-sheet note stays separate from caption');
  assert.match(readerCss,/p\.reader-cartoon-followup\{text-align:center;text-align-last:center\}/);
 }
 assert.equal(d.querySelector('[data-toggle-source]'),formula,'original formula control retained');
 if(embedded) {
  assert(d.body.classList.contains('reader-embed'));assert.equal(d.querySelectorAll('.reader-toolbar').length,0);assert.equal(d.querySelectorAll('iframe').length,0);
  w.dispatchEvent(new w.Event('pagehide'));assert(!map.has('exam-library:recent:v1'),'embedded document never writes recent state');dom.window.close();return relative;
 }
 assert.equal(d.querySelectorAll('.reader-toolbar').length,1);w.eval(script);assert.equal(d.querySelectorAll('.reader-toolbar').length,1,'idempotent enhancement');
 assert(d.querySelector('.reader-toc').options.length>0);
 if(badUrl){assert.equal(d.querySelectorAll('.reader-versions a').length,0,'reject unsafe scheme');assert(![...d.querySelectorAll('.reader-version')].some(x=>x.textContent==='并排对比'),'unsafe alternate cannot enable comparison');}else assert.equal(d.querySelector('.reader-versions a').href,new URL('other.htm',url).href);
 if(resume&&previous)assert(scroll>4000,'explicitly resume');else assert.equal(scroll,0,'never silently resume');
 if(compare) {
  w.scrollTo({top:2500});await wait(30);
  const compareButton=[...d.querySelectorAll('.reader-version')].find(x=>x.textContent==='并排对比');compareButton.click();
  assert(d.body.classList.contains('reader-comparing'));assert.equal(compareButton.getAttribute('aria-pressed'),'true');
  const frames=[...d.querySelectorAll('.reader-compare-frame')];assert.equal(frames.length,2);
  const own=new URL(url),other=new URL('other.htm',url);own.searchParams.set('exam-embed','1');other.searchParams.set('exam-embed','1');
  assert.equal(frames[0].src,mode==='svg'?own.href:other.href,'left is SVG');assert.equal(frames[1].src,mode==='svg'?other.href:own.href,'right is reflow');
  assert(frames[0].title.includes('SVG 原版'));assert(frames[1].title.includes('LaTeX 重排'));
  for(const a of d.querySelectorAll('.reader-compare-open')){assert.equal(a.target,'_blank');assert(!a.href.includes('exam-embed'));}
  assert.equal(m.textContent,textBefore,'comparison retains original text');assert.equal(m.querySelectorAll('svg').length,svgCount);assert.equal(m.querySelectorAll('img').length,imageCount);
  const recordDuring=map.get('exam-library:recent:v1');w.scrollTo({top:90000});await wait(30);w.dispatchEvent(new w.Event('pagehide'));assert.equal(map.get('exam-library:recent:v1'),recordDuring,'compare view does not contaminate reading progress');
  d.querySelector('.reader-compare-overview button').click();assert(!d.body.classList.contains('reader-comparing'));assert.equal(scroll,2500,'restores single-page scroll');assert(d.querySelector('.reader-comparison').hidden);
  compareButton.click();assert.equal(d.querySelectorAll('.reader-compare-frame').length,2,'reuses independent frames');
  const active=[...d.querySelectorAll('.reader-version')].find(x=>x.textContent===(mode==='svg'?'SVG 原版':'LaTeX 重排'));active.click();assert(!d.body.classList.contains('reader-comparing'),'single version exits compare');
  compareButton.click();d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape'}));assert(!d.body.classList.contains('reader-comparing'),'Escape exits when focus is in parent');
  dom.window.close();return relative;
 }

 const focus=[...d.querySelectorAll('.reader-button')].find(x=>x.textContent==='专注阅读');focus.click();assert.equal(focus.getAttribute('aria-pressed'),'true');focus.click();assert.equal(focus.getAttribute('aria-pressed'),'false');
 const settings=d.querySelector('.reader-settings');settings.open=true;d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape'}));assert(!settings.open,'Escape dismisses settings');
 if(mode==='reflow') {
  const more=[...d.querySelectorAll('button')].find(x=>x.textContent==='增大');more.click();assert.equal(d.body.style.getPropertyValue('--reader-font-size'),'20px');
  for(let i=0;i<10;i++)more.click();assert.equal(d.body.style.getPropertyValue('--reader-font-size'),'26px');assert(more.disabled,'max size is bounded');
  const width=d.querySelector('[aria-label="阅读宽度"]');width.value='760';width.dispatchEvent(new w.Event('change'));assert.equal(d.body.style.getPropertyValue('--reader-width'),'760px');
 } else {
  const zoom=d.querySelector('[aria-label="原卷缩放"]');zoom.value='150';zoom.dispatchEvent(new w.Event('change'));assert(d.body.classList.contains('reader-zoomed'));assert.equal(d.body.style.getPropertyValue('--reader-svg-width'),'1500px');zoom.value='fit';zoom.dispatchEvent(new w.Event('change'));assert(!d.body.classList.contains('reader-zoomed'));
 }
 if(denied)assert(d.querySelector('.reader-storage-status').textContent.includes('不允许保存'),'storage denied gracefully');
 const toc=d.querySelector('.reader-toc');toc.value='1';toc.dispatchEvent(new w.Event('change'));assert(d.activeElement.id,'TOC moves keyboard focus');
 w.scrollTo({top:5000});await wait(30);w.dispatchEvent(new w.Event('pagehide'));
 if(!denied){const records=JSON.parse(map.get('exam-library:recent:v1'));assert.equal(records[0].url,url);assert(records[0].progress>=0&&records[0].progress<=1);assert.equal(records.filter(x=>x.url===url).length,1);assert.equal(typeof records[0].updatedAt,'number');}
 dom.window.close();return relative;
}
function redrawFixture({embedded=false, mode='reflow', originalSize=[90, 80], expectedWidth='280px', delayedSize=false}={}) {
 const file=path.join(base,files[0][0]);
 const url=new URL(`file://${file}`).href;
 const dom=new JSDOM(fs.readFileSync(file,'utf8'),{url:url+(embedded?'?exam-embed=1':''),runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window,d=w.document,m=d.querySelector('main');
 Object.defineProperty(w,'localStorage',{value:{getItem(){return null},setItem(){}}});
 Object.defineProperty(w,'scrollY',{get:()=>0});w.scrollTo=()=>{};
 m.getBoundingClientRect=()=>({top:200,height:10000});
 const image=m.querySelector('figure img');assert(image,'source fixture has a figure image');
 const originalSrc=image.getAttribute('src'),originalAlt=image.getAttribute('alt');
 Object.defineProperties(image,{
  naturalWidth:{get:()=>originalSize[0]},
  naturalHeight:{get:()=>originalSize[1]},
  complete:{get:()=>!delayedSize}
 });
 const replacementHref='2014-01.assets/color-redraw-test.svg';
 const outsider=d.createElement('img');outsider.src=originalSrc;m.append(outsider);
 const nearFigure=d.createElement('figure'),nearImage=d.createElement('img');
 nearImage.src=`${originalSrc}?different=1`;nearFigure.append(nearImage);m.append(nearFigure);
 const pictureFigure=d.createElement('figure'),picture=d.createElement('picture'),pictureImage=d.createElement('img');
 pictureImage.src=originalSrc;picture.append(pictureImage);pictureFigure.append(picture);m.append(pictureFigure);
 const glyphFigure=d.createElement('figure'),glyph=d.createElement('img');
 glyph.className='inline-glyph';glyph.src=originalSrc;glyphFigure.append(glyph);m.append(glyphFigure);
 Object.defineProperties(glyph,{naturalWidth:{value:90},naturalHeight:{value:80},complete:{value:true}});
 Object.defineProperties(nearImage,{naturalWidth:{value:300},naturalHeight:{value:100},complete:{value:true}});
 const config=d.getElementById('exam-reader-config');
 const payload=JSON.parse(config.textContent);
 payload.mode=mode;payload.imageRedraws=[{id:'redraw-test',originalHref:originalSrc,replacementHref,alt:'彩色图表说明'}];
 config.textContent=JSON.stringify(payload);
 w.eval(script);
 if(mode==='svg') {
  assert.equal(m.querySelectorAll('.reader-redraw-control').length,0,'SVG reader keeps original images');
  assert.equal(image.getAttribute('src'),originalSrc);
  assert(!image.classList.contains('reader-figure-image'),'SVG page image sizing untouched');
 } else {
  const redraw=image.nextElementSibling,control=redraw.nextElementSibling;
  if(delayedSize){
   assert(!image.parentElement.classList.contains('reader-sized-figure'),'waits for source dimensions');
   image.dispatchEvent(new w.Event('load'));
  }
  assert.equal(image.parentElement.style.getPropertyValue('--reader-figure-width'),expectedWidth,'width derives from original image');
  assert(image.parentElement.classList.contains('reader-sized-figure'));
  assert(image.classList.contains('reader-figure-image'));
  assert(redraw.classList.contains('reader-figure-image'),'redraw shares source sizing rule');
  assert.equal(nearFigure.style.getPropertyValue('--reader-figure-width'),'450px','unmapped figure is normalized');
  assert(!glyph.classList.contains('reader-figure-image'),'fallback glyph stays untouched');
  assert(!glyphFigure.classList.contains('reader-sized-figure'));
  assert.equal(glyphFigure.querySelectorAll('.reader-redraw-control').length,0,'fallback glyph is never replaced');
  assert(redraw.classList.contains('reader-redraw-image'));
  assert(control.classList.contains('reader-redraw-control'));
  assert.equal(control.dataset.redrawId,'redraw-test');
  assert.equal(image.getAttribute('src'),originalSrc,'original image node retained');
  assert.equal(redraw.src,new URL(replacementHref,url).href);
  assert.equal(redraw.alt,'彩色图表说明');
  assert.equal(control.textContent,'重绘图加载中查看原图');
  assert.equal(outsider.src,new URL(originalSrc,url).href,'non-figure image left alone');
  assert.equal(nearImage.src,new URL(`${originalSrc}?different=1`,url).href,'URL must match exactly');
  assert.equal(pictureImage.nextElementSibling,null,'picture source remains untouched');
  const toggle=control.querySelector('button');
  toggle.click();assert.equal(image.hidden,false);
  redraw.dispatchEvent(new w.Event('load'));
  assert.equal(image.hidden,false,'late load cannot undo user switch');
  assert.equal(control.textContent,'原图查看重绘图');
  toggle.click();assert.equal(image.hidden,true,'loaded redraw shown by default when selected');
  assert.equal(redraw.hidden,false);assert.equal(control.textContent,'重绘图查看原图');
  assert.equal(image.getAttribute('alt'),originalAlt);
  redraw.dispatchEvent(new w.Event('error'));
  assert.equal(image.hidden,false,'failed redraw falls back to original');
  assert.equal(image.getAttribute('src'),originalSrc);
  assert.equal(image.getAttribute('alt'),originalAlt);
  assert.equal(redraw.hidden,true);
  assert(toggle.hidden,'failed redraw cannot be retried indefinitely');
  assert(control.textContent.includes('加载失败'));
  redraw.dispatchEvent(new w.Event('load'));assert.equal(image.hidden,false,'late load cannot revive failed redraw');
  w.eval(script);assert.equal(m.querySelectorAll('.reader-redraw-control').length,1,'redraw enhancement idempotent');
  assert.equal(image.parentElement.style.getPropertyValue('--reader-figure-width'),expectedWidth,'repeat enhancement retains original width basis');
 }
 if(embedded)assert.equal(d.querySelectorAll('.reader-toolbar').length,0,'embedded redraw has no toolbar');
 dom.window.close();
}
(async()=>{
 assert.match(readerCss,/figure\.reader-sized-figure\s*>\s*img\.reader-figure-image/,'sized figure rule applies to both images');
 assert.match(readerCss,/object-fit:\s*contain/,'figure scaling does not crop content');
 for(const [file,mode] of files)console.log('PASS',await fixture(file,mode));
 console.log('PASS centered cartoon reply',await fixture('english-exams-reflow-latex/cet6/papers/2015-12-02.htm','reflow'));
 console.log('PASS denied storage',await fixture(files[0][0],'reflow',{denied:true}));
 console.log('PASS explicit resume',await fixture(files[0][0],'reflow',{resume:true,previous:true}));
 console.log('PASS no implicit resume',await fixture(files[0][0],'reflow',{previous:true}));
 console.log('PASS reject unsafe URL',await fixture(files[0][0],'reflow',{badUrl:true}));
 console.log('PASS compare from reflow',await fixture(files[0][0],'reflow',{compare:true}));
 console.log('PASS compare from SVG',await fixture(files[4][0],'svg',{compare:true}));
 console.log('PASS compare without storage',await fixture(files[0][0],'reflow',{compare:true,denied:true}));
 console.log('PASS embedded reflow no recursion',await fixture(files[0][0],'reflow',{embedded:true}));
 console.log('PASS embedded SVG no recursion',await fixture(files[4][0],'svg',{embedded:true}));
 redrawFixture();console.log('PASS redraw switching and error fallback');
 redrawFixture({embedded:true});console.log('PASS embedded redraw');
 redrawFixture({mode:'svg'});console.log('PASS SVG original unaffected');
 redrawFixture({originalSize:[900,400],expectedWidth:'600px'});console.log('PASS wide figure cap');
 redrawFixture({originalSize:[78,80],expectedWidth:'280px'});console.log('PASS small SVG diagram legibility');
 redrawFixture({originalSize:[90,400],expectedWidth:'126px',delayedSize:true});console.log('PASS tall figure cap and delayed source load');
})().catch(error=>{console.error(error);process.exitCode=1});
