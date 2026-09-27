from pathlib import Path
import fitz,json,hashlib
from lxml import html
from clean_source import cleaned_document,omitted_pages,normalize,AD,HEADER
ROOT=Path(__file__).resolve().parent
fitz.TOOLS.mupdf_display_errors(False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((ROOT/'manifest.json').read_text());count=0;redactions=0;checks=[];omissions=0;native_images=0
for spec in m['documents']:
 path=Path(spec['path']);assert sha(path)==spec['sha256'];raw=fitz.open(path);clean,removed=cleaned_document(path)
 omitted=omitted_pages(path);by_page={}
 for r in removed:by_page.setdefault(r['page'],[]).append(r)
 assert len(raw)==len(clean)==spec['pages']
 for i,(a,b) in enumerate(zip(raw,clean),1):
  asset=ROOT/'papers'/f'{spec["id"]}.assets'/f'page-{i:03}.svg'
  if i in omitted:
   assert not asset.exists(),(spec['id'],i,'advert page remains accessible')
   omissions+=1;continue
  a.get_text();a.get_svg_image(text_as_path=True)
  assert asset.read_text()==b.get_svg_image(text_as_path=True)
  assert not any(t in normalize(b.get_text()) for t in (AD,HEADER))
  pa=a.get_pixmap();pb=b.get_pixmap();assert (pa.width,pa.height,pa.n)==(pb.width,pb.height,pb.n)
  aa=pa.samples;bb=pb.samples;regions=by_page.get(i,[])
  if regions:
   allowed=[((fitz.Rect(r['bbox'])*a.rotation_matrix)+(-2,-2,2,2)).irect & fitz.IRect(0,0,pa.width,pa.height) for r in regions]
   assert aa!=bb,(spec['id'],i,'advert not removed')
   stride=pa.stride
   for row in range(pa.height):
    start=row*stride;end=start+stride;spans=sorted((r.x0,r.x1) for r in allowed if r.y0<=row<r.y1)
    cursor=0
    for x0,x1 in spans:
     assert aa[start+cursor*pa.n:start+x0*pa.n]==bb[start+cursor*pa.n:start+x0*pa.n],(spec['id'],i,row,'outside advert changed')
     cursor=max(cursor,x1)
    assert aa[start+cursor*pa.n:end]==bb[start+cursor*pa.n:end],(spec['id'],i,row,'outside advert changed')
   redactions+=len(regions)
   native_images+=sum(r['kind']=='image' for r in regions)
  else:assert aa==bb,(spec['id'],i,'unexpected image modification')
  count+=1
 tree=html.fromstring((ROOT/spec['file']).read_text())
 assert len(tree.xpath('//section[@class="page-wrap"]'))==len(raw)-len(omitted)==spec['displayed_pages']
 checks.append({'id':spec['id'],'source_pages':len(raw),'displayed_pages':len(raw)-len(omitted),'omitted_advert_pages':omitted,'sha256':spec['sha256'],'removed_advert_regions':sum(r['kind']!='whole_page' for r in removed)})
 print(spec['id'],'PASS',flush=True)
assert count+omissions==292
assert next(s for s in checks if s['id']=='2019-answers')['omitted_advert_pages']==[7]
out={'documents':len(checks),'source_pages':count+omissions,'displayed_pages':count,'omitted_advert_pages':omissions,'removed_advert_regions':redactions,'removed_qr_images':native_images,'original_pdfs_unchanged':True,'all_svg_match_native_cleaned_pdf':True,'all_pixel_changes_within_advert_bounds':True,'2019_page_6_preserved':True,'browser_tested':False,'checks':checks}
(ROOT/'verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(count,redactions,omissions)
