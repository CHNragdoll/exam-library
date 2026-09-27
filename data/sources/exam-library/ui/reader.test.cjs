/* node reader.test.cjs; jsdom is a temporary test-only dependency, never shipped. */
const {JSDOM} = require(process.env.EXAM_JSDOM || 'jsdom');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const base = path.resolve(__dirname, '../..');
const script = fs.readFileSync(path.join(__dirname, 'reader.js'), 'utf8');
const readerCss = fs.readFileSync(path.join(__dirname, 'reader.css'), 'utf8');
const englishCss = fs.readFileSync(path.join(base, 'english-exams-reflow-latex/style.css'), 'utf8');
const files = [
 ['english-exams-reflow-latex/kaoyan/papers/2014-01.htm','reflow'],
 ['english-exams-reflow-latex/cet6/papers/2015-12-01.htm','reflow'],
 ['english-exams-reflow-latex/cet6/papers/2015-12-02.htm','reflow'],
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
 const generatedConfig=JSON.parse(d.getElementById('exam-reader-config')?.textContent||'{}');
 const map = new Map();
 if(previous)map.set('exam-library:recent:v1',JSON.stringify([{url,progress:.5,scrollY:4000,updatedAt:Date.now()}]));
 Object.defineProperty(w,'localStorage',{value:{getItem(k){if(denied)throw Error('denied');return map.get(k)||null},setItem(k,v){if(denied)throw Error('denied');map.set(k,v)}}});
 let scroll=0;Object.defineProperty(w,'scrollY',{get:()=>scroll});w.scrollTo=o=>{scroll=o.top;w.dispatchEvent(new w.Event('scroll'))};
 m.getBoundingClientRect=()=>({top:200-scroll,height:10000});
 d.querySelectorAll('#exam-reader-config').forEach(n=>n.remove());
 const c=d.createElement('script');c.id='exam-reader-config';c.type='application/json';
 const structuredToc=relative.includes('cet6/papers/2015-12-02.htm')
  ? JSON.parse(fs.readFileSync(path.join(base,'exam-library/structured/papers/cet6/2015-12-02.json'),'utf8')).toc.map(entry=>{
    const [,pageIndex,blockIndex]=/^b-(\d+)-(\d+)$/.exec(entry.sourceBlockId);
    return {label:entry.label,level:entry.level,pageIndex:Number(pageIndex),blockIndex:Number(blockIndex)};
   }) : undefined;
 const translationParagraphStarts=relative.includes('cet6/papers/2015-12-02.htm')
  ? ['最近，中国政府决定将其工','中国造产品越来越受欢迎。'] : undefined;
 c.textContent=JSON.stringify({title:'试卷测试',category:relative.includes('/cet6/')?'cet6':'kaoyan',documentId:relative.includes('2015-12-02.htm')?'cet6:2015-12-02':'test',categoryLabel:'考研英语',mode,libraryHref:'../../exam-library/index.htm',categoryHref:'../index.htm',alternateHref:badUrl?'javascript:alert(1)':'other.htm',structuredToc,translationParagraphStarts,readingParagraphStarts:generatedConfig.readingParagraphStarts});
 d.body.append(c);
 const sourcePageNodes=[...m.querySelectorAll(':scope > section[data-source-page]')];
 const tocSourceTargets=structuredToc && new Map(structuredToc.map(entry=>
  [entry.label,sourcePageNodes[entry.pageIndex-1]?.children[entry.blockIndex-1]]));
 const textBefore=m.textContent, formula=d.querySelector('[data-toggle-source]'), svgCount=m.querySelectorAll('svg').length, imageCount=m.querySelectorAll('img').length;
 w.eval(script);w.dispatchEvent(new w.Event('load'));await wait(20);
 // Source-confirmed continuations restore spaces that PDF extraction dropped
 // at block boundaries; compare every non-whitespace character instead.
 assert.equal(m.textContent.replace(/\s+/g,''),textBefore.replace(/\s+/g,''),'exam wording unchanged');assert.equal(m.querySelectorAll('svg').length,svgCount,'formulas unchanged');assert.equal(m.querySelectorAll('img').length,imageCount,'figures unchanged');
 if(relative.includes('cet6/papers/2015-12-01.htm')) {
  const note=m.querySelector('.reader-answer-sheet-note');
  assert(note && note.textContent.includes('答题卡1'),'answer-sheet note starts its own paragraph');
  assert(!note.previousElementSibling.textContent.includes('注意：'),'note no longer trails directions');
  const first=[...m.querySelectorAll('.reader-listening-question')].find(row=>row.querySelector('.question')?.textContent.trim()==='1.');
  assert(first && first.querySelector('ul.options'),'bare listening number shares a row with A/B options');
 }
 if(relative.includes('cet6/papers/2015-12-02.htm')) {
  const originalStarts=['But if it was known','The study’s most striking',
   'In one of the study’s experiments','The “African-American” group','Hall’s findings'];
  const sourceParagraphs=[...m.querySelectorAll('section[data-source-page="7"] > p.paragraph')];
  for(const start of originalStarts)assert(sourceParagraphs.some(p=>p.textContent.trim().startsWith(start)),
   `source SVG paragraph starts at ${start}`);
  assert.equal(sourceParagraphs.filter(p=>p.classList.contains('reader-source-paragraph')).length,5,
   'Passage One has exactly five source paragraphs before Passage Two starts');
  assert(!sourceParagraphs.some(p=>p.textContent.includes('A) In the long view')),
   'lettered matching-passage option stays outside the reading paragraphs');
  const translation=[...m.querySelectorAll('.reader-translation-body')];
  assert.equal(translation.length,2,'the two original translation paragraphs are separate');
  assert(translation[0].textContent.trim().startsWith('最近，中国政府'));
  assert(translation[1].textContent.trim().startsWith('中国造产品'));
  assert(m.querySelector('.reader-translation-directions').textContent.trim().endsWith('Answer Sheet 2.'));
  const lettered=[...m.querySelectorAll('.reader-lettered-paragraph')];
  assert(lettered.some(p=>p.querySelector('.reader-lettered-label')?.textContent==='J)'));
  assert(lettered.some(p=>p.querySelector('.reader-lettered-label')?.textContent==='K)'));
  const passageI=lettered.find(p=>p.querySelector('.reader-lettered-label')?.textContent==='I)');
  assert(passageI?.textContent.includes('because the engineers, designers'),
   'source page break inside matching paragraph I stays joined');
  const caption=m.querySelector('p.reader-cartoon-followup');
  assert(caption && caption.textContent.includes('We just don’t have much useful information.'),'cartoon reply is centered below figure');
  assert(!caption.textContent.includes('注意：'),'answer-sheet note stays separate from caption');
  const readingNote=[...m.querySelectorAll('.reader-answer-sheet-note')]
   .find(note=>note.textContent.includes('答题卡2'));
  assert(readingNote && readingNote.previousElementSibling.textContent.trim().endsWith('can’t hurt.'),
   'underlined answer-sheet note starts a new line after reading prose');
  assert(readingNote.querySelector('u'),'original note emphasis is preserved');
  assert.match(readerCss,/p\.reader-cartoon-followup\{text-align:center;text-align-last:center\}/);
  for (const number of ['6.', '8.', '16.']) {
   const row=[...m.querySelectorAll('.reader-listening-question')]
    .find(item=>item.querySelector('.question')?.textContent.trim()===number);
   assert(row,`question ${number} is kept with its choices`);
   assert.deepEqual([...row.querySelectorAll('.option-label')].map(label=>label.textContent.trim()),
    ['A.','B.','C.','D.'],`question ${number} has A/B and C/D in order`);
  }
 }
 assert.equal(d.querySelector('[data-toggle-source]'),formula,'original formula control retained');
 if(embedded) {
  assert(d.body.classList.contains('reader-embed'));assert.equal(d.querySelectorAll('.reader-toolbar').length,0);assert.equal(d.querySelectorAll('iframe').length,0);
  w.dispatchEvent(new w.Event('pagehide'));assert(!map.has('exam-library:recent:v1'),'embedded document never writes recent state');dom.window.close();return relative;
 }
 assert.equal(d.querySelectorAll('.reader-toolbar').length,1);w.eval(script);assert.equal(d.querySelectorAll('.reader-toolbar').length,1,'idempotent enhancement');
 assert(d.querySelector('.reader-toc').options.length>0);
 if(relative.includes('cet6/papers/2015-12-02.htm')) {
  const select=d.querySelector('.reader-toc');
  for(const [label,expected] of [['Part Ⅱ Listening Comprehension (30 minutes)','PartⅡ Listening Comprehension'],['Section A','Section A'],['第 2 题','2.'],['第 9 题','9.']]) {
   const index=[...select.options].findIndex(option=>option.textContent.trim()===label);
   assert(index>=0,`${label} appears in the structured TOC`);
   select.value=String(index);select.dispatchEvent(new w.Event('change'));
   assert(d.activeElement.textContent.includes(expected),`${label} focuses its matching source block`);
  }
  const sourcePages=[...m.querySelectorAll(':scope > section[data-source-page]')];
  assert.equal(sourcePages.length,9,'only top-level sections are PDF pages');
  assert(m.querySelector('span[data-source-page]'),'source has inline spans carrying page metadata');
  for(const label of ['Part Ⅲ Reading Comprehension (40 minutes)','第 46 题','第 51 题']) {
   const expected=tocSourceTargets.get(label);
   const index=[...select.options].findIndex(option=>option.textContent.trim()===label);
   assert(index>=0 && expected,`${label} has a source block`);
   select.value=String(index);select.dispatchEvent(new w.Event('change'));
   assert.equal(d.activeElement,expected,`${label} jumps past inline spans to its exact block`);
  }
  assert([...select.options].find(o=>o.textContent.trim()==='Section A').textContent.startsWith('　'));
  assert([...select.options].find(o=>o.textContent.trim()==='第 2 题').textContent.startsWith('　　'));
 }
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
function choiceLayoutFixture() {
 const file=path.join(base,'english-exams-reflow-latex/cet6/papers/2015-12-02.htm');
 const dom=new JSDOM(fs.readFileSync(file,'utf8'));
 const w=dom.window,d=w.document,style=d.createElement('style');
 style.textContent=englishCss;d.head.append(style);
 const row=[...d.querySelectorAll('.choice-row')].find(node=>node.textContent.includes('Touch his heart.'));
 assert(row && row.children.length===5,'question 9 has number and A-D');
 assert.equal(row.children[4].textContent.trim().startsWith('D.'),true,'D option remains complete');
 assert.equal(w.getComputedStyle(row.parentElement).overflowX,'visible','no horizontal scrolling');
 assert.equal(w.getComputedStyle(row).minWidth,'0px','choice row fits content width');
 assert.match(w.getComputedStyle(row).gridTemplateColumns,/repeat\(2,minmax\(0,1fr\)\)/,'two option columns');
 assert.equal(w.getComputedStyle(row.children[1]).gridRow,'1');
 assert.equal(w.getComputedStyle(row.children[2]).gridRow,'1');
 assert.equal(w.getComputedStyle(row.children[3]).gridRow,'2');
 assert.equal(w.getComputedStyle(row.children[4]).gridRow,'2');
 assert.equal(w.getComputedStyle(row.children[4]).whiteSpace,'normal','long options wrap');
 dom.window.close();
}
function tocHierarchyFixture() {
 const relative='english-exams-reflow-latex/kaoyan/papers/2026-01.htm';
 const file=path.join(base,relative);
 const dom=new JSDOM(fs.readFileSync(file,'utf8'),{url:new URL(`file://${file}`).href,runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window,d=w.document,m=d.querySelector('main');
 const data=JSON.parse(fs.readFileSync(path.join(base,'exam-library/structured/papers/kaoyan/2026-01.json'),'utf8'));
 const structuredToc=data.toc.map(entry=>{
  const match=/^b-(\d+)-(\d+)$/.exec(entry.sourceBlockId);
  assert(match,`valid source block ID: ${entry.sourceBlockId}`);
  return {label:entry.label,level:entry.level,pageIndex:Number(match[1]),blockIndex:Number(match[2])};
 });
 const config=d.getElementById('exam-reader-config');
 const payload=JSON.parse(config.textContent);
 assert.deepEqual(payload.structuredToc,structuredToc,'reader config reflects current structured TOC');
 Object.defineProperty(w,'localStorage',{value:{getItem(){return null},setItem(){}}});
 let scroll=0;Object.defineProperty(w,'scrollY',{get:()=>scroll});w.scrollTo=options=>{scroll=options.top};
 w.eval(script);
 const select=d.querySelector('.reader-toc');
 const options=[...select.options];
 const entries=options.map(option=>option.textContent.trim());
 const section=entries.indexOf('Section II Reading Comprehension');
 const part=entries.indexOf('Part A',section+1);
 const text=entries.indexOf('Text 1',part+1);
 const question=entries.indexOf('第 21 题',text+1);
 assert(section>=0 && section<part && part<text && text<question,
  'reading section, part, text and question appear in source order');
 assert.equal(options[section].textContent,'Section II Reading Comprehension');
 assert(options[part].textContent.startsWith('　'));
 assert(options[text].textContent.startsWith('　　'));
 assert(options[question].textContent.startsWith('　　　'));
 const expected=[
  [section,'Section II Reading Comprehension'],
  [part,'Part A'],
  [text,'Text 1'],
  [question,'21.']
 ];
 for(const [index,content] of expected){
  const entry=structuredToc.find(item=>item.label===entries[index] && (
   item.pageIndex>0));
  assert(entry,`source entry for ${content}`);
  const node=[...m.querySelectorAll(':scope > section[data-source-page]')][entry.pageIndex-1]?.children[entry.blockIndex-1];
  assert(node && node.textContent.includes(content),`${content} maps to its own source block`);
  node.getBoundingClientRect=()=>({top:500});
  d.querySelector('.reader-toolbar').getBoundingClientRect=()=>({height:100});
  scroll=0;select.value=String(index);select.dispatchEvent(new w.Event('change'));
  assert.equal(d.activeElement,node,`TOC jump focuses exact ${content} block`);
  assert.equal(scroll,378,`TOC jump positions ${content} below toolbar`);
 }
 const writing=entries.indexOf('Section III Writing');
 const writingPart=entries.indexOf('Part A',writing+1);
 assert(writing>question && writingPart>writing,'writing Part A is nested under its own section');
 assert(options[writingPart].textContent.startsWith('　'));
 dom.window.close();
}
function compactChoiceFixture() {
 const file=path.join(base,'english-exams-reflow-latex/kaoyan/papers/2026-01.htm');
 const dom=new JSDOM(fs.readFileSync(file,'utf8'),{url:new URL(`file://${file}`).href,runScripts:'outside-only',pretendToBeVisual:true});
 const w=dom.window,d=w.document,m=d.querySelector('main');
 Object.defineProperty(w,'localStorage',{value:{getItem(){return null},setItem(){}}});
 Object.defineProperty(w,'scrollY',{get:()=>0});w.scrollTo=()=>{};
 const original=[...m.querySelectorAll('.choice-row')].map(row=>row.textContent);
 w.eval(script);
 const rows=[...m.querySelectorAll('.choice-row')];
 assert.equal(rows.length,20,'2026 cloze has 20 source choice rows');
 assert(rows.every(row=>row.classList.contains('reader-four-column')),'short 2026 cloze alternatives use a four-column row');
 for(const row of rows){
  assert.deepEqual([...row.querySelectorAll('.choice-item strong')].map(label=>label.textContent.trim()),['A.','B.','C.','D.']);
 }
 assert.deepEqual(rows.map(row=>row.textContent),original,'compact layout preserves source option text');
 assert.match(readerCss,/\.choice-row\.reader-four-column\{grid-template-columns:2\.1em repeat\(4,minmax\(0,1fr\)\)/);
 assert.match(readerCss,/@container \(max-width:740px\)/,'narrow reader uses two-column fallback');
 assert.match(readerCss,/@container \(max-width:420px\)/,'phone reader uses single-column fallback');
 dom.window.close();
 const longFile=path.join(base,'english-exams-reflow-latex/cet6/papers/2015-12-02.htm');
 const longDom=new JSDOM(fs.readFileSync(longFile,'utf8'),{url:new URL(`file://${longFile}`).href,runScripts:'outside-only',pretendToBeVisual:true});
 const longWindow=longDom.window;
 Object.defineProperty(longWindow,'localStorage',{value:{getItem(){return null},setItem(){}}});
 Object.defineProperty(longWindow,'scrollY',{get:()=>0});longWindow.scrollTo=()=>{};
 longWindow.eval(script);
 const longRow=[...longWindow.document.querySelectorAll('.choice-row')]
  .find(row=>row.textContent.includes('Touch his heart.'));
 assert(longRow && !longRow.classList.contains('reader-four-column'),'prose alternatives retain wrapping layout');
 longDom.window.close();
}
(async()=>{
 assert.match(readerCss,/figure\.reader-sized-figure\s*>\s*img\.reader-figure-image/,'sized figure rule applies to both images');
 assert.match(readerCss,/object-fit:\s*contain/,'figure scaling does not crop content');
 for(const [file,mode] of files)console.log('PASS',await fixture(file,mode));
 console.log('PASS centered cartoon reply',await fixture('english-exams-reflow-latex/cet6/papers/2015-12-02.htm','reflow'));
 choiceLayoutFixture();console.log('PASS listening choices wrap without horizontal scrolling');
 compactChoiceFixture();console.log('PASS short cloze choices use four columns');
 tocHierarchyFixture();console.log('PASS structured TOC hierarchy and exact jumps');
 console.log('PASS denied storage',await fixture(files[0][0],'reflow',{denied:true}));
 console.log('PASS explicit resume',await fixture(files[0][0],'reflow',{resume:true,previous:true}));
 console.log('PASS no implicit resume',await fixture(files[0][0],'reflow',{previous:true}));
 console.log('PASS reject unsafe URL',await fixture(files[0][0],'reflow',{badUrl:true}));
 console.log('PASS compare from reflow',await fixture(files[0][0],'reflow',{compare:true}));
	console.log('PASS compare from SVG',await fixture(files[5][0],'svg',{compare:true}));
 console.log('PASS compare without storage',await fixture(files[0][0],'reflow',{compare:true,denied:true}));
 console.log('PASS embedded reflow no recursion',await fixture(files[0][0],'reflow',{embedded:true}));
	console.log('PASS embedded SVG no recursion',await fixture(files[5][0],'svg',{embedded:true}));
 redrawFixture();console.log('PASS redraw switching and error fallback');
 redrawFixture({embedded:true});console.log('PASS embedded redraw');
 redrawFixture({mode:'svg'});console.log('PASS SVG original unaffected');
 redrawFixture({originalSize:[900,400],expectedWidth:'600px'});console.log('PASS wide figure cap');
 redrawFixture({originalSize:[78,80],expectedWidth:'280px'});console.log('PASS small SVG diagram legibility');
 redrawFixture({originalSize:[90,400],expectedWidth:'126px',delayedSize:true});console.log('PASS tall figure cap and delayed source load');
})().catch(error=>{console.error(error);process.exitCode=1});
