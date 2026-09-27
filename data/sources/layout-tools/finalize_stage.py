"""One-time refinement of the initial staged batch: lazy per-page assets."""
import base64
import json
import re
import shutil
from pathlib import Path
from lxml import html
from archive_renderer import STYLE, digest
from repair_archive import STAGE, COMBINED, LEGACY, write_json

root=STAGE/COMBINED.name
manifest=json.loads((root/'manifest.json').read_text())
for entry in manifest['papers']:
    f=root/entry['file'];body=f.read_text();number=[0]
    def move_image(match):
        number[0]+=1
        target=f.with_suffix('.assets')/f'page-{number[0]:03}.svg'
        target.parent.mkdir(exist_ok=True)
        svg=base64.b64decode(match.group(1),validate=True)
        assert digest(svg)==entry['page_rendering'][number[0]-1]['svg_sha256']
        target.write_bytes(svg)
        return 'src="'+target.parent.name+'/'+target.name+'"'
    if 'src="data:image/svg+xml;base64,' in body:
        body=re.sub(r'src="data:image/svg\+xml;base64,([^"]+)"',move_image,body)
        assert number[0]==entry['pages']
    if 'class="sr-only"' not in body:
        def accessible(match):
            block=match.group(0)
            text=re.search(r'<pre class="source-text">(.*?)</pre>',block,re.S).group(1)
            return '<div class="sr-only" aria-label="本页文字">'+text+'</div>'+block
        body=re.sub(r'<details class="page-text">.*?</details>',accessible,body,flags=re.S)
    body=re.sub(r'<style>.*?</style>',lambda _: '<style>'+STYLE+'</style>',body,count=1,flags=re.S)
    body=body.replace('点击每页下方“查看 / 复制本页文字”提取文字；','点击每页下方“查看 / 复制本页文字”提取文字或查找整句；')
    body=body.replace('不含听力音频及网站付费解析。</p>','不含听力音频及网站付费解析。请保留同目录的 .assets 素材文件夹。</p>')
    f.write_text(body)
    entry['htm_sha256']=digest(f.read_bytes())
    entry['asset_directory']=str(f.with_suffix('.assets').relative_to(root))
    entry['offline_images']=True
    entry['asset_layout']='local SVG files, internally self-contained; lazy-loaded per page'
    if entry['category']=='kaoyan':
        legacy=STAGE/LEGACY.name/'papers'/f.name
        shutil.copy2(f,legacy)
        shutil.copytree(f.with_suffix('.assets'),legacy.with_suffix('.assets'),dirs_exist_ok=True)
write_json(root/'manifest.json',manifest)
legacy_root=STAGE/LEGACY.name
legacy=json.loads((legacy_root/'manifest.json').read_text())
by_name={Path(r['file']).name:r for r in manifest['papers'] if r['category']=='kaoyan'}
for i,r in enumerate(legacy['papers']):
    updated=dict(by_name[Path(r['file']).name],file=r['file'],asset_directory=str(Path(r['file']).with_suffix('.assets')))
    updated.pop('reused_from',None);legacy['papers'][i]=updated
write_json(legacy_root/'manifest.json',legacy)
for archive in (root,legacy_root):
    for f in archive.rglob('index.htm'):
        s=f.read_text().replace('各试卷为自包含 HTM，文字可选择、搜索，图片和图形内嵌。','各试卷采用 HTM + 配套 .assets 素材文件夹；原卷排版按页加载，可展开文字复制。')
        s=s.replace('各页文字和图表均已内嵌，无需联网或打开 PDF。','各页配有本地 SVG 素材，无需联网或打开 PDF。请保留配套 .assets 文件夹。')
        f.write_text(s)
    readme=archive/'README.md'
    s=readme.read_text().replace('自包含','离线').replace('图片及矢量图形内嵌。','图片和字形保存在配套 .assets 文件夹。')
    s+='\n阅读时请保留 HTM 旁边同名 .assets 文件夹。原始 SVG 内部资源自包含，无联网依赖；按页加载避免大卷单个 HTML 过大。查找完整句子请先展开本页文字。透明选择层为便捷操作，源编码异常页仍需核对；移动端性能和浏览器交互未完成本轮实测。\n'
    readme.write_text(s)
print('REFINED 206 papers; local page assets; accessible text')
