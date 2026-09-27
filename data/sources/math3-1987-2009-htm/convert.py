"""Preserve all pages of the supplied 1987–2009 mathematics source as offline SVG."""
# Shared reader shell: inject before this generator computes the HTML digest.
import sys as _reader_sys
from pathlib import Path as _ReaderPath
_reader_ui = next(p / 'exam-library' for p in _ReaderPath(__file__).resolve().parents if (p / 'exam-library/enhance_readers.py').is_file())
if str(_reader_ui) not in _reader_sys.path: _reader_sys.path.insert(0, str(_reader_ui))
from enhance_readers import write_reader
from pathlib import Path
import fitz,json,re,unicodedata,hashlib,html,sys,zipfile
from lxml import html as lh
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'layout-tools'))
from archive_renderer import render_page,STYLE
from catalog_design import CSS,card
SOURCE=Path('/Users/apple/Downloads/a/考研数学真题 数学三 2009-2021【公众号-世纪高教在线】/a/2009-1987年考研数学三真题及答案.pdf')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 doc=fitz.open(SOURCE);toc=doc.get_toc();assert len(doc)==132 and len(toc)==46
 # Page 2 contains only QR-code/course/group promotion, never exam content.
 # Do not retain an obsolete directly openable advert asset after rebuilding.
 (ROOT/'papers/frontmatter.assets/page-002.svg').unlink(missing_ok=True)
 entries=[];covered=[]
 specs=[('frontmatter',None,'封面',1,1)]
 for i,(_,label,start) in enumerate(toc):
  year=int(re.search(r'\d{4}',unicodedata.normalize('NFKC',label))[0]);kind='answers' if '答案' in label else 'questions'
  specs.append((kind,year,f'{year} 年考研数学三 · '+('参考答案' if kind=='answers' else '真题'),start,toc[i+1][2]-1 if i+1<len(toc) else len(doc)))
 for kind,year,title,start,end in specs:
  stem=f'{year}-{kind}' if year else kind;target=ROOT/'papers'/f'{stem}.htm';target.parent.mkdir(exist_ok=True);sections=[];metadata=[]
  for number,sp in enumerate(range(start,end+1),1):
   asset=target.with_suffix('.assets')/f'page-{number:03}.svg';markup,meta=render_page(doc[sp-1],number,asset)
   assert asset.read_bytes()==doc[sp-1].get_svg_image(text_as_path=True).encode()
   markup=markup.replace('查看 / 复制本页文字','文字识别参考（公式以原图为准）')
   sections.append(f'<section class="page-wrap" data-source-page="{sp}"><div class="page-label">第 {number} / {end-start+1} 页</div><div class="sheet">{markup}</div></section>');metadata.append({'source_page':sp,'svg_sha256':sha(asset)});covered.append(sp)
  nav='<a href="../../exam-library/math3/index.htm">← 考研数学三目录</a> · <a href="../index.htm">本册目录</a>'
  if year:nav+=f' · <a href="{year}-'+('answers' if kind=='questions' else 'questions')+'.htm">'+('参考答案' if kind=='questions' else '真题')+'</a>'
  write_reader(target, '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>'+STYLE+'</style></head><body><header>'+nav+'<h1>'+title+'</h1><p>原卷矢量版 · 公式与图形按原样显示 · 1987–1996 年保留试卷 IV、V 区分</p></header><main>'+''.join(sections)+'</main><footer>用户提供的原 PDF 第 '+str(start)+'–'+str(end)+' 页；可复制的文字层含公式识别错误，请以图形为准。</footer></body></html>')
  entries.append({'year':year,'kind':kind,'title':title,'file':str(target.relative_to(ROOT)),'pages':end-start+1,'source_pages':list(range(start,end+1)),'page_rendering':metadata,'htm_sha256':sha(target)})
  print('CONVERTED',stem,end-start+1,flush=True)
 assert sorted(covered)==[n for n in range(1,133) if n!=2]
 body=''
 for y in range(2009,1986,-1):
  group=sorted((e for e in entries if e['year']==y),key=lambda e:e['kind']=='answers')
  body+=f'<section class="year" id="year-{y}"><h2>{y}年</h2><div class="grid">'+''.join(card(e,e['file']) for e in group)+'</div></section>'
 jump='<details class="jump"><summary>按年份跳转</summary><nav class="years">'+''.join(f'<a href="#year-{y}">{y}</a>' for y in range(2009,1986,-1))+'</nav></details>'
 (ROOT/'index.htm').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>1987–2009 考研数学三</title><style>'+CSS+'</style></head><body><header><a href="../exam-library/math3/index.htm">← 考研数学三全部年份</a><h1>1987–2009 考研数学三</h1><p>23 年真题及参考答案 · 保留早年 IV、V 卷 · <a href="papers/frontmatter.htm">封面</a></p>'+jump+'</header><main>'+body+'</main><footer>原版归档；2009 年与已有资料重复，统一目录使用既有双版本。</footer></body></html>')
 (ROOT/'manifest.json').write_text(json.dumps({'source_path':str(SOURCE),'source_sha256':sha(SOURCE),'years':23,'documents':46,'pages':131,'source_pages':132,'removed_advert_pages':[2],'papers':[e for e in entries if e['year']],'supplements':[e for e in entries if not e['year']]},ensure_ascii=False,indent=2))
 checks=0
 for p in ROOT.rglob('*.htm'):
  t=lh.fromstring(p.read_text(),parser=lh.HTMLParser(huge_tree=True))
  for u in t.xpath('//a/@href|//img/@src'):
   if u.startswith('#'):assert t.xpath('//*[@id=$id]',id=u[1:])
   elif not u.startswith('data:'):assert (p.parent/u).is_file(),(p,u)
   checks+=1
 (ROOT/'verification.json').write_text(json.dumps({'pages':len(covered),'all_non_advert_pages_covered_once':True,'removed_advert_pages':[2],'raw_source_pages':132,'svg_matches_source':True,'local_links_checked':checks,'browser_tested':False},indent=2))
 (ROOT/'README.md').write_text('# 1987–2009 数学三原版归档\n\n统一入口为 ../exam-library/index.htm。23 年题目和答案分开，1987–1996 年 IV/V 卷保留同年原顺序，封面与说明另存。已移除第 2 页纯推广页；其余 131 页逐页 SVG 与原PDF字形导出相同，原 PDF 未修改。2009 年仍保留本册归档；统一入口去重显示既有版本。\n')
 print('VERIFIED',len(covered),'source pages',checks,'links')
if __name__=='__main__':main()
