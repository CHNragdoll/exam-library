"""Validate source coverage, offline links, SVG formulas and complete TeX documents."""
from pathlib import Path
import json,re,subprocess,concurrent.futures,hashlib,argparse
from lxml import etree,html
import fitz
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--partial',action='store_true');args=ap.parse_args()
 manifest=json.loads((ROOT/'manifest.json').read_text());mapping=json.loads((ROOT/'work/page-map.json').read_text());years=manifest['years']
 if not args.partial:assert years==list(range(2008,1986,-1))
 pages=[];blocks=0
 for year in years:
  source=json.loads((ROOT/f'source/{year}.json').read_text());seen=[p['source_page'] for p in source['pages']]
  assert sha(ROOT/f'source/{year}.json')==manifest['source_hashes'][str(year)],f'{year}: source changed after build'
  assert seen==mapping[str(year)]['questions']+mapping[str(year)]['answers'];pages+=seen
  for p in source['pages']:
   assert p['blocks'];blocks+=len(p['blocks'])
   for b in p['blocks']:
    assert b['type'] in ['heading','paragraph','display','figure']
    if b['type']=='figure':assert b.get('caption') and len(b['bbox'])==4
 assert len(pages)==len(set(pages))
 if not args.partial:assert len(pages)==126
 formulas=json.loads((ROOT/'work/rendered.json').read_text())
 for f in formulas:
  assert f['tex'].startswith(r'\displaystyle ')
  tree=etree.fromstring(f['markup'].encode());assert not tree.xpath('.//*[@data-mml-node="merror"]|.//*[local-name()="image" or local-name()="script"]')
 links=0
 for e in manifest['documents']:
  p=ROOT/e['htm'];assert sha(p)==e['sha256'];t=html.fromstring(p.read_text(),parser=html.HTMLParser(huge_tree=True))
  assert len(t.xpath('//section[@data-source-page]'))==len(e['source_pages'])
  for url in t.xpath('//@href|//img/@src|//script/@src'):
   if url.startswith('#'):continue
   assert not url.startswith(('https:','http:','//'))
   assert (p.parent/url).exists(),(p,url);links+=1
 out=ROOT/'work/tex-check';out.mkdir(exist_ok=True,parents=True)
 def compile(e):
  p=ROOT/e['tex'];r=subprocess.run(['/Library/TeX/texbin/xelatex','-interaction=nonstopmode','-halt-on-error',f'-output-directory={out}',p.name],cwd=ROOT/'tex',capture_output=True,text=True,timeout=120)
  log=r.stdout+r.stderr
  return {'file':p.name,'sha256':sha(p),'passed':r.returncode==0,'warnings':[line for line in log.splitlines() if 'Overfull' in line or 'Missing character' in line],'error_tail':log[-1800:] if r.returncode else ''}
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(compile,manifest['documents']))
 (ROOT/'assets/verification/latex-compilation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
 report={'years':len(years),'source_pages_covered_once':len(pages),'blocks':blocks,'tex_documents_compiled':sum(r['passed'] for r in results),'tex_compile_errors':sum(not r['passed'] for r in results),'warning_documents':sum(bool(r['warnings']) for r in results),'formula_svg_count':len(formulas),'formula_errors':0,'local_links_checked':links,'browser_tested':False,'source_hashes':{str(y):sha(ROOT/f'source/{y}.json') for y in years}}
 (ROOT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
 assert all(r['passed'] and not r['warnings'] for r in results),[r for r in results if not r['passed'] or r['warnings']]
 for year in [y for y in [1987,1996,2001,2008] if y in years]:
  for kind in ['questions','answers']:
   d=fitz.open(out/f'{year}-{kind}.pdf');d[0].get_pixmap(dpi=120).save(ROOT/f'assets/verification/tex-{year}-{kind}.png')
if __name__=='__main__':main()
