#!/usr/bin/env python3
"""Prepare original-PDF / actual fallback-image pairs; does not modify sources."""
from pathlib import Path
import json,re,html,hashlib
import fitz
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.local/fallback-visual-review';OUT.mkdir(parents=True,exist_ok=True)
rows=[r for r in json.loads((ROOT/'docs/source-integrity-triage-final-2026-09-28.json').read_text())['rows'] if r['classification']=='image_fallback_unreviewed']
cache={};result=[]
for index,row in enumerate(rows,1):
 cat,stem=row['documentId'].split(':');pg=int(row['pages'][0]);pdfpath=Path(row['sourcePdf'])
 if str(pdfpath) not in cache:cache[str(pdfpath)]=fitz.open(pdfpath)
 page=cache[str(pdfpath)][pg-1];bi=int(re.search(r'PDF text block (\d+)',row['evidence'])[1])-1
 pdfblock=page.get_text('blocks',sort=True)[bi];box=fitz.Rect(pdfblock[:4]);box+=(-3,-3,3,3);box &= page.rect
 current=ROOT/'data/sources/exam-library/structured/papers'/cat/(stem+'.json');bank=json.loads(current.read_text())
 reflow=(current.parent/bank['source']['reflow']).resolve();sourcejson=reflow.with_suffix('.json')
 rawpage=None
 if sourcejson.exists():
  raw=json.loads(sourcejson.read_text());rawpage=next((p for i,p in enumerate(raw['pages'],1) if int(p.get('source_page',i))==pg),None)
 refs=[]
 for b in bank['blocks']:
  if int(b['sourcePageIndex'])!=pg:continue
  for rel in re.findall(r'<img[^>]*src="([^"]+)"',b['contentHtml']):
   path=(current.parent/html.unescape(rel)).resolve();match=re.search(r'char-\d+-line-(\d+)',path.name)
   bbox=None
   if match and rawpage:
    item=rawpage['blocks'][int(match[1])];bbox=item.get('bbox')
   if bbox and not (fitz.Rect(bbox)&box).is_empty:refs.append({'path':str(path),'bbox':bbox,'blockId':b['id']})
 # actual fallback image only, in original coordinate frame; text not in images remains white at right.
 canvas=fitz.open();cp=canvas.new_page(width=box.width*2+18,height=box.height+28)
 cp.insert_text((4,12),f'{index:03d} {row["documentId"]} p{pg} PDF block {bi+1} | PDF LEFT / actual fallback RIGHT',fontsize=8)
 left=fitz.Rect(0,24,box.width,24+box.height)
 cp.show_pdf_page(left,cache[str(pdfpath)],pg-1,clip=box)
 for ref in refs:
  r=fitz.Rect(ref['bbox']);target=fitz.Rect(r.x0-box.x0+box.width+18,r.y0-box.y0+24,r.x1-box.x0+box.width+18,r.y1-box.y0+24)
  # Large fallback extends beyond target paragraph: crop naturally at canvas edges except header.
  try:
   if ref['path'].endswith('.svg'):
    d=fitz.open(ref['path']);dp=fitz.open('pdf',d.convert_to_pdf());cp.show_pdf_page(target,dp,0)
   else:cp.insert_image(target,filename=ref['path'])
  except Exception as e:ref['render_error']=str(e)
 # Keep native text sizes readable; tall blocks are shown at <=2x.
 scale=min(2.0,1500/(box.width*2+18));proof=OUT/f'{index:03d}.png';cp.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).save(proof)
 text=' '.join(b['text'] for b in bank['blocks'])
 norm=lambda s:''.join(c.lower() for c in s if c.isalnum())
 selectable=norm(text); uncovered=[]
 for b in page.get_text('dict')['blocks']:
  for line in b.get('lines',[]):
   for s in line.get('spans',[]):
    r=fitz.Rect(s['bbox']);inter=r&box
    if inter.is_empty or inter.get_area()<r.get_area()*.75:continue
    inimage=any((r&fitz.Rect(z['bbox'])).get_area()>=r.get_area()*.90 for z in refs)
    n=norm(s['text'])
    if not inimage and len(n)>=8 and n not in selectable:uncovered.append(s['text'])
 result.append({**row,'reviewId':index,'pdfBlockIndex':bi+1,'pdfBlockBBox':list(box),'pdfText':pdfblock[4],
  'currentReflow':str(reflow),'currentReflowSHA':hashlib.sha256(reflow.read_bytes()).hexdigest(),
  'fallbackImages':refs,'not_accounted_for_text_spans':uncovered,'proof':str(proof),'visualConclusion':'pending'})
(OUT/'prepared.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('Prepared',len(result),'rows; with images',sum(bool(r['fallbackImages']) for r in result),'unaccounted spans',sum(bool(r['not_accounted_for_text_spans']) for r in result))
