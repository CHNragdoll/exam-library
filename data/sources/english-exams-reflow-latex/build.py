"""Build 206 offline, text-reflowing English papers and matching LaTeX."""
# Shared reader shell: inject before this generator computes the HTML digest.
import sys as _reader_sys
from pathlib import Path as _ReaderPath
_reader_ui = next(p / 'exam-library' for p in _ReaderPath(__file__).resolve().parents if (p / 'exam-library/enhance_readers.py').is_file())
if str(_reader_ui) not in _reader_sys.path: _reader_sys.path.insert(0, str(_reader_ui))
from enhance_readers import write_reader
from pathlib import Path
import sys,json,re,html,hashlib,subprocess,zipfile,statistics,unicodedata
import fitz
from concurrent.futures import ProcessPoolExecutor
from lxml import html as lh
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT.parent/'layout-tools'))
from extract import extract,markup,plain,SITE
from repair_archive import source_pdf
from encoding import get_unknown_glyphs
from layout import prepare,copy_flowchart,continues_paragraph

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def e(s):return html.escape(str(s),quote=True)
def textext(s):
    mapping={'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}','→':r'\(\rightarrow\)','←':r'\(\leftarrow\)','√':r'\(\sqrt{}\)','∞':r'\(\infty\)','≤':r'\(\leq\)','≥':r'\(\geq\)','·':r'\textperiodcentered{}','­':'-'}
    mapping.update({'‒':r'\textendash{}','А':r'{\fontspec{FandolSong-Regular.otf}А}','а':r'{\fontspec{FandolSong-Regular.otf}а}','′':r'\(\prime\)','″':r'\(\prime\prime\)','₂':r'\textsubscript{2}','―':r'\textemdash{}','℉':r'\(^{\circ}\mathrm{F}\)','■':r'\(\blacksquare\)','□':r'\(\square\)','♦':r'\(\blacklozenge\)'})
    mapping.update({chr(0x2460+i):r'\textcircled{'+str(i+1)+'}' for i in range(20)})
    return ''.join(mapping.get(c,unicodedata.normalize('NFKC',c) if 0x2160<=ord(c)<=0x217f else c) for c in s)
def texruns(runs):
    result=[]
    for r in runs:
        if r.get('glyph'):
            result.append(r'\raisebox{'+str(round(r.get('glyph_baseline',-.12),3))+r'em}{\includegraphics[height='+str(round(r.get('glyph_height',1),3))+r'em]{'+r['glyph'].replace('.svg','.png')+r'}}\allowbreak{}');continue
        text=''.join(r'\par\noindent\rule{.95\linewidth}{.4pt}\par ' if re.fullmatch(r'_{15,}',part) else textext(part) for part in re.split(r'(_{15,})',r['text']));b,u,i=r['flags']
        if r'\par' in text:b=u=i=False
        if u:text=(r'\CJKunderline{' if re.search(r'[\u3400-\u9fff]',r['text']) else r'\uline{')+text+'}'
        if i:text=r'\textit{'+text+'}'
        if b:text=r'\textbf{'+text+'}'
        result.append(text)
    return ''.join(result)
def htmlruns(runs):
    out=[]
    for r in runs:
        if r.get('glyph'):out.append(f'<img class="inline-glyph" src="{e(r["glyph"])}" style="height:{r.get('glyph_height',1):.3f}em;vertical-align:{r.get('glyph_baseline',-.12):.3f}em" alt="原卷字形">')
        else:
            if r['flags'][1] and r['text'].strip().isdigit():out.append('<span class="blank">'+e(r['text'])+'</span>')
            else:out.append(markup([r]))
    return ''.join(out)
def source_chars(page):
    return get_unknown_glyphs(page)

def make_paper(entry):
    src=source_pdf(entry);assert sha(src)==entry['source_pdf_sha256']
    category=entry['category'];stem=Path(entry['file']).stem
    target=ROOT/category/'papers'/f'{stem}.htm';target.parent.mkdir(parents=True,exist_ok=True)
    assets=target.with_suffix('.assets');assets.mkdir(exist_ok=True)
    doc=fitz.open(src);sections=[];tex=[];pages=[];glyphs=0;figure_total=0
    for pn,page in enumerate(doc,1):
        unknown=source_chars(page)
        data=extract(page,unknown_glyphs=unknown)
        data['blocks']=prepare(data['blocks'],page)
        rendered=[];textblocks=[];pageglyph=0
        note_pending=any(b['type']=='source_line' for b in data['blocks'])
        plain_text_end=''.join(r['text'] for r in pages[-1]['blocks'][-1].get('runs',[])).rstrip() if pages and pages[-1]['blocks'] else ''
        for bi,b in enumerate(data['blocks']):
            for rs in ([] if b['type']=='source_line' else [b['runs']] if 'runs'in b else [item['runs'] for item in b.get('items',[])]):
                for r in rs:
                    if r.get('glyph_box'):
                        pageglyph+=1;glyphs+=1;name=f'char-{pn:03}-{pageglyph:03}';box=fitz.Rect(r.pop('glyph_box'))
                        box=box+(-.3,-.3,.3,.3)
                        try:page.get_pixmap(dpi=300,clip=box & page.rect,alpha=False).save(assets/(name+'.png'))
                        except Exception as error:raise ValueError(f'{category}/{stem} page {pn} crop {box}: {error}') from None
                        r['glyph']=assets.name+'/'+name+'.png'
                        r['glyph_height']=box.height/r.pop('glyph_font_size',12);r['glyph_baseline']=(r.pop('glyph_origin_y',box.y1-2)-box.y1)/ (box.height/r['glyph_height'])
            if b['type']=='source_line':
                pageglyph+=1;glyphs+=1;name=f'char-{pn:03}-line-{bi:03}';box=fitz.Rect(b['bbox']).normalize()
                page.get_pixmap(dpi=220,clip=box,alpha=False).save(assets/(name+'.png'))
                width=box.width/b['font_size'];height=box.height/b['font_size']
                rendered.append(f'<div class="source-line"><img src="{assets.name}/{name}.png" style="width:{width:.3f}em" alt="原卷文字区域，文字层异常，保留原图"></div>')
                tex.append(r'\noindent\includegraphics[width=\linewidth,height=.8\textheight,keepaspectratio]{'+assets.name+'/'+name+r'.png}\par')
            elif b['type']=='flowchart':
                figure_total+=1;name=f'figure-{pn:03}-{bi:03}'
                copy_flowchart(page,b['bbox'],assets/name)
                rendered.append(f'<figure class="flowchart" style="width:{fitz.Rect(b["bbox"]).width/12:.3f}em"><img src="{assets.name}/{name}.svg" alt="'+e(' → '.join(b['tokens']))+'"></figure>')
                tex.append(r'\begin{center}\includegraphics[width=\linewidth]{'+assets.name+'/'+name+r'.pdf}\end{center}')
            elif b['type']=='choice_row':
                cells='<span class="choice-number">'+htmlruns(b['runs'])+'</span>'+''.join('<span class="choice-item"><strong>'+e(item['label'])+'.</strong> '+htmlruns(item['runs'])+'</span>' for item in b['items'])
                rendered.append('<div class="choice-scroll"><div class="choice-row">'+cells+'</div></div>')
                tex.append(r'\noindent\begin{tabularx}{\linewidth}{@{}lXXXX@{}}'+texruns(b['runs'])+' & '+' & '.join(r'\textbf{'+x['label']+'.} '+texruns(x['runs']) for x in b['items'])+r'\\\end{tabularx}\par')
            elif b['type']=='caption':
                caption='<figcaption>'+htmlruns(b['runs'])+'</figcaption>'
                if rendered and rendered[-1].endswith('</figure>'):rendered[-1]=rendered[-1][:-9]+caption+'</figure>'
                else:rendered.append('<p class="figure-caption">'+htmlruns(b['runs'])+'</p>')
                tex.append(r'\begin{center}'+texruns(b['runs'])+r'\end{center}')
            elif b['type']=='figure':
                figure_total+=1;name=f'figure-{pn:03}-{bi:03}';box=fitz.Rect(b['bbox'])
                temp=fitz.open();clip=box & page.rect;out=temp.new_page(width=clip.width,height=clip.height);out.show_pdf_page(out.rect,doc,pn-1,clip=clip)
                (assets/(name+'.svg')).write_text(temp[0].get_svg_image(text_as_path=True));temp[0].get_pixmap(dpi=160).save(assets/(name+'.png'));temp.close()
                rendered.append(f'<figure><img src="{assets.name}/{name}.svg" alt="原卷图表" loading="lazy"></figure>')
                tex.append(r'\begin{center}\includegraphics[width=.85\linewidth,height=.55\textheight,keepaspectratio]{'+assets.name+'/'+name+r'.png}\end{center}')
            elif b['type']=='options':
                long=any(sum(len(r['text']) for r in item['runs'])>85 for item in b['items'])
                rendered.append('<ul class="options'+(' single' if long else '')+'">'+''.join('<li><span class="option-label">'+e(item['label'])+'.</span><span>'+htmlruns(item['runs'])+'</span></li>' for item in b['items'])+'</ul>')
                tex.append(r'\begin{itemize}[leftmargin=2em,itemsep=.2em,topsep=.4em]'+''.join(r'\item['+item['label']+'.] '+texruns(item['runs'])+'\n' for item in b['items'])+r'\end{itemize}')
            else:
                tag='h2' if b['type']=='heading' else 'p'
                value=texruns(b['runs'])
                join=(bi==0 and pages and pages[-1]['blocks'] and not note_pending
                    and continues_paragraph(pages[-1]['blocks'][-1],b)
                    and sections[-1].endswith('</p></section>'))
                if join:
                    separator='' if plain_text_end.endswith('-') else ' '
                    sections[-1]=sections[-1][:-14]+separator+f'<span data-source-page="{pn}">'+htmlruns(b['runs'])+'</span></p></section>'
                    tex[-1]=tex[-1].rstrip()+separator+value+'\n'
                    b['continues_previous_page']=True
                else:
                    rendered.append(f'<{tag} class="{b["type"]}">'+htmlruns(b['runs'])+f'</{tag}>')
                    tex.append((r'\subsection*{'+value+'}' if tag=='h2' else value)+'\n')
        note=f'<p class="notice">本页部分文字层异常，已保留原图文字区域；这些区域随窗口缩放，暂不能重新换行或复制。</p>' if pageglyph else ''
        sections.append(f'<section data-source-page="{pn}">{note}'+''.join(rendered)+'</section>')
        data.pop('source_text');data['unmapped_source_glyphs']=unknown;data['source_page']=pn;data['inline_glyphs']=pageglyph;pages.append(data)
    title=entry['title'];shared=''
    if entry.get('shared_with_second_paper'):
        second=stem.rsplit('-',1)[0]+'-02.htm';shared=f'<p class="notice">原资料只提供本套的独立部分，其余题目与第 2 套共用。<a href="{second}">打开第 2 套</a></p>'
    body='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+e(title)+'</title><link rel="stylesheet" href="../../style.css"></head><body><header><a href="../index.htm">← 分类目录</a><h1>'+e(title)+'</h1><p>文字重排 · 随窗口自动换行 · 可选中复制 · 离线阅读</p><nav><a href="'+stem+'.tex" download>下载 LaTeX 源码</a><a href="'+stem+'.json" download>下载结构化文本</a></nav>'+shared+'</header><main class="paper">'+''.join(sections)+'</main><footer>图表保留独立原图；不含听力音频及付费解析。</footer></body></html>'
    write_reader(target, body)
    texdoc=r'''\documentclass[UTF8,11pt]{ctexart}
\usepackage[a4paper,margin=22mm]{geometry}
\usepackage{graphicx,enumitem,amssymb,tabularx}
\usepackage[normalem]{ulem}
\usepackage{xeCJKfntef}
\setlength{\parindent}{0pt}
\setlength{\parskip}{.6em}
\sloppy
\begin{document}
'''+r'\section*{'+textext(title)+'}\n'+'\n\n'.join(tex)+'\n'+r'\end{document}'
    target.with_suffix('.tex').write_text(texdoc)
    target.with_suffix('.json').write_text(json.dumps({'title':title,'pages':pages},ensure_ascii=False,indent=2))
    return {'category':category,'year':entry['year'],'title':title,'file':str(target.relative_to(ROOT)),'pages':len(doc),'inline_glyphs':glyphs,'figures':figure_total,'source_pdf_sha256':entry['source_pdf_sha256'],'htm_sha256':sha(target),'source_word_count':entry.get('english_words')}

def catalogs(manifest,entries):
    categories=manifest['categories']
    for category in categories:
        code=category['category'];group=[e for e in entries if e['category']==code];blocks=[]
        for year in sorted({e['year'] for e in group},reverse=True):
            items=sorted((e for e in group if e['year']==year),key=lambda e:Path(e['file']).name,reverse=True)
            cards=''.join('<article class="entry"><h3><a href="'+str(Path(e['file']).relative_to(code))+'">'+e['title']+'</a></h3><p>'+str(e['pages'])+' 页 · 文字重排</p><a href="'+str(Path(e['file']).relative_to(code).with_suffix('.tex'))+'" download>LaTeX 源码</a></article>' for e in items)
            blocks.append(f'<section class="year"><h2>{year}</h2><div class="cards">{cards}</div></section>')
        (ROOT/code/'index.htm').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+category['name']+' · 重排版</title><link rel="stylesheet" href="../style.css"></head><body><header><a href="../index.htm">← 全部考试</a><h1>'+category['name']+'</h1><p>'+str(len(group))+' 套 · HTML 自适应正文与 LaTeX 源码</p></header><main class="catalog">'+''.join(blocks)+'</main></body></html>')
    cards=''.join('<a class="category" href="'+c['category']+'/index.htm"><strong>'+c['name']+'</strong><small>'+str(len([e for e in entries if e['category']==c['category']]))+' 套试卷</small></a>' for c in categories)
    (ROOT/'index.htm').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>英语真题 · 文字重排版</title><link rel="stylesheet" href="style.css"></head><body><header><h1>英语真题 · 文字重排版</h1><p>206 套公开试卷 · 正文随窗口换行 · 可选中复制 · 附 LaTeX 源码</p></header><main class="catalog categories">'+cards+'</main><footer>部分旧卷文字层异常，对应区域保留原图并在页内提示。旧版原卷文件不变。</footer></body></html>')

def main():
    manifest=json.loads((ROOT.parent/'english-exams-web-2026-09-26/manifest.json').read_text());entries=[]
    selected=manifest['papers']
    if '--sample' in sys.argv:
        selected=[x for x in selected if x['file'] in ['kaoyan/papers/2026-01.htm','kaoyan/papers/2000-01.htm','cet4/papers/2014-06-01.htm','cet6/papers/2012-06-01.htm','tem4/papers/2022.htm','tem8/papers/2022.htm']]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for i,result in enumerate(pool.map(make_paper,selected),1):
            entries.append(result);print(f'{i}/{len(selected)} {result["file"]} glyphs={result["inline_glyphs"]} figures={result["figures"]}',flush=True)
    catalogs(manifest,entries)
    (ROOT/'manifest.json').write_text(json.dumps({'papers':entries,'documents':len(entries),'pages':sum(e['pages'] for e in entries),'inline_glyphs':sum(e['inline_glyphs'] for e in entries),'figures':sum(e['figures'] for e in entries),'browser_tested':False},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
