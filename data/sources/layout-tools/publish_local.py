"""Install the verified local archive and ZIPs; no Git/network/Anki changes."""
import json
import os
import shutil
import zipfile
from pathlib import Path
from archive_renderer import digest
from repair_archive import STAGE, SOURCES, COMBINED, LEGACY, BACKUP, write_json

INSTALL_RECORD='layout-repair-install.json'

def main():
    report=json.loads((STAGE/COMBINED.name/'verification.json').read_text())
    assert report['papers']==206 and report['pages']==2020
    assert report.get('manual_raster_review_completed') is True
    assert not any(v['requires_manual_raster_review'] and not v.get('reviewed') for v in report['visual_checks'])
    install=[];packages=[]
    for root,zipname in [(COMBINED,'英语真题_HTM_公开206套.zip'),(LEGACY,'考研英语真题_2000-2026_HTM_44套.zip')]:
        staged=STAGE/root.name
        manifest=json.loads((staged/'manifest.json').read_text())
        include=[staged/'index.htm',staged/'README.md',staged/'manifest.json',staged/'verification.json',staged/'LAYOUT_REPAIR.md']
        include+=list(staged.glob('*/index.htm'))
        for r in manifest['papers']:
            f=staged/r['file'];include.append(f)
            assert digest(f.read_bytes())==r['htm_sha256']
            for n,meta in enumerate(r['page_rendering'],1):
                asset=f.with_suffix('.assets')/f'page-{n:03}.svg'
                assert digest(asset.read_bytes())==meta['svg_sha256']
                include.append(asset)
        include+=list((staged/'assets/layout-repair').glob('*.png'))
        if (staged/'VISUAL_CATALOG.md').is_file():include.append(staged/'VISUAL_CATALOG.md')
        include+=list((staged/'assets/visual-catalog').glob('*.png'))
        archive=STAGE/zipname
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for f in include:
                z.write(f,str(Path(root.name)/f.relative_to(staged)))
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            assert len(z.namelist())==len(include)==len(set(z.namelist()))
            for r in manifest['papers']:
                member=str(Path(root.name)/r['file'])
                assert digest(z.read(member))==r['htm_sha256']
        packages.append({'file':zipname,'sha256':digest(archive.read_bytes()),'bytes':archive.stat().st_size,'members':len(include)})
        for f in staged.rglob('*'):
            if f.is_file(): install.append((f,root/f.relative_to(staged)))
        install.append((archive,SOURCES/zipname))
    # Protect edits made while rendering: every existing destination must still
    # equal the backed-up baseline, or the exact candidate in an idempotent retry.
    for source,target in install:
        if target.exists():
            prior=BACKUP/target.relative_to(SOURCES)
            assert target.read_bytes()==source.read_bytes() or (prior.is_file() and target.read_bytes()==prior.read_bytes()),f'File changed during repair: {target}'
    completed=[];created=[]
    try:
        for source,target in install:
            if target.exists() and target.read_bytes()==source.read_bytes():continue
            existed=target.exists()
            target.parent.mkdir(parents=True,exist_ok=True)
            temp=target.with_name(target.name+'.layout-tmp')
            shutil.copy2(source,temp);os.replace(temp,target)
            relative=str(target.relative_to(SOURCES))
            completed.append(relative)
            if not existed:created.append(relative)
        for p in packages:assert digest((SOURCES/p['file']).read_bytes())==p['sha256']
        # Validate installed bytes for every paper, image and navigation/report.
        for source,target in install:assert digest(source.read_bytes())==digest(target.read_bytes()),target
    except BaseException:
        rollback_errors=[]
        for relative in reversed(completed):
            target=SOURCES/relative
            try:
                if relative in created:target.unlink(missing_ok=True)
                else:
                    prior=BACKUP/relative
                    assert prior.is_file()
                    shutil.copy2(prior,target)
                    assert digest(target.read_bytes())==digest(prior.read_bytes())
            except Exception as error:rollback_errors.append({'file':relative,'error':str(error)})
        write_json(STAGE/'install-partial.json',{'installed':completed,'backup':str(BACKUP),'rollback_errors':rollback_errors,'rollback_completed':not rollback_errors})
        raise
    write_json(SOURCES/INSTALL_RECORD,{'files':len(install),'packages':packages,'backup':str(BACKUP),'staging':str(STAGE),'installed_byte_comparison':True})
    print(json.dumps({'installed_files':len(install),'packages':packages},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
