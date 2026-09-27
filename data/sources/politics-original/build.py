"""Archive politics PDFs with identified promotions removed from reading copies."""
# Shared reader shell: inject before this generator computes the HTML digest.
import sys as _reader_sys
from pathlib import Path as _ReaderPath
_reader_ui = next(p / 'exam-library' for p in _ReaderPath(__file__).resolve().parents if (p / 'exam-library/enhance_readers.py').is_file())
if str(_reader_ui) not in _reader_sys.path: _reader_sys.path.insert(0, str(_reader_ui))
from enhance_readers import write_reader
from pathlib import Path
import sys,json,hashlib,html
import fitz
from lxml import html as lh
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'layout-tools'))
from archive_renderer import render_page,STYLE
from catalog_design import CSS,card
from clean_source import cleaned_document,omitted_pages
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 specs=json.loads((ROOT/'sources.json').read_text());entries=[];total=0
 for spec in specs:
  path=Path(spec['path']);assert sha(path)==spec['sha256'];pdf,removals=cleaned_document(path);assert len(pdf)==spec['pages']
  target=ROOT/'papers'/f"{spec['id']}.htm";target.parent.mkdir(exist_ok=True);parts=[];pages=[];omitted=omitted_pages(path);shown=0
  for i,page in enumerate(pdf,1):
   if i in omitted:
    stale=target.with_suffix(".assets")/f"page-{i:03}.svg"
    if stale.exists():stale.unlink()
    continue
   shown+=1
   asset=target.with_suffix('.assets')/f'page-{i:03}.svg';markup,meta=render_page(page,i,asset)
   assert asset.read_bytes()==page.get_svg_image(text_as_path=True).encode()
   parts.append(f'<section class="page-wrap"><div class="page-label">第 {shown} / {len(pdf)-len(omitted)} 页</div><div class="sheet">{markup}</div></section>')
   pages.append({'page':i,'sha256':sha(asset)});total+=1
  title=html.escape(spec['title'])
  write_reader(target, '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>'+STYLE+'</style></head><body><header><a href="../../exam-library/politics/index.htm">← 政治双版本目录</a><h1>'+title+'</h1><p>原卷排版 · 已去除推广内容 · 全文离线阅读</p></header><main>'+''.join(parts)+'</main><footer>用户提供的 PDF 阅读版；已移除推广页、引流页眉与推广二维码，正文与图表保留。</footer></body></html>')
  entries.append({**spec,'displayed_pages':shown,'omitted_advert_pages':omitted,'advert_removals':removals,'file':str(target.relative_to(ROOT)),'page_rendering':pages,'htm_sha256':sha(target)})
  print('ORIGINAL',spec['id'],len(pdf),flush=True)
 years=sorted({e['year'] for e in entries},reverse=True)
 body=''.join(f'<section class="year" id="year-{y}"><h2>{y}年</h2><div class="grid">'+''.join(card({**e,'pages':e['displayed_pages']},e['file']) for e in entries if e['year']==y)+'</div></section>' for y in years)
 jump='<details class="jump"><summary>按年份跳转</summary><nav class="years">'+''.join(f'<a href="#year-{y}">{y}</a>' for y in years)+'</nav></details>'
 (ROOT/'index.htm').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>考研政治真题</title><style>'+CSS+'</style></head><body><header><a href="../exam-library/index.htm">← 考研真题大全</a><h1>考研政治</h1><p>'+f'{min(years)}–{max(years)} · {len(years)} 年真题与参考解析'+'</p>'+jump+'</header><main>'+body+'</main><footer>保留原卷正文与版面；已去除推广内容。</footer></body></html>')
 (ROOT/'manifest.json').write_text(json.dumps({'documents':entries,'source_pages':sum(e['pages'] for e in entries),'displayed_pages':total,'omitted_advert_pages':sum(len(e['omitted_advert_pages']) for e in entries)},ensure_ascii=False,indent=2))
 print('TOTAL',total)
if __name__=='__main__':main()
