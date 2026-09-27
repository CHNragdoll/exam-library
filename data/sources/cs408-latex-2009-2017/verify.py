"""Check complete source coverage, editable math, TeX compilation and offline links."""
from pathlib import Path
import argparse,collections,concurrent.futures,hashlib,json,re,subprocess
import fitz
from lxml import html,etree
from build import split_choices
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--partial',action='store_true');args=ap.parse_args()
 m=json.loads((ROOT/'manifest.json').read_text());sources=json.loads((ROOT/'sources.json').read_text());spec={s['id']:s for s in sources}
 if not args.partial:assert {e['id'] for e in m['documents']}==set(spec)
 blocks=0;codes=0;tables=0;displays=0;figures=0;question_coverage={};choice_groups=0
 for y,digest in m['source_hashes'].items():
  p=ROOT/f'source/{y}.json';assert sha(p)==digest,(y,'changed after build');s=json.loads(p.read_text())
  expected=[(x['id'],n) for x in sources if x['year']==int(y) for n in range(1,x['pages']+1)]
  assert [(p['source_id'],p['source_page']) for p in s['pages']]==expected
  if int(y)>=2016:
   numbers=[]
   for page in s['pages']:
    for b in page['blocks']:
     if b['type']=='paragraph':
      result=split_choices(b['text'])
      if result:
       prefix,options,_=result
       restored=prefix+''.join(label+'.'+value for label,value in options)
       normalize=lambda text:re.sub(r'\s','',text).replace('．','.')
       assert normalize(restored)==normalize(b['text']),(y,'option text changed')
       choice_groups+=1
      if int(y) in [2020,2023] and re.match(r'^(21[.]|22[．])',b['text']):
       assert result and result[1][0][0]=='A',(y,'cross-page A option')
     if b['type'] in ['paragraph','heading']:
      match=re.match(r'^\s*(\d{1,2})[.．、]',b.get('text',''))
      if match:numbers.append(int(match[1]))
   counts=collections.Counter(numbers)
   assert counts==collections.Counter(range(1,48)),(y,'question coverage',dict(counts))
   question_coverage[y]={'first':1,'last':47,'count':47,'duplicates':[]}
   assert all(spec[sid]['kind']=='questions' for sid in {p['source_id'] for p in s['pages']})
  for p in s['pages']:
   for b in p['blocks']:
    blocks+=1;codes+=b['type']=='code';tables+=b['type']=='table';displays+=b['type']=='display';figures+=b['type']=='figure'
    if b['type']=='figure':assert not any(t in b.get('caption','') for t in ['矩阵照片','公式截图','整页']),b
 links=0
 for e in m['documents']:
  p=ROOT/e['htm'];assert sha(p)==e['htm_sha256'];assert sha(ROOT/e['tex'])==e['tex_sha256']
  t=html.fromstring(p.read_text(),parser=html.HTMLParser(huge_tree=True))
  assert len(t.xpath('//section[@data-source-page]'))==e['pages']
  for url in t.xpath('//@href|//img/@src|//script/@src'):
   if url.startswith('#'):assert t.xpath('//*[@id=$id]',id=url[1:]);continue
   assert not url.startswith(('https:','http:','//'))
   if args.partial and url=='../../exam-library/cs408/index.htm' and not (p.parent/url).is_file():continue
   assert (p.parent/url).is_file(),(p,url);links+=1
  assert not t.xpath('//*[@data-mml-node="merror"]')
 fs=json.loads((ROOT/'work/rendered.json').read_text());assert len(fs)==m['formulas']
 for f in fs:
  assert not f.get('error') and f['tex'].startswith(r'\displaystyle ')
  t=etree.fromstring(f['markup'].encode());assert not t.xpath('.//*[local-name()="image" or local-name()="script"]')
 if '2015' in m['source_hashes']:
  source=json.loads((ROOT/'source/2015.json').read_text())
  matrices=[b['tex'] for p in source['pages'] if p['source_page']==10 for b in p['blocks'] if b['type']=='display' and r'\begin{bmatrix}' in b['tex']]
  assert len(matrices)==2
  values=[[[int(c) for c in row.split('&')] for row in t.split(r'\begin{bmatrix}')[1].split(r'\end{bmatrix}')[0].split(r'\\')] for t in matrices]
  a,a2=values
  assert a==[[0,1,1,0,1],[1,0,0,1,1],[1,0,0,1,0],[0,1,1,0,1],[1,1,0,1,0]]
  assert a2==[[sum(a[i][k]*a[k][j] for k in range(5)) for j in range(5)] for i in range(5)]
  relevant=[f for f in fs if f['original_tex'] in matrices]
  assert len(relevant)==2 and all('data-mml-node="mtable"' in f['markup'] for f in relevant)
 out=ROOT/'work/tex-check';out.mkdir(exist_ok=True)
 def compile(e):
  p=ROOT/e['tex'];r=subprocess.run(['/Library/TeX/texbin/xelatex','-interaction=nonstopmode','-halt-on-error',f'-output-directory={out}',p.name],cwd=ROOT/'tex',capture_output=True,text=True,timeout=180)
  log=r.stdout+r.stderr
  return {'file':p.name,'sha256':sha(p),'passed':r.returncode==0,'warnings':[l for l in log.splitlines() if 'Overfull' in l or 'Missing character' in l],'error_tail':log[-2400:] if r.returncode else ''}
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(compile,m['documents']))
 (ROOT/'assets/verification/latex-compilation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
 report={'documents':len(m['documents']),'pages':m['source_pages'],'blocks':blocks,'code_blocks':codes,'tables':tables,'display_formulas':displays,'formulas':len(fs),'figures':figures,'local_links_checked':links,'tex_documents_compiled':sum(r['passed'] for r in results),'warning_documents':sum(bool(r['warnings']) for r in results),'source_hashes':m['source_hashes'],'lossless_choice_groups':choice_groups,'new_question_coverage':question_coverage,'browser_tested':False}
 (ROOT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
 assert all(r['passed'] and not r['warnings'] for r in results),[r for r in results if not r['passed'] or r['warnings']]
 for sid in ['2009-complete','2012-complete','2015-complete']:
  p=out/f'{sid}.pdf'
  if p.exists():
   d=fitz.open(p);d[0].get_pixmap(dpi=115).save(ROOT/f'assets/verification/tex-{sid}.png')
if __name__=='__main__':main()
