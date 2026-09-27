"""Convert the user-provided mathematics PDF into a portable local HTM archive."""
# Shared reader shell: inject before this generator computes the HTML digest.
import sys as _reader_sys
from pathlib import Path as _ReaderPath
_reader_ui = next(p / 'exam-library' for p in _ReaderPath(__file__).resolve().parents if (p / 'exam-library/enhance_readers.py').is_file())
if str(_reader_ui) not in _reader_sys.path: _reader_sys.path.insert(0, str(_reader_ui))
from enhance_readers import write_reader
import base64
import hashlib
import html
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path
import fitz
from lxml import html as lh

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'layout-tools'))
from archive_renderer import render_page,STYLE,digest,safe_text
from catalog_design import CSS,card
from other_ad_cleaner import clean_document

SOURCE=Path('/Users/apple/Downloads/a/考研数学真题 数学三 2009-2021【公众号-世纪高教在线】/2019-2009年考研数学三真题及答案.pdf')

def main():
    source_hash=digest(SOURCE.read_bytes())
    entries=[];coverage=[];samples=[]
    evidence=ROOT/'assets/verification';evidence.mkdir(parents=True,exist_ok=True)
    with fitz.open(SOURCE) as doc:
        removed=clean_document(doc,'math3-2009-2019')
        toc=doc.get_toc();assert len(doc)==55 and len(toc)==22
        for i,(_,label,start) in enumerate(toc):
            year=int(re.search(r'20\d{2}',label).group())
            kind='answers' if '答案' in label else 'questions'
            end=toc[i+1][2]-1 if i+1<len(toc) else len(doc)
            assert end-start+1==(1 if kind=='answers' else 4)
            title=f'{year} 年考研数学三 · '+('参考答案' if kind=='answers' else '真题')
            f=ROOT/'papers'/f'{year}-{kind}.htm';f.parent.mkdir(exist_ok=True)
            sections=[];metadata=[]
            for n,source_number in enumerate(range(start,end+1),1):
                page=doc[source_number-1]
                markup,meta=render_page(page,n,f.with_suffix('.assets')/f'page-{n:03}.svg')
                # Math OCR is visibly inaccurate even when the original glyphs
                # render perfectly. Do not imply copied formulas are reliable.
                markup=markup.replace('查看 / 复制本页文字','文字识别参考（公式可能有误）')
                sections.append(f'<section class="page-wrap" data-page="{n}" data-source-page="{source_number}"><div class="page-label">第 {n} / {end-start+1} 页</div><div class="sheet">{markup}</div></section>')
                meta['source_page']=source_number;metadata.append(meta);coverage.append(source_number)
                if source_number in (1,5,26,30,51,55):
                    svg=f.with_suffix('.assets')/f'page-{n:03}.svg'
                    source=page.get_pixmap(dpi=120,alpha=False)
                    source.save(evidence/f'source-{source_number}.png')
                    target=evidence/f'htm-page-{source_number}.png'
                    subprocess.run(['rsvg-convert','-w',str(source.width),'-h',str(source.height),'-b','white','-o',str(target),str(svg)],check=True)
                    rendered=fitz.Pixmap(str(target))
                    if rendered.alpha:rendered=fitz.Pixmap(rendered,0)
                    assert rendered.width==source.width and rendered.height==source.height
                    a,b=source.samples,rendered.samples
                    error=sum(abs(x-y) for x,y in zip(a,b,strict=True))/len(a)
                    samples.append({'source_page':source_number,'mean_absolute_channel_difference':round(error,4)})
            other='questions' if kind=='answers' else 'answers'
            next_label='返回真题' if kind=='answers' else '查看参考答案'
            body='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>'+STYLE+'</style></head><body><header><a href="../index.htm">← 全部年份</a><h1>'+title+'</h1><p>原卷排版 · 公式与图形按原样显示 · 可离线阅读</p><p><a href="'+f'{year}-{other}.htm'+'">'+next_label+'</a></p><p>数学公式请以试卷画面为准；下方文字识别结果可能有错字或公式错误。</p></header><main id="exam-pages">'+''.join(sections)+'</main><footer>原始 PDF 第 '+str(start)+'–'+str(end)+' 页 · 请保留同名 .assets 素材文件夹</footer></body></html>'
            write_reader(f, body)
            entries.append({'year':year,'kind':kind,'title':title,'file':str(f.relative_to(ROOT)),'pages':end-start+1,'source_pages':[start,end],'htm_sha256':digest(f.read_bytes()),'page_rendering':metadata})
            print('CONVERTED',title,start,end,flush=True)
        assert coverage==list(range(1,56))
        assert sorted({e['year'] for e in entries})==list(range(2009,2020))
        for e in entries:
            f=ROOT/e['file'];d=lh.fromstring(f.read_text(),parser=lh.HTMLParser(huge_tree=True))
            sections=d.xpath('//section[@data-source-page]');assert len(sections)==e['pages']
            for section,meta in zip(sections,e['page_rendering'],strict=True):
                page=doc[int(section.get('data-source-page'))-1]
                assert ''.join(section.xpath('.//pre[@class="source-text"]')[0].itertext())==safe_text(page.get_text())
                svg=f.with_suffix('.assets')/f'page-{meta["page"]:03}.svg'
                assert digest(svg.read_bytes())==meta['svg_sha256']
                assert svg.read_bytes()==page.get_svg_image(text_as_path=True).encode()
    header='<header><h1>历年考研数学三真题</h1><p>2009–2019 年 · 11 年真题及参考答案 · 共 55 页</p><details class="jump"><summary>按年份跳转</summary><nav class="years">'+''.join(f'<a href="#year-{year}">{year}</a>' for year in range(2019,2008,-1))+'</nav></details></header>'
    sections=''
    for year in range(2019,2008,-1):
        group=sorted((e for e in entries if e['year']==year),key=lambda e:e['kind']=='answers')
        sections+=f'<section class="year" id="year-{year}"><h2>{year}年</h2><div class="grid">'+''.join(card(e,e['file']) for e in group)+'</div></section>'
    (ROOT/'index.htm').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>2009–2019 考研数学三真题</title><style>'+CSS+'</style></head><body>'+header+'<main>'+sections+'</main><footer>本地试卷 · 点击封面打开真题或参考答案</footer></body></html>')
    for f in [ROOT/'index.htm']+[ROOT/e['file'] for e in entries]:
        d=lh.fromstring(f.read_text(),parser=lh.HTMLParser(huge_tree=True))
        for link in d.xpath('//a/@href|//img/@src'):
            if link.startswith('#'):
                assert d.xpath('//*[@id=$value]',value=link[1:])
            else:assert (f.parent/link).is_file(),(f,link)
    assert digest(SOURCE.read_bytes())==source_hash
    manifest={'removed_adverts':removed,'source_name':SOURCE.name,'source_sha256':source_hash,'source_unmodified':True,'years':11,'documents':22,'pages':55,'papers':entries}
    (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    report={'all_55_source_pages_covered_once':True,'bookmarks_preserved_as_22_documents':True,'all_svg_bytes_match_cleaned_source_rendering':True,'copy_text_matches_source':True,'all_local_links_valid':True,'rendered_samples':samples,'removed_advert_regions':sum(len(x['rectangles']) for x in removed),'browser_interaction_tested':False,'math_ocr_reliability':'Not reliable; formulas must be read from the original glyph rendering.'}
    (ROOT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'README.md').write_text('# 考研数学三真题与参考答案（2009–2019）\n\n打开 index.htm，从年份封面目录进入真题或参考答案。每年真题 4 页、答案 1 页，共 55 页。\n\n请保留 papers/ 内每个 HTM 同名的 .assets 素材文件夹。公式、表格、图形用原字形与坐标显示，无需 PDF 阅读器；没有重新识别或改写公式。源 PDF 保持原样。\n\n复制文字只作识别参考，源文本层已有错字和公式识别错误，不能用作可靠的数学公式。\n\n来源书签、原始页码及哈希在 manifest.json；文件/素材/链接核验以及 6 页本地渲染对照记录在 verification.json。浏览器交互未完成本轮实测。\n')
    files=[ROOT/'index.htm',ROOT/'README.md',ROOT/'manifest.json',ROOT/'verification.json']+list((ROOT/'papers').rglob('*'))
    files=[f for f in files if f.is_file()]
    archive=ROOT.parent/'考研数学三_2009-2019_真题及答案_HTM.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in files:z.write(f,str(Path(ROOT.name)/f.relative_to(ROOT)))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist())==81
    print('DONE',len(entries),'documents; 55 pages;',archive.stat().st_size,'zip bytes',flush=True)

if __name__=='__main__':main()
