"""Remove identified advertising from an in-memory reading copy; raw PDFs stay intact."""
from pathlib import Path
import fitz,re,json
ROOT=Path(__file__).resolve().parent
AD='公众号【研池大叔】，免费分享考研干货！'
HEADER='微信公众号【酱子考研】后台发送【PDF】获取更多考研资料'
def normalize(text):return re.sub(r'\s+','',text)
def document_id(path):
 specs=json.loads((ROOT/'sources.json').read_text())
 return next(s['id'] for s in specs if Path(s['path'])==Path(path))
def omitted_pages(path):
 return json.loads((ROOT/'advert_regions.json').read_text())['omitted_pages'].get(document_id(path),[])
def cleaned_document(path):
 doc=fitz.open(path);records=[];ident=document_id(path)
 rules=json.loads((ROOT/'advert_regions.json').read_text())
 for i,page in enumerate(doc,1):
  if i in rules['omitted_pages'].get(ident,[]):
   records.append({'page':i,'kind':'whole_page','bbox':list(page.rect),'reason':'QR promotions, paid printing and practice-platform advertisement only; visually checked'})
   continue
  before=normalize(page.get_text());expected=before;regions=[]
  for b in page.get_text('blocks'):
   normalized=normalize(b[4])
   if normalized in (AD,HEADER):
    rect=fitz.Rect(b[:4]);assert rect.y1<30 or rect.y0>page.rect.height-25,(ident,i,'margin advert overlaps body',rect)
    regions.append({'page':i,'kind':'text','removed_text':normalized,'bbox':list(rect)})
    expected=expected.replace(normalized,'')
  for rule in rules['image_regions']:
   if rule['id']==ident and rule['page']==i:
    rect=fitz.Rect(rule['bbox'])
    assert any((r-rect).norm()<.01 for r in page.get_image_rects(rule['xref'])),(ident,i,'source image moved')
    regions.append({'page':i,'kind':'image','xref':rule['xref'],'bbox':list(rect),'reason':rule['reason']})
  # Header text redactions never touch vectors or images.
  for region in regions:
   if region['kind']=='text':page.add_redact_annot(fitz.Rect(region['bbox']),fill=(1,1,1),cross_out=False)
  if any(r['kind']=='text' for r in regions):page.apply_redactions(images=0,graphics=0,text=0)
  assert normalize(page.get_text())==expected,(ident,i,'nonadvert text changed')
  # Remove the independent QR image object directly. Unlike redacting all page
  # content, this leaves compressed source glyph streams and antialiasing untouched.
  for region in regions:
   if region['kind']=='image':page.delete_image(region['xref'])
  assert normalize(page.get_text())==expected,(ident,i,'QR cleaning changed source text')
  records.extend(regions)
 return doc,records
