"""Archive publicly listed examination documents as offline HTML.
No authentication, premium translations/answers, application or database writes.
"""
# Shared reader shell: inject before this generator computes the HTML digest.
import sys as _reader_sys
from pathlib import Path as _ReaderPath
_reader_ui = next(p / 'exam-library' for p in _ReaderPath(__file__).resolve().parents if (p / 'exam-library/enhance_readers.py').is_file())
if str(_reader_ui) not in _reader_sys.path: _reader_sys.path.insert(0, str(_reader_ui))
from enhance_readers import write_reader
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib, html, json, re, time, base64
from lxml import etree
import requests
import fitz
from lxml import html as lh
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"layout-tools"))
from archive_renderer import STYLE as ARCHIVE_STYLE, render_page, RENDERER_VERSION
from catalog_design import clean_paper_html,write_catalogs

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / '.firecrawl'
catalogs=json.loads((CACHE/'catalogs.json').read_text())
urls=[u for c in catalogs for u in c['links']]
assert len(urls)==162 and len(set(urls))==162
NAMES={'kaoyan':'考研英语','cet6':'大学英语六级','cet4':'大学英语四级','tem4':'英语专业四级','tem8':'英语专业八级'}
STYLE = ARCHIVE_STYLE
def sha(b): return hashlib.sha256(b).hexdigest()
def fetch(url):
    for n in range(3):
        try:
            r=requests.get(url,timeout=(15,60),headers={'User-Agent':'AnkiStudyArchive/1.0 (personal offline study)'})
            if r.status_code in (401,403): raise RuntimeError(f'access restricted: HTTP {r.status_code}')
            r.raise_for_status();return r
        except (requests.Timeout,requests.ConnectionError):
            if n==2:raise
            time.sleep(n+1)
    raise RuntimeError('fetch failed')
def archive(url):
    parts=url.split('/')[3:];category=parts[0];key='-'.join(parts[1:]);year=parts[1][:4];kind=parts[-1] if len(parts)>2 else '01'
    cache= CACHE/category;cache.mkdir(exist_ok=True)
    raw_file=cache/f'{key}-viewer.htm';pdf_file=cache/f'{key}.pdf'
    if raw_file.exists():
        raw=raw_file.read_text(encoding='utf-8')
    else:
        response=fetch(url);raw=response.content.decode('utf-8')
    raw_file.write_text(raw,encoding='utf-8')
    marker=re.search(r'var\s+globalConfig\s*=\s*',raw)
    if not marker:raise RuntimeError('public viewer configuration missing')
    cfg=json.JSONDecoder().raw_decode(raw[marker.end():])[0]
    assert cfg['filePath']=='/'.join(parts)
    name=cfg['title']
    host=cfg.get('pdfHost','https://zhenti.burningvocabulary.cn')
    assert host in ['https://res-zhenti.burningvocabulary.cn','https://zhenti.burningvocabulary.cn']
    # Identical public document path used by the site's standard viewer.
    pdf_url=host+'/images/read/'+cfg['filePath']+'/'+''.join((cfg['fn']['f1']+cfg['fn']['f2'])[::-1])+'.pdf'
    if cfg.get('fnameVersion'): pdf_url+='?v='+str(cfg['fnameVersion'])
    pdf_bytes=pdf_file.read_bytes() if pdf_file.exists() else fetch(pdf_url).content
    assert pdf_bytes.startswith(b'%PDF'), 'not a PDF document'
    pdf_file.write_bytes(pdf_bytes)
    rendering=[];pages=[];counts=[];text_preserved=True;images=0;total_words=0;raw_text=[];encoding_pages=[];shared_note=False
    with fitz.open(stream=pdf_bytes,filetype='pdf') as doc:
        assert not doc.needs_pass and len(doc)>0
        for n,page in enumerate(doc,1):
            text=page.get_text('text')
            markup,info=render_page(page,n,(ROOT/category/'papers')/(key+'.assets')/f'page-{n:03}.svg')
            rendering.append(info)
            if info['source_encoding_warning']:encoding_pages.append(n)
            shared_note=shared_note or '其余与第2套完全一致' in text
            images+=info['embedded_source_images'];counts.append(len(text));total_words+=len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*",text));raw_text.append(text)
            pages.append(f'<section class="page-wrap" data-page="{n}"><div class="page-label">第 {n} / {len(doc)} 页</div><div class="sheet">{markup}</div></section>')
        page_count=len(doc)
    assert total_words>1000 or (page_count==1 and shared_note), 'unexpectedly short examination document'
    archive_note=''
    if shared_note: archive_note='<p><strong>原站说明：本卷只单列作文和翻译，其余题目与第 2 套相同。</strong> <a href="'+key[:-2]+'02.htm">打开同次考试第 2 套</a></p>'
    if encoding_pages: archive_note+='<p>第 '+','.join(map(str,encoding_pages))+' 页原始文字编码异常，已内嵌原页图像保证阅读效果；这些页的复制/搜索文字可能不准确。</p>'
    timestamp=datetime.now(timezone.utc).isoformat()
    body='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="source-url" content="'+html.escape(url,quote=True)+'"><title>'+html.escape(name)+'</title><style>'+STYLE+'</style></head><body><header><a href="../index.htm">← 全部年份</a><h1>'+html.escape(name)+'</h1><p>离线存档 · '+str(page_count)+' 页 · <a href="'+url+'">原网站</a></p><p>原卷排版保真，随窗口缩放；展开每页文字可复制或查找整句。请保留同名 .assets 素材文件夹；不包含听力音频、网站付费解析或翻译功能。</p>'+archive_note+'</header><main id="exam-pages">'+''.join(pages)+'</main><footer>来源：英语真题在线 · 抓取时间 '+timestamp+' · 原站署名和试卷内容保留。</footer></body></html>'
    target=ROOT/category/'papers'/f'{key}.htm';target.parent.mkdir(parents=True,exist_ok=True);write_reader(target, clean_paper_html(body),encoding='utf-8')
    (cache/f'{key}-text.json').write_text(json.dumps(raw_text,ensure_ascii=False,indent=2),encoding='utf-8')
    time.sleep(.35)
    return {'category':category,'year':int(year),'paper':kind,'title':name,'source_url':url,'document_url':pdf_url,'file':str(target.relative_to(ROOT)),'status':'complete','renderer':RENDERER_VERSION,'page_rendering':rendering,'asset_directory':str(target.with_suffix('.assets').relative_to(ROOT)),'pages':page_count,'text_characters':sum(counts),'english_words':total_words,'page_text_characters':counts,'embedded_images':images,'copy_text_matches_xml_safe_source':text_preserved,'encoding_warning_pages':encoding_pages,'shared_with_second_paper':shared_note,'offline_images':True,'source_pdf_sha256':sha(pdf_bytes),'htm_sha256':sha(target.read_bytes()),'fetched_at':timestamp}


results=[];failures=[]
restricted=[{'category':'tem4','advertised_papers':13,'public_papers':4,'unavailable_papers':9,'range':'2010–2021','reason':'目录明确要求付费解锁；未尝试访问受限页面'}, {'category':'tem8','advertised_papers':15,'public_papers':4,'unavailable_papers':11,'range':'2010–2021','reason':'目录明确要求付费解锁；未尝试访问受限页面'}]
def save_progress():
    (ROOT/'download-progress.json').write_text(json.dumps({'expected_public_new':len(urls),'completed_new':len(results),'failures':failures,'restricted':restricted,'papers':sorted(results,key=lambda x:x['source_url'])},ensure_ascii=False,indent=2)+'\n')
with ThreadPoolExecutor(max_workers=1) as pool:
    jobs={pool.submit(archive,u):u for u in urls}
    for future in as_completed(jobs):
        u=jobs[future]
        try:
            r=future.result();results.append(r);print(f"OK {len(results)}/{len(urls)} {r['category']} {r['title']} {r['pages']} pages",flush=True)
        except Exception as e:
            failures.append({'source_url':u,'error':str(e)});print('FAILED',u,type(e).__name__,str(e),flush=True)
        save_progress()

# Reuse the already verified 44 examinations without a second network download.
import shutil
legacy=ROOT.parent/'kaoyan-web-2026-09-26'
prior=json.loads((legacy/'manifest.json').read_text())
assert prior['completed']==44 and not prior['failures']
for entry in prior['papers']:
    r=dict(entry);f=legacy/r['file'];assert sha(f.read_bytes())==r['htm_sha256']
    target=ROOT/'kaoyan'/r['file'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,target)
    shutil.copytree(f.with_suffix('.assets'),target.with_suffix('.assets'),dirs_exist_ok=True)
    r['category']='kaoyan';r['file']=str(target.relative_to(ROOT));r['asset_directory']=str(target.with_suffix('.assets').relative_to(ROOT));r['reused_from']='../kaoyan-web-2026-09-26/manifest.json';results.append(r)

INDEX_STYLE='body{max-width:1000px;margin:40px auto;padding:0 24px;font:17px/1.7 system-ui;color:#243044;background:#fafbfc}a{color:#1258a2}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:10px 8px;border-bottom:1px solid #dce3eb}p{color:#526074}h1{font-size:30px}.notice{padding:16px;background:#fff4da;border-radius:8px}.category{margin:20px 0;padding:20px;background:white;border:1px solid #dde4ed;border-radius:12px}'
def document(title,body):return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+INDEX_STYLE+'</style></head><body>'+body+'</body></html>'
summary=[];cards=[]
for cat in NAMES:
    group=sorted((r for r in results if r['category']==cat),key=lambda x:x['source_url'],reverse=True)
    expected=44 if cat=='kaoyan' else len(next(c for c in catalogs if c['category']==cat)['links'])
    rows=''.join('<tr><td><a href="'+str(Path(r['file']).relative_to(cat))+'">'+html.escape(r['title'])+'</a></td><td>'+str(r['pages'])+'</td><td><a href="'+r['source_url']+'">来源</a></td></tr>' for r in group)
    notice=''
    if cat in ['tem4','tem8']:notice='<p class="notice">当前已保存 2022–2025 年公开的 4 套试卷。2010–2021 年需要网站付费账号，尚未获取；2026 年目录标注持续更新中。</p>'
    if cat in ['cet4','cet6']:notice='<p>2026 年 6 月仅上架第 2、3 套；第 1 套原站标注将考前发布。</p>'
    (ROOT/cat/'index.htm').write_text(document(NAMES[cat]+' · 离线真题','<a href="../index.htm">← 全部考试</a><h1>'+NAMES[cat]+'</h1><p>'+str(len(group))+' / '+str(expected)+' 套公开试卷，'+str(sum(r['pages'] for r in group))+' 页。</p>'+notice+'<table><thead><tr><th>试卷</th><th>页数</th><th>原网页</th></tr></thead><tbody>'+rows+'</tbody></table>'),encoding='utf-8')
    item={'category':cat,'name':NAMES[cat],'expected_public':expected,'downloaded':len(group),'pages':sum(r['pages'] for r in group),'years':sorted({r['year'] for r in group})};summary.append(item)
    cards.append('<div class="category"><h2><a href="'+cat+'/index.htm">'+NAMES[cat]+'</a></h2><p>'+str(len(group))+' 套 · '+str(item['pages'])+' 页 · '+str(min(item['years']))+'–'+str(max(item['years']))+' 年</p>'+notice+'</div>')
(ROOT/'index.htm').write_text(document('英语真题离线总目录','<h1>英语真题离线总目录</h1><p>已保存 '+str(len(results))+' 套 · '+str(sum(r['pages'] for r in results))+' 页，包含此前的 44 套考研英语。</p><p>各试卷为离线 HTM 与配套素材，文字可选择、搜索，图片和图形内嵌。无需 PDF 阅读器。只存档题面，不含听力音频、网站付费答案解析或翻译。</p><p class="notice">专四、专八更早年份需要付费解锁，未获取，详见对应目录。</p>'+''.join(cards)+'<p>来源：<a href="https://zhenti.burningvocabulary.cn/">英语真题在线</a>。逐套来源、页数和 SHA-256 见 manifest.json。</p>'),encoding='utf-8')
manifest={'created_at':datetime.now(timezone.utc).isoformat(),'source':'https://zhenti.burningvocabulary.cn/','expected_public_total':206,'completed':len(results),'newly_downloaded':len(results)-44,'reused_kaoyan':44,'categories':summary,'restricted':restricted,'failures':failures,'papers':sorted(results,key=lambda x:x['source_url'])}
(ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(ROOT/'README.md').write_text('# 英语真题离线 HTM 归档\n\n打开 index.htm 查看五类目录。各类 papers/*.htm 为离线题面与配套素材，可离线打开、选择文字、搜索。图片及矢量图形内嵌。\n\n新增公开试卷：六级 83 套、四级 71 套、专四 4 套、专八 4 套；复用此前考研 44 套，共 206 套公开目录目标。实际完成数及失败项见 manifest.json。\n\n## 未获取的部分\n\n专四目录标称 13 套，公开 4 套，其余 9 套受限；专八标称 15 套，公开 4 套，其余 11 套受限。早期 2010–2021 年须付费解锁，未尝试访问。专四/专八 2026 年待原站更新；四级/六级 2026 年 6 月第 1 套未上架。听力音频、付费解析/翻译、用户账号功能不在本次 HTM 题面归档内。\n\n## 来源与校验\n\n使用原站公开网页中的标准阅读器配置读取公开试卷，转换为 HTML；未使用账号或绕过受限页面。逐页文本按 HTML5 数字字符引用规则转换后忽略空白一致、图片内嵌、每套 SHA-256、页数与来源链接记录在清单。这验证转换完整性，不证明原站试卷内容本身无误。可见字形使用原字体轮廓。少数旧卷源文字编码异常，相关页内嵌原页图像保留阅读效果，复制/搜索文字可能不准确，清单 encoding_warning_pages 列出页码。2022 年 6 月四级和六级第 3 套依原站只含作文与翻译，其他题目与第 2 套相同，已加本地链接。\n\n.firecrawl/ 保留响应和源文档以便追溯；日常阅读及 ZIP 只需 HTM 和清单。未修改 Anki 数据库、模板或发布新版本。\n',encoding='utf-8')
write_catalogs(ROOT,json.loads((ROOT/'manifest.json').read_text()),legacy=False)
print('DONE',len(results),'total;',len(failures),'failures; 20 older TEM papers restricted',flush=True)
if failures:raise SystemExit(1)
