"""Package only current output and referenced assets, excluding intermediate trials."""
from pathlib import Path
import json,re,zipfile
from lxml import html
ROOT=Path(__file__).resolve().parent
m=json.loads((ROOT/'manifest.json').read_text())
files={p for p in ROOT.iterdir() if p.suffix in ('.py','.css','.htm','.json','.md')}
files.update((ROOT/'tools').glob('*.py'));files.update((ROOT/'assets/verification').glob('*.png'))
for entry in m['papers']:
    p=ROOT/entry['file'];files.update([p,p.with_suffix('.tex'),p.with_suffix('.json'),p.parent.parent/'index.htm'])
    tree=html.fromstring(p.read_text())
    files.update((p.parent/s).resolve() for s in tree.xpath('//@src'))
    files.update((p.parent/s).resolve() for s in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}',p.with_suffix('.tex').read_text()))
assert all(p.is_file() for p in files)
# Only remove obsolete generated figure/character assets from this new output.
for p in ROOT.glob('*/papers/*.assets/*'):
    if p.is_file() and p.name.startswith(('char-','figure-')) and p.resolve() not in files:p.unlink()
out=ROOT.parent/'英语真题_公开206套_LaTeX及重排HTM.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(files):z.write(p,ROOT.name+'/'+str(p.relative_to(ROOT)))
print(out, len(files), out.stat().st_size)
