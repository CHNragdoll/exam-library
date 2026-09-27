"""Reconcile the 2016–2025 addition against the saved 2009–2015 library."""
from pathlib import Path
import hashlib,json
from lxml import html
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 old=json.loads((ROOT/'work/before-cs408-2016-2025/existing-content.json').read_text());preserved=0
 for category,items in old.items():
  p=ROOT/category/'index.htm';tree=html.fromstring(p.read_text())
  actual=[str((p.parent/n.get('href')).resolve()) for n in tree.xpath('//div[@class="versions"]/a')]
  paths=[item['path'] for item in items];oldset=set(paths)
  assert [path for path in actual if path in oldset]==paths,(category,'old links changed')
  if category!='cs408':assert actual==paths,(category,'out of scope addition')
  for item in items:assert sha(Path(item['path']))==item['sha256'],item['path'];preserved+=1
 p=ROOT/'cs408/index.htm';tree=html.fromstring(p.read_text());cards=tree.xpath('//article[@class="paper"]')
 assert len(cards)==17
 for card in cards:
  links=card.xpath('./div[@class="versions"]/a');assert len(links)==2
  stems=[Path(n.get('href')).stem for n in links];assert stems[0]==stems[1]
  year=int(stems[0][:4]);assert stems[0]==f'{year}-'+('complete' if year<2016 else 'questions')
 report=json.loads((ROOT/'verification.json').read_text())
 assert report['paper_cards']==289 and report['version_links']==578
 result={'previous_paper_links_and_hashes_preserved':preserved,'new_years':list(range(2016,2026)),'cs408_years':17,'cs408_version_links':34,'all_library_cards':289,'all_library_version_links':578}
 (ROOT/'work/cs408-2016-2025-preservation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
