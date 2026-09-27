"""Verify original page fidelity, input immutability and working offline links."""
from pathlib import Path
import hashlib,json
import fitz,sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'layout-tools'))
from other_ad_cleaner import clean_document
from lxml import html
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 m=json.loads((ROOT/'manifest.json').read_text())
 specs=json.loads((ROOT/'sources.json').read_text())
 assert {d['id'] for d in m['documents']}=={s['id'] for s in specs}
 assert {d['year'] for d in m['documents']}==set(range(2009,2026))
 pages=links=0
 for d in m['documents']:
  source=Path(d['path']);assert sha(source)==d['sha256']
  pdf=fitz.open(source);assert len(pdf)==d['pages']
  assert clean_document(pdf,'cs408',d['id'])==d.get('removed_adverts',[])
  htm=ROOT/d['file'];assert sha(htm)==d['htm_sha256']
  for page,rec in zip(pdf,d['page_rendering'],strict=True):
   asset=htm.with_suffix('.assets')/f'page-{rec["page"]:03}.svg'
   assert sha(asset)==rec['sha256']
   assert asset.read_bytes()==page.get_svg_image(text_as_path=True).encode()
   pages+=1
 for p in [ROOT/'index.htm',*(ROOT/'papers').glob('*.htm')]:
  doc=html.fromstring(p.read_text(),parser=html.HTMLParser(huge_tree=True))
  for url in doc.xpath('//@href|//img/@src|//object/@data'):
   if url.startswith('#'):
    assert doc.xpath('//*[@id=$id]',id=url[1:]);continue
   assert not url.startswith(('http:','https:','//'))
   assert (p.parent/url).is_file(),(p,url);links+=1
 assert pages==m['source_pages']==sum(s['pages'] for s in specs)==333
 report={'documents':len(m['documents']),'pages':pages,'source_hashes_unchanged':True,'all_svg_match_cleaned_native_pdf_render':True,'removed_advert_regions':sum(len(x['rectangles']) for d in m['documents'] for x in d.get('removed_adverts',[])),'local_links_checked':links,'browser_tested':False}
 (ROOT/'verification.json').write_text(json.dumps(report,indent=2))
 print(json.dumps(report))
if __name__=='__main__':main()
