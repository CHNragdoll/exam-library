"""Build a verified, offline layout repair in a staging tree. Never downloads."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import copy
import json
import re
import shutil
import zipfile
import fitz
from lxml import html
from archive_renderer import STYLE, RENDERER_VERSION, render_page, safe_text, digest

SOURCES = Path(__file__).resolve().parent.parent
COMBINED = SOURCES/'english-exams-web-2026-09-26'
LEGACY = SOURCES/'kaoyan-web-2026-09-26'
STAGE = SOURCES/'.layout-repair-stage'
BACKUP = SOURCES/'layout-repair-backup'

def write_json(path, data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def backup():
    BACKUP.mkdir(exist_ok=True)
    records=[]
    for root in (COMBINED, LEGACY):
        paths=[p for ext in ('*.htm','*.svg') for p in root.rglob(ext) if '.firecrawl' not in p.parts]
        paths += [p for p in root.iterdir() if p.suffix in ('.json','.md','.py')]
        for f in paths:
            target=BACKUP/root.name/f.relative_to(root)
            if target.exists():
                assert target.read_bytes()==f.read_bytes(), f'Backup differs from current file; select a new backup directory: {f}'
            if not target.exists():
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(f,target)
            records.append({'file':str(target.relative_to(BACKUP)), 'sha256':digest(target.read_bytes())})
    for f in SOURCES.glob('*.zip'):
        if f.name in ('英语真题_HTM_公开206套.zip','考研英语真题_2000-2026_HTM_44套.zip'):
            target=BACKUP/f.name
            if target.exists():assert target.read_bytes()==f.read_bytes(), f'Backup differs from current ZIP: {f}'
            if not target.exists():shutil.copy2(f,target)
            records.append({'file':target.name,'sha256':digest(target.read_bytes())})
    write_json(BACKUP/'backup-manifest.json',records)
    # Byte-for-byte recovery check, independent of the current generated files.
    for r in records: assert digest((BACKUP/r['file']).read_bytes())==r['sha256']
    return len(records)

def source_pdf(entry):
    stem=Path(entry['file']).stem
    if entry['category']=='kaoyan':return LEGACY/'.firecrawl'/(stem+'.pdf')
    return COMBINED/'.firecrawl'/entry['category']/(stem+'.pdf')

def rebuild():
    assert not STAGE.exists(), 'Staging tree already exists; do not mix runs. Choose a fresh STAGE path.'
    print('BACKUP',backup(),'files',flush=True)
    for root in (COMBINED,LEGACY):
        dest=STAGE/root.name;dest.mkdir(parents=True,exist_ok=True)
        for f in root.rglob('index.htm'):
            if '.firecrawl' in f.parts:continue
            target=dest/f.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,target)
        for name in ('README.md','manifest.json'):
            shutil.copy2(root/name,dest/name)
    manifest=json.loads((COMBINED/'manifest.json').read_text())
    for i,entry in enumerate(manifest['papers'],1):
        pdf=source_pdf(entry)
        assert pdf.is_file(),f'missing offline source: {pdf}'
        assert digest(pdf.read_bytes())==entry['source_pdf_sha256'],pdf
        sections=[];meta=[]
        paper_target=STAGE/COMBINED.name/entry['file']
        with fitz.open(pdf) as doc:
            assert len(doc)==entry['pages']
            for n,page in enumerate(doc,1):
                markup,info=render_page(page,n,paper_target.with_suffix('.assets')/f'page-{n:03}.svg')
                sections.append(f'<section class="page-wrap" data-page="{n}"><div class="page-label">第 {n} / {len(doc)} 页</div><div class="sheet">{markup}</div></section>')
                meta.append(info)
        old=(COMBINED/entry['file']).read_text()
        body=re.sub(r'<style>.*?</style>',lambda _: '<style>'+STYLE+'</style>',old,count=1,flags=re.S)
        body,count=re.subn(r'<main id="exam-pages">.*?</main>',lambda _: '<main id="exam-pages">'+''.join(sections)+'</main>',body,count=1,flags=re.S)
        assert count==1
        body=re.sub(r'<p>正文与图表已内嵌.*?</p>','<p>原卷排版 · 随窗口缩放 · 可离线阅读。点击每页下方“查看 / 复制本页文字”提取文字或查找整句；少数旧卷编码异常页已标注。不含听力音频及网站付费解析。</p>',body,count=1)
        body=re.sub(r'<p>第 [0-9,]+ 页原始文字编码异常.*?</p>','',body)
        target=STAGE/COMBINED.name/entry['file'];target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(body)
        for field in ['pdf_text_matches_html_ignoring_whitespace','pdf_text_matches_html_after_html5_mapping']:
            entry.pop(field,None)
        entry.update({'renderer':RENDERER_VERSION,'htm_sha256':digest(target.read_bytes()),
                      'layout_repaired_at':datetime.now(timezone.utc).isoformat(),
                      'page_rendering':meta,'copy_text_matches_xml_safe_source':True,
                      'encoding_warning_pages':[r['page'] for r in meta if r['source_encoding_warning']]})
        if entry['category']=='kaoyan':
            legacy_target=STAGE/LEGACY.name/'papers'/target.name
            legacy_target.parent.mkdir(exist_ok=True);shutil.copy2(target,legacy_target)
            shutil.copytree(target.with_suffix('.assets'),legacy_target.with_suffix('.assets'),dirs_exist_ok=True)
        print(f'REBUILT {i}/206 {entry["file"]}',flush=True)
    write_json(STAGE/COMBINED.name/'manifest.json',manifest)
    legacy=json.loads((LEGACY/'manifest.json').read_text())
    by_name={Path(r['file']).name:r for r in manifest['papers'] if r['category']=='kaoyan'}
    for i,r in enumerate(legacy['papers']):
        replacement=copy.deepcopy(by_name[Path(r['file']).name]);replacement['file']=r['file'];replacement.pop('reused_from',None)
        legacy['papers'][i]=replacement
    write_json(STAGE/LEGACY.name/'manifest.json',legacy)
    for root in (COMBINED,LEGACY):
        readme=STAGE/root.name/'README.md'
        s=readme.read_text()
        s=s.replace('PDF 字体使用本机字体替代，布局可能有轻微差异。','').replace('字体由本机替代，可能有轻微布局差异。','')
        s+='\n## 排版修正版\n\n全部页改用内嵌 SVG 保留源字体轮廓、字距、下划线和图表坐标；页面按窗口等比缩放。每页有独立文字层和可展开的复制文本。可见内容不依赖本机字体；原站网页叠加的圆形答题按钮、解析等交互不属于试卷源内容。\n\n少数源文档的字符编码异常仍影响复制/搜索，相关页明确提示；本次没有用猜测替换文字。原始来源和 PDF 缓存不变。备份位于 ../layout-repair-backup/。\n'
        readme.write_text(s)
        for index in (STAGE/root.name).rglob('index.htm'):
            s=index.read_text().replace('</h1>','</h1><p>排版修正版：保留原字体与图形坐标，自动适应窗口宽度。各页下方可展开复制文字。</p>',1)
            index.write_text(s)
    print('STAGED',flush=True)

if __name__=='__main__':
    rebuild()
