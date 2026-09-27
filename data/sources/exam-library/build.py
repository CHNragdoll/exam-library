"""Create a dual-version catalog using the existing SVG catalog design."""
from pathlib import Path
import os,html,json
from lxml import html as lh,etree
ROOT=Path(__file__).resolve().parent
SOURCES=ROOT.parent
SVG=SOURCES/'english-exams-web-2026-09-26'
REFLOW=SOURCES/'english-exams-reflow-latex'
CATEGORIES=[('kaoyan','考研英语',SVG/'kaoyan/index.htm',REFLOW/'kaoyan/index.htm','2000–2026 年 · 44 套'),('math3','考研数学三',SOURCES/'math3-2009-2019-htm/index.htm',SOURCES/'math3-latex-2009-2019/index.htm','1987–2019 年 · 33 年真题及参考答案'),('cet6','大学英语六级',SVG/'cet6/index.htm',REFLOW/'cet6/index.htm','2012–2026 年 · 83 套'),('cet4','大学英语四级',SVG/'cet4/index.htm',REFLOW/'cet4/index.htm','2014–2026 年 · 71 套'),('tem4','英语专业四级',SVG/'tem4/index.htm',REFLOW/'tem4/index.htm','2022–2025 年 · 4 套'),('tem8','英语专业八级',SVG/'tem8/index.htm',REFLOW/'tem8/index.htm','2022–2025 年 · 4 套')]
CATEGORIES.insert(2,('cs408','408 计算机统考',SOURCES/'cs408-original/index.htm',SOURCES/'cs408-latex-2009-2017/index.htm','2009–2025 年 · 17 年真题及答案解析'))
CATEGORIES.insert(3,('politics','考研政治',SOURCES/'politics-original/index.htm',SOURCES/'politics-latex-2003-2023/index.htm','2003–2023 年 · 21 年真题，2009–2023 年答案解析'))
def e(s):return html.escape(str(s),quote=True)
def link(target,page):return os.path.relpath(target,page.parent)
def read(p):return lh.fromstring(p.read_text())
def serial(node):return etree.tostring(node,encoding='unicode',method='html')
KINDS={'questions':'真题','answers':'答案解析','complete':'真题与解析'}
def collect():
    docs=[]
    for code,name,svgindex,latexindex,_ in CATEGORIES:
        indexes=[svgindex]
        if code=='math3':indexes.append(SOURCES/'math3-1987-2009-htm/index.htm')
        for index in indexes:
            for card in read(index).xpath('//main//a[contains(concat(" ",normalize-space(@class)," ")," paper ")]'):
                svg=(index.parent/card.get('href')).resolve();year=int(svg.name[:4])
                if index!=svgindex and year==2009:continue
                latex=latexindex.parent/'papers'/svg.name
                if code=='cs408' and svg.stem.endswith('-answers'):latex=SOURCES/'cs408-answers-latex-2016-2025/papers'/svg.name
                if code=='politics' and svg.stem.endswith('-answers'):latex=SOURCES/'politics-answers-latex-2009-2023/papers'/svg.name
                if code=='math3' and year<2009:latex=SOURCES/'math3-latex-1987-2009/papers'/svg.name
                title=card.xpath('.//h3')[0].text_content().strip()
                cover=(index.parent/card.xpath('.//img')[0].get('src')).resolve()
                assert all(x.is_file() for x in [svg,latex,cover]),(svg,latex,cover)
                kind=next((k for k in KINDS if svg.stem.endswith('-'+k)),'questions')
                caption=card.xpath('.//div[@class="caption"]/span')
                docs.append(dict(id=code+':'+svg.stem,title=title,category=code,categoryLabel=name,year=year,kind=kind,svg=svg,reflow=latex,cover=cover,detail=caption[0].text_content() if caption else ''))
        stems=[d['svg'].stem for d in docs if d['category']==code]
        if code=='cs408':
            expected=[f'{y}-complete' for y in range(2009,2016)]+[f'{y}-questions' for y in range(2016,2026)]+[f'{y}-answers' for y in range(2016,2026)]
            assert sorted(stems)==sorted(expected),('408 expected years/kinds',stems)
        if code=='math3':
            expected=[f'{year}-{kind}' for year in range(2019,1986,-1) for kind in ['questions','answers']]
            assert sorted(stems)==sorted(expected)
            for d in docs:
                if d['category']==code and d['year']==2009:
                    assert 'math3-2009-2019-htm' in str(d['svg']) and 'math3-latex-2009-2019' in str(d['reflow'])
    assert len({d['id'] for d in docs})==len(docs)
    order={c[0]:i for i,c in enumerate(CATEGORIES)}
    return sorted(docs,key=lambda d:(-d['year'],order[d['category']],list(KINDS).index(d['kind']),d['title']))
def document(title,body,page):
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+e(title)+'</title><link rel="stylesheet" href="'+e(link(ROOT/'ui/tokens.css',page))+'"><link rel="stylesheet" href="'+e(link(ROOT/'catalog.css',page))+'"><script defer src="'+e(link(ROOT/'ui/catalog.js',page))+'"></script></head><body>'+body+'</body></html>'
def versions(d,page):
    title=d['title']
    return '<div class="versions" aria-label="'+e(title)+' 版本选择"><a href="'+e(link(d['svg'],page))+'" aria-label="'+e(title)+' · SVG 原版">SVG 原版</a><a class="reflow" href="'+e(link(d['reflow'],page))+'" aria-label="'+e(title)+' · LaTeX 重排版">LaTeX 重排</a></div>'
def card(d,page,mode):
    target=d['reflow'] if mode=='latex' else d['svg']
    attrs=' '.join('data-'+k+'="'+e(d[k])+'"' for k in ['id','year','category','kind'])
    search=d['title']+' '+d['categoryLabel']+' '+KINDS[d['kind']]
    return '<article class="paper" '+attrs+' data-search="'+e(search)+'"><a class="cover-link" href="'+e(link(target,page))+'" aria-label="'+e(d['title'])+' · '+('LaTeX 重排版' if mode=='latex' else 'SVG 原版')+'"><div class="cover"><img loading="lazy" decoding="async" src="'+e(link(d['cover'],page))+'" alt="" width="595" height="842"></div></a><div class="caption"><div class="paper-meta"><span>'+e(d['categoryLabel'])+'</span><span class="kind kind-'+d['kind']+'">'+KINDS[d['kind']]+'</span></div><h3><a href="'+e(link(target,page))+'">'+e(d['title'])+'</a></h3><p>'+e(d['detail'])+'</p></div>'+versions(d,page)+'</article>'
def render(docs,all_docs,page,active='',mode=''):
    names={c[0]:c[1] for c in CATEGORIES};name=names.get(active,'考研真题大全')
    counts={c[0]:sum(d['category']==c[0] for d in all_docs) for c in CATEGORIES}
    years=sorted({d['year'] for d in docs},reverse=True)
    title=name+(' · SVG 原版' if mode=='svg' else ' · LaTeX 重排' if mode=='latex' else '')
    nav='<a class="subject-link" href="'+e(link(ROOT/'index.htm',page))+'"'+(' aria-current="page"' if not active else '')+'><span>全部资料</span><span>'+str(len(all_docs))+'</span></a>'
    for code,label,*_ in CATEGORIES:
        nav+='<a class="subject-link" href="'+e(link(ROOT/code/'index.htm',page))+'"'+(' aria-current="page"' if active==code else '')+'><span>'+label+'</span><span>'+str(counts[code])+'</span></a>'
    header='<a class="skip-link" href="#catalog-main">跳到资料列表</a><header class="site-header"><a class="brand" href="'+e(link(ROOT/'index.htm',page))+'"><span class="brand-mark" aria-hidden="true">卷</span><span>考研真题大全<small>本地学习资料库</small></span></a><span class="offline-label"><span aria-hidden="true">●</span> 离线可读</span></header>'
    aside='<aside class="sidebar"><p class="nav-label">资料分类</p><nav aria-label="资料分类">'+nav+'</nav><div class="sidebar-note"><strong>选择适合的阅读方式</strong><p>SVG 原版保留卷面排版。<br>LaTeX 重排随窗口宽度换行。</p><a href="'+e(link(ROOT/'image-review.htm',page))+'">插图重绘对照审计 →</a></div></aside>'
    heading='<div class="page-heading"><div><p class="eyebrow">'+('按科目查阅' if active else '你的备考书架')+'</p><h1>'+e(title)+'</h1><p>'+str(len(docs))+' 份资料 · '+str(min(years))+'—'+str(max(years))+' 年 · 两种阅读版本</p></div></div>'
    recent='<section class="recent-panel" aria-labelledby="recent-title"><div class="section-line"><h2 id="recent-title">继续阅读</h2><button type="button" id="clear-recent" class="text-button" hidden>清除记录</button></div><p id="recent-empty" class="subtle">读过的试卷会显示在这里，方便接着读。</p><div id="recent-list" class="recent-list"></div></section>'
    subject='<label>科目<select id="filter-category" name="category"><option value="">全部科目</option>'+''.join('<option value="'+c+'">'+e(n)+'</option>' for c,n,*_ in CATEGORIES)+'</select></label>' if not active else ''
    filters='<form id="catalog-filters" class="filters" role="search" aria-label="筛选真题"><label class="search-field"><span>搜索资料</span><input id="catalog-search" name="q" type="search" placeholder="搜索年份、科目或试卷名称" autocomplete="off"></label><div class="filter-controls">'+subject+'<label>年份<select id="filter-year" name="year"><option value="">全部年份</option>'+''.join('<option value="'+str(y)+'">'+str(y)+' 年</option>' for y in years)+'</select></label><label>类型<select id="filter-kind" name="kind"><option value="">全部类型</option>'+''.join('<option value="'+k+'">'+v+'</option>' for k,v in KINDS.items() if any(d['kind']==k for d in docs))+'</select></label><button class="reset-button" type="reset">清除筛选</button></div></form>'
    groups=''.join('<section class="year" id="year-'+str(y)+'"><div class="year-heading"><h2>'+str(y)+'<span> 年</span></h2><span class="year-count">'+str(sum(d['year']==y for d in docs))+' 份资料</span></div><div class="grid">'+''.join(card(d,page,mode) for d in docs if d['year']==y)+'</div></section>' for y in years)
    empty='<div id="no-results" class="empty-state" hidden><h2>没有找到匹配的资料</h2><p>试试其他年份或更短的关键词。</p><button type="button" id="empty-reset">清除筛选，查看全部</button></div>'
    body=header+'<div class="app-shell">'+aside+'<main id="catalog-main" data-active-category="'+e(active)+'">'+heading+recent+filters+'<div class="result-summary"><h2>资料列表</h2><p id="result-count" role="status" aria-live="polite">共 '+str(len(docs))+' 份资料</p></div><div id="paper-list">'+groups+'</div>'+empty+'<div class="load-more"><button type="button" id="load-more" hidden>显示更多</button></div><noscript><p class="notice">当前显示全部资料。启用 JavaScript 后可使用搜索、筛选和阅读记录。</p></noscript><footer>本地离线资料库 · 题卷与答案以所收录原稿为准。<a href="#catalog-main">回到顶部 ↑</a></footer></main></div>'
    page.parent.mkdir(exist_ok=True);page.write_text(document(title,body,page))
def main():
    docs=collect();(ROOT/'catalog.css').write_text('/* Shared catalog styles; edit ui/catalog.css. */\n@import url("ui/catalog.css");\n')
    (ROOT/'documents.json').write_text(json.dumps([{k:(link(v,ROOT/'index.htm') if isinstance(v,Path) else v) for k,v in d.items()} for d in docs],ensure_ascii=False,indent=2))
    render(docs,docs,ROOT/'index.htm')
    for code,*_ in CATEGORIES:
        selected=[d for d in docs if d['category']==code];render(selected,docs,ROOT/code/'index.htm',code)
        if code=='math3':render(selected,docs,ROOT/code/'svg.htm',code,'svg')
        if code in ['math3','cs408','politics']:render(selected,docs,ROOT/code/'latex.htm',code,'latex')
    checks=0
    for p in ROOT.rglob('*.htm'):
        if 'work' in p.relative_to(ROOT).parts:continue
        t=read(p);assert not t.xpath('//a//a')
        for value in t.xpath('//@href|//@src'):
            if value.startswith('#'):
                assert t.xpath('//*[@id=$target]',target=value[1:]);continue
            assert (p.parent/value).is_file(),(p,value);checks+=1
        cards=t.xpath('//article[@class="paper"]');assert all(len(c.xpath('./div[@class="versions"]/a'))==2 for c in cards)
    counts={c[0]:sum(d['category']==c[0] for d in docs) for c in CATEGORIES}
    (ROOT/'verification.json').write_text(json.dumps({'categories':counts,'paper_cards':len(docs),'version_links':len(docs)*2,'local_links_checked':checks,'browser_tested':False},ensure_ascii=False,indent=2))
    print(counts,checks,'local links verified')
    if (ROOT/'enhance_readers.py').is_file():
        from enhance_readers import enhance_all
        enhance_all()
    from build_image_review import build_review
    build_review()
if __name__=='__main__':main()
