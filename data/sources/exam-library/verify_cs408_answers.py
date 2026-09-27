"""Reconcile answer additions against the preserved 578 existing version files."""
from pathlib import Path
import hashlib,json
from lxml import html
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 old=json.loads((ROOT/'work/before-cs408-answers/existing-content.json').read_text());preserved=0
 for category,items in old.items():
  p=ROOT/category/'index.htm';tree=html.fromstring(p.read_text());actual=[str((p.parent/a.get('href')).resolve()) for a in tree.xpath('//div[@class="versions"]/a')]
  paths=[item['path'] for item in items];oldset=set(paths);assert [p for p in actual if p in oldset]==paths,category
  if category!='cs408':assert actual==paths,category
  for item in items:assert sha(Path(item['path']))==item['sha256'],item['path'];preserved+=1
 p=ROOT/'cs408/index.htm';tree=html.fromstring(p.read_text());cards=tree.xpath('//article[@class="paper"]');assert len(cards)==27
 for card in cards:
  links=card.xpath('./div[@class="versions"]/a');assert len(links)==2
  stems=[Path(a.get('href')).stem for a in links];assert stems[0]==stems[1]
 for year in range(2016,2026):
  section=tree.xpath('//section[@id=$id]',id=f'year-{year}')[0]
  stems=[Path(a.get('href')).stem for a in section.xpath('.//div[@class="versions"]/a[1]')]
  assert stems==[f'{year}-questions',f'{year}-answers'],(year,stems)
 p=ROOT/'politics/index.htm';tree=html.fromstring(p.read_text());cards=tree.xpath('//article[@class="paper"]');assert len(cards)==36
 for year in range(2003,2024):
  section=tree.xpath('//section[@id=$id]',id=f'year-{year}')[0]
  stems=[Path(a.get('href')).stem for a in section.xpath('.//div[@class="versions"]/a[1]')]
  assert stems==[f'{year}-questions']+([f'{year}-answers'] if year>=2009 else []),(year,stems)
 report=json.loads((ROOT/'verification.json').read_text());assert report['paper_cards']==335 and report['version_links']==670
 result={'previous_paper_links_and_hashes_preserved':preserved,'new_answer_years':list(range(2016,2026)),'cs408_documents':27,'cs408_version_links':54,'politics_documents':36,'politics_version_links':72,'all_library_cards':335,'all_library_version_links':670}
 (ROOT/'work/cs408-answers-preservation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
