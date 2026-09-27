"""Check answer-source coverage, editable math, current TeX, and offline links."""
from pathlib import Path
import argparse,concurrent.futures,hashlib,json,re,subprocess
import fitz
from lxml import html,etree
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--partial',action='store_true');args=ap.parse_args()
 m=json.loads((ROOT/'manifest.json').read_text());specs=json.loads((ROOT/'sources.json').read_text());byid={s['id']:s for s in specs}
 if not args.partial:assert {e['id'] for e in m['documents']}==set(byid)
 independent=json.loads((ROOT/'work/independent-answer-key-check.json').read_text())['keys']
 counts=dict(blocks=0,code_blocks=0,tables=0,display_formulas=0,figures=0);coverage={}
 for year,digest in m['source_hashes'].items():
  path=ROOT/f'source/{year}.json';assert sha(path)==digest,(year,'changed after build');source=json.loads(path.read_text());sid=f'{year}-answers';spec=byid[sid]
  assert sha(Path(spec['path']))==spec['sha256']
  assert [(p['source_id'],p['source_page']) for p in source['pages']]==[(sid,i) for i in range(1,spec['pages']+1)]
  key=source['answer_key'];assert set(key)=={str(i) for i in range(1,41)},year
  assert all(v in ['A','B','C','D'] for v in key.values()),year
  assert key==independent[year],(year,'independent answer-key mismatch',[(q,key[q],independent[year].get(q)) for q in key if key[q]!=independent[year].get(q)])
  assert sorted(source['covered_questions'])==list(range(1,48)),year
  coverage[year]={'answer_key_count':40,'covered_questions':source['covered_questions'],'original_pages':spec['pages']}
  for page in source['pages']:
   for block in page['blocks']:
    counts['blocks']+=1
    countkey={'code':'code_blocks','table':'tables','display':'display_formulas','figure':'figures'}.get(block['type'])
    if countkey:counts[countkey]+=1
    if block['type']=='figure':assert not any(x in block.get('caption','') for x in ['公式截图','矩阵照片','整页']),block
 links=0
 for entry in m['documents']:
  p=ROOT/entry['htm'];assert sha(p)==entry['htm_sha256'];assert sha(ROOT/entry['tex'])==entry['tex_sha256']
  t=html.fromstring(p.read_text(),parser=html.HTMLParser(huge_tree=True));assert len(t.xpath('//section[@data-source-page]'))==entry['pages']
  assert not t.xpath('//*[@data-mml-node="merror"]')
  for url in t.xpath('//@href|//img/@src|//script/@src'):
   if url.startswith('#'):assert t.xpath('//*[@id=$id]',id=url[1:]);continue
   assert not url.startswith(('http:','https:','//'))
   assert (p.parent/url).is_file(),(p,url);links+=1
 formulas=json.loads((ROOT/'work/rendered.json').read_text());assert len(formulas)==m['formulas']
 for item in formulas:
  assert not item.get('error') and item['tex'].startswith(r'\displaystyle ')
  tree=etree.fromstring(item['markup'].encode());assert not tree.xpath('.//*[local-name()="image" or local-name()="script"]')
 out=ROOT/'work/tex-check';out.mkdir(exist_ok=True)
 def compile(entry):
  p=ROOT/entry['tex'];r=subprocess.run(['/Library/TeX/texbin/xelatex','-interaction=nonstopmode','-halt-on-error',f'-output-directory={out}',p.name],cwd=ROOT/'tex',capture_output=True,text=True,timeout=180)
  log=r.stdout+r.stderr
  dependencies={name:sha((p.parent/name).resolve()) for name in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}',p.read_text())}
  return {'file':p.name,'sha256':sha(p),'dependencies':dependencies,'passed':r.returncode==0,'warnings':[l for l in log.splitlines() if 'Overfull' in l or 'Missing character' in l],'error_tail':log[-2400:] if r.returncode else ''}
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(compile,m['documents']))
 (ROOT/'assets/verification/latex-compilation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
 report={'documents':len(m['documents']),'pages':m['source_pages'],**counts,'formulas':len(formulas),'local_links_checked':links,'tex_documents_compiled':sum(r['passed'] for r in results),'warning_documents':sum(bool(r['warnings']) for r in results),'source_hashes':m['source_hashes'],'answer_coverage':coverage,'browser_tested':False}
 (ROOT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
 m['tex_compilation_verified']=len(results)==len(specs) and all(r['passed'] and not r['warnings'] for r in results)
 (ROOT/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
 assert all(r['passed'] and not r['warnings'] for r in results),[r for r in results if not r['passed'] or r['warnings']]
 for e in m['documents']:
  pdf=fitz.open(out/f'{e["id"]}.pdf');pdf[0].get_pixmap(dpi=115).save(ROOT/f'assets/verification/{e["id"]}-first.png')
if __name__=='__main__':main()
