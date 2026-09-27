"""Offline visual catalogs and removal of the requested site URL identifier."""
from pathlib import Path
import html
import re
import fitz

URL_MARK = re.compile(r'(?:https?://)?(?:zhenti\.|www\.)?burningvocabulary\.(?:cn|com)/?',re.I)

def url_rectangles(page):
    result=[]
    for block in page.get_text('rawdict')['blocks']:
        for line in block.get('lines',[]):
            chars=[c for span in line['spans'] for c in span['chars']]
            compact=[];mapping=[]
            for i,c in enumerate(chars):
                for letter in c['c']:
                    if not letter.isspace():compact.append(letter);mapping.append(i)
            for match in URL_MARK.finditer(''.join(compact)):
                selected=chars[mapping[match.start()]:mapping[match.end()-1]+1]
                rect=fitz.Rect(selected[0]['bbox'])
                for c in selected[1:]:rect |= fitz.Rect(c['bbox'])
                result.append(rect)
    return result

def page_without_url(page):
    """Return (page, owning temporary document, removed rectangles).

    Redact only the URL glyphs in an in-memory copy. Preserve images, vectors,
    and the source document; no broad footer crop or white overlay.
    """
    rects=url_rectangles(page)
    if not rects:return page,None,[]
    copied=fitz.open()
    copied.insert_pdf(page.parent,from_page=page.number,to_page=page.number,links=False,annots=False)
    clean=copied[0]
    for r in rects:clean.add_redact_annot(r,fill=False,cross_out=False)
    clean.apply_redactions(images=0,graphics=0,text=0)
    assert not url_rectangles(clean),'URL glyphs survived redaction'
    normal=lambda s:re.sub(r'\s+','',s)
    assert normal(clean.get_text())==URL_MARK.sub('',normal(page.get_text())), 'Redaction touched text outside the URL'
    return clean,copied,[list(r) for r in rects]

def clean_paper_html(body):
    body=re.sub(r'<a href="https?://[^\"]*burningvocabulary[^\"]*">.*?</a>','',body,flags=re.S)
    body=re.sub(r'<footer>.*?</footer>','<footer>本地试卷 · 原卷排版 · 可离线阅读</footer>',body,flags=re.S)
    return body.replace(' · </p>','</p>')

CSS='''
*{box-sizing:border-box}html{background:#f5f6f8;color:#26323d;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;scroll-behavior:smooth}body{margin:0}a{color:inherit;text-decoration:none}a:focus-visible,summary:focus-visible{outline:3px solid #2977bf;outline-offset:5px}header,main,footer{max-width:1060px;margin:auto;padding:0 28px}header{padding-top:40px}h1{font-size:clamp(28px,4vw,42px);line-height:1.3;letter-spacing:-.03em;margin:24px 0 12px}header p,footer{color:#6c7681}.crumb{font-size:14px;color:#586776}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:25px 0}.tabs a{padding:8px 16px;border-radius:22px;background:#e9edf1;color:#596675}.tabs a[aria-current=page]{background:#253b51;color:white}.jump{border-top:1px solid #dde2e7;border-bottom:1px solid #dde2e7;padding:13px 0;margin:26px 0}.jump summary{cursor:pointer;color:#506173}.years{display:flex;flex-wrap:wrap;gap:8px;padding-top:14px}.years a{padding:5px 12px;border:1px solid #dce2e8;border-radius:6px;background:#fff}.year{padding-top:36px;scroll-margin-top:20px}.year h2{font-size:30px;margin:8px 0 28px;text-align:center;letter-spacing:-.02em}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:38px 52px;margin:0 auto 32px;max-width:900px}.paper{display:block;min-width:0;border-radius:12px}.cover{aspect-ratio:595.32/841.92;background:#fff;overflow:hidden;border:1px solid #dce1e7;box-shadow:0 4px 14px #24304412;border-radius:5px;transition:box-shadow .15s,transform .15s}.cover img{width:100%;height:100%;object-fit:contain;display:block;background:white}.paper:hover .cover{box-shadow:0 8px 24px #24304420;transform:translateY(-3px)}.caption{padding:16px 2px 4px;display:flex;align-items:baseline;justify-content:space-between;gap:14px}.caption h3{font-size:19px;font-weight:600;margin:0;line-height:1.45}.caption span{color:#7b8792;font-size:14px;white-space:nowrap}.notice{color:#6c7681;font-size:14px;max-width:900px;margin:18px auto}.home-grid{margin-top:38px}.home-grid .cover{aspect-ratio:4/3}.home-grid .cover img{object-fit:cover;object-position:top}.home-grid .caption h3{font-size:24px}footer{font-size:13px;padding-top:36px;padding-bottom:40px;border-top:1px solid #dde2e7;margin-top:40px}
@media(max-width:620px){header,main,footer{padding-left:18px;padding-right:18px}header{padding-top:24px}.grid{grid-template-columns:minmax(0,1fr);gap:30px;max-width:420px}.year{padding-top:24px}.year h2{font-size:26px}.tabs a{padding:7px 13px}.caption h3{font-size:18px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}.cover{transition:none}.paper:hover .cover{transform:none}}
'''
NAMES={'kaoyan':'考研英语','cet6':'大学英语六级','cet4':'大学英语四级','tem4':'英语专业四级','tem8':'英语专业八级'}

def shell(title,header,body):
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+CSS+'</style></head><body><header>'+header+'</header><main>'+body+'</main><footer>本地真题资料库 · 点击试卷封面打开全文</footer></body></html>'

def card(entry,relative):
    cover=str(Path(relative).with_suffix('.assets')/'page-001.svg')
    title=html.escape(entry['title'])
    return '<a class="paper" href="'+relative+'" aria-label="打开'+title+'"><div class="cover"><img loading="lazy" decoding="async" src="'+cover+'" alt="'+title+' 首页预览" width="595" height="842"></div><div class="caption"><h3>'+title+'</h3><span>'+str(entry['pages'])+' 页</span></div></a>'

def paper_order(entry):
    match=re.search(r'/[0-9]{4}-([0-9]{2})/',entry['source_url'])
    month=int(match.group(1)) if match else 0
    return (-entry['year'],-month,entry.get('paper','01'))

def write_catalogs(root,manifest,legacy=False):
    entries=manifest['papers']
    cats=['kaoyan'] if legacy else list(NAMES)
    for cat in cats:
        group=sorted((r for r in entries if r.get('category','kaoyan')==cat),key=paper_order)
        years=sorted({r['year'] for r in group},reverse=True)
        top=('<span class="crumb">离线真题</span>' if legacy else '<a class="crumb" href="../index.htm">← 全部考试</a>')+'<h1>历年'+NAMES[cat]+'真题</h1><p>'+str(min(years))+'–'+str(max(years))+' 年 · '+str(len(group))+' 套试卷</p>'
        if not legacy:top+='<nav class="tabs" aria-label="考试类别">'+''.join('<a href="../'+c+'/index.htm"'+(' aria-current="page"' if c==cat else '')+'>'+NAMES[c]+'</a>' for c in cats)+'</nav>'
        top+='<details class="jump"><summary>按年份跳转</summary><nav class="years">'+''.join(f'<a href="#year-{y}">{y}</a>' for y in years)+'</nav></details>'
        body=''
        if cat in ('tem4','tem8'):body='<p class="notice">当前收录公开可访问的 2022–2025 年试卷。</p>'
        for year in years:
            cards=''.join(card(r,r['file'] if legacy else str(Path(r['file']).relative_to(cat))) for r in group if r['year']==year)
            body+=f'<section class="year" id="year-{year}"><h2>{year}年</h2><div class="grid">{cards}</div></section>'
        destination=root/'index.htm' if legacy else root/cat/'index.htm'
        destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(shell('历年'+NAMES[cat]+'真题',top,body))
    if not legacy:
        tiles=[]
        for cat in cats:
            group=sorted((r for r in entries if r['category']==cat),key=paper_order)
            first=group[0];image=str(Path(first['file']).with_suffix('.assets')/'page-001.svg')
            tiles.append('<a class="paper" href="'+cat+'/index.htm"><div class="cover"><img src="'+image+'" loading="lazy" alt="'+NAMES[cat]+'试卷预览"></div><div class="caption"><h3>'+NAMES[cat]+'</h3><span>'+str(len(group))+' 套</span></div></a>')
        (root/'index.htm').write_text(shell('英语真题资料库','<h1>英语真题资料库</h1><p>五类考试 · 206 套试卷 · 离线阅读</p>','<div class="grid home-grid">'+''.join(tiles)+'</div>'))
