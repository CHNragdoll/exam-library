"""Local, backed-up update of catalogs and visible site identifiers."""
# Shared reader shell: inject before this generator computes the HTML digest.
import sys as _reader_sys
from pathlib import Path as _ReaderPath
_reader_ui = next(p / 'exam-library' for p in _ReaderPath(__file__).resolve().parents if (p / 'exam-library/enhance_readers.py').is_file())
if str(_reader_ui) not in _reader_sys.path: _reader_sys.path.insert(0, str(_reader_ui))
from enhance_readers import write_reader
from pathlib import Path
import copy
import json
import re
import shutil
from datetime import datetime
import fitz
from archive_renderer import render_page,digest,RENDERER_VERSION
from catalog_design import url_rectangles,write_catalogs
from repair_archive import COMBINED,LEGACY,SOURCES,source_pdf,write_json

RUN=SOURCES/'visual-catalog-run'
BACKUP=RUN/'backup'
STAGE=RUN/'stage'

def main():
    assert not RUN.exists(),'Use a fresh run directory; never mix backups.'
    RUN.mkdir()
    for root in (COMBINED,LEGACY):
        shutil.copytree(root,BACKUP/root.name,ignore=shutil.ignore_patterns('.firecrawl'))
        shutil.copytree(BACKUP/root.name,STAGE/root.name)
    for name in ('英语真题_HTM_公开206套.zip','考研英语真题_2000-2026_HTM_44套.zip'):
        shutil.copy2(SOURCES/name,BACKUP/name)
    snapshot=[]
    for p in BACKUP.rglob('*'):
        if p.is_file():snapshot.append({'file':str(p.relative_to(BACKUP)),'sha256':digest(p.read_bytes())})
    write_json(RUN/'backup-manifest.json',snapshot)
    root=STAGE/COMBINED.name
    manifest=json.loads((root/'manifest.json').read_text())
    changed=0;marks=0
    for i,entry in enumerate(manifest['papers'],1):
        target=root/entry['file'];body=target.read_text()
        sections=re.findall(r'<section class="page-wrap".*?</section>',body,re.S)
        assert len(sections)==entry['pages']
        with fitz.open(source_pdf(entry)) as doc:
            assert digest(source_pdf(entry).read_bytes())==entry['source_pdf_sha256']
            for n,page in enumerate(doc,1):
                rects=url_rectangles(page)
                if rects:
                    markup,info=render_page(page,n,target.with_suffix('.assets')/f'page-{n:03}.svg')
                    replacement=f'<section class="page-wrap" data-page="{n}"><div class="page-label">第 {n} / {len(doc)} 页</div><div class="sheet">{markup}</div></section>'
                    body=body.replace(sections[n-1],replacement,1)
                    entry['page_rendering'][n-1]=info
                    changed+=1;marks+=len(rects)
                else:
                    info=entry['page_rendering'][n-1]
                    info['removed_url_rectangles']=[]
                    info['display_text_sha256']=info['text_sha256']
        # Visible page headers/footers are local reading UI; provenance remains in
        # the unchanged source_url/document_url fields in the manifest.
        body=re.sub(r'<a href="https?://[^\"]*burningvocabulary[^\"]*">.*?</a>','',body,flags=re.S)
        body=re.sub(r'<footer>.*?</footer>','<footer>本地试卷 · 原卷排版 · 可离线阅读</footer>',body,flags=re.S)
        body=body.replace(' · </p>','</p>')
        write_reader(target, body)
        entry['renderer']=RENDERER_VERSION
        entry['htm_sha256']=digest(target.read_bytes())
        entry['visible_site_identifier_removed']=True
        if entry['category']=='kaoyan':
            twin=STAGE/LEGACY.name/'papers'/target.name
            shutil.copy2(target,twin)
            shutil.copytree(target.with_suffix('.assets'),twin.with_suffix('.assets'),dirs_exist_ok=True)
        print(f'UPDATED {i}/206 {entry["file"]}',flush=True)
    write_json(root/'manifest.json',manifest)
    legacy_root=STAGE/LEGACY.name
    legacy=json.loads((legacy_root/'manifest.json').read_text())
    lookup={Path(r['file']).name:r for r in manifest['papers'] if r['category']=='kaoyan'}
    for i,r in enumerate(legacy['papers']):
        new=copy.deepcopy(lookup[Path(r['file']).name]);new['file']=r['file'];new['asset_directory']=str(Path(r['file']).with_suffix('.assets'));new.pop('reused_from',None);legacy['papers'][i]=new
    write_json(legacy_root/'manifest.json',legacy)
    write_catalogs(root,manifest)
    write_catalogs(legacy_root,legacy,legacy=True)
    write_json(RUN/'build-result.json',{'papers':206,'pages':2020,'pages_with_identifiers_removed':changed,'url_identifiers_removed':marks,'backup_files':len(snapshot)})
    print('DONE',changed,'pages;',marks,'URL labels removed',flush=True)

if __name__=='__main__':main()
