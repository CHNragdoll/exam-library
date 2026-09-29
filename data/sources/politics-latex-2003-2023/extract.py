"""Lossless text-layer import: remove only page furniture; rebuild flowing paragraphs."""
from pathlib import Path
import json,re,sys,fitz
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'politics-original'))
from clean_source import cleaned_document
from page_furniture import is_page_footer_line
HEAD=re.compile(r'^(?:[一二三四五六七八九十]+[、．.]|\d{4}\s*年.*(?:考试|试题|政治)|材料\s*[一二三四五六七八九十\d]+|选做题\s*[ⅠⅡI]+|[（(][一二三四五六七八九十]+[)）])')
QUESTION=re.compile(r'^\d{1,2}\s*[．.、]')
OPTION=re.compile(r'^[ABCDE]\s*[．.、]')
SUBQ=re.compile(r'^(?:[（(]\d+[)）]|[①②③④⑤⑥⑦⑧⑨⑩])')
def norm(t):return re.sub(r'\s+','',t)
def join(a,b):
 if a and b and a[-1].isascii() and b[0].isascii() and a[-1].isalnum() and b[0].isalnum():return a+' '+b
 return a+b

def import_spec(spec):
 pdf,removed=cleaned_document(spec['path']);pages=[];source_text=[];discard=[];images=[];allblocks=[];qnums=[]
 for pi,page in enumerate(pdf,1):
  events=[];table_rects=[]
  for table in page.find_tables().tables:
   rows=table.extract()
   if len(rows)<2 or len(rows[0])<2:continue
   rows=[[c or '' for c in row] for row in rows]
   rect=fitz.Rect(table.bbox);table_rects.append(rect)
   events.append((rect.y0,rect.x0,{'type':'table','rows':rows}))
  for block in page.get_text('dict')['blocks']:
   if block['type']==1:
    rect=fitz.Rect(block['bbox'])
    if rect.get_area()>page.rect.get_area()*.8:raise ValueError('scanned page in text-layer batch')
    events.append((rect.y0,rect.x0,{'type':'figure','bbox':list(rect),'caption':''}));images.append([pi,list(rect)])
   else:
    for line in block['lines']:
     t=''.join(s['text'] for s in line['spans']).strip();box=line['bbox']
     if not t:continue
     if any(r.contains(fitz.Rect(box).tl+(1,1)) for r in table_rects):continue
     if is_page_footer_line(t,pi) and (box[1]>page.rect.height-45 or box[3]<40):discard.append([pi,t,list(box)]);continue
     events.append((box[1],box[0],{'text':t,'bbox':list(box)}))
  # Rows sharing a baseline retain left-to-right option order.
  events.sort(key=lambda x:(round(x[0]/3),x[1]))
  blocks=[];prev_y=None;prev_h=12;option_x=None
  for y,x,obj in events:
   if obj.get('type') in ['figure','table']:
    blocks.append(obj);allblocks.append(obj);prev_y=None
    if obj['type']=='table':source_text.extend(str(c) for row in obj['rows'] for c in row)
    continue
   t=obj['text'];source_text.append(t)
   heading=bool(HEAD.match(t));question=bool(QUESTION.match(t)) or (spec['year']==2017 and t.startswith('14 社会主义'));option=bool(OPTION.match(t));subq=bool(SUBQ.match(t))
   if question:qnums.append(int(re.match(r'\d+',t)[0]))
   new=heading or question or subq
   previous=blocks[-1] if blocks else (allblocks[-1] if allblocks else None)
   if option:
    # Keep A-E in one semantic block without joining with the question stem.
    if t.startswith('A'):option_x=x
    new=not (previous and previous['type']=='paragraph' and OPTION.match(previous['text']))
   elif previous and previous['type']=='paragraph' and OPTION.match(previous['text']) and not new:
    # wrapped option continuation belongs to its option block
    if option_x is not None and x<option_x-3:new=True
   elif prev_y is not None and y-prev_y>prev_h*2.4:new=True
   if not new and previous and previous['type']=='paragraph':
    previous['text']=join(previous['text'],t) if not option else previous['text']+' '+t
    if previous not in blocks:previous.setdefault('continued_on_pages',[]).append(pi)
   else:
    b={'type':'heading' if heading else 'paragraph','text':t};blocks.append(b);allblocks.append(b)
   prev_y=y;prev_h=obj['bbox'][3]-obj['bbox'][1]
  pageitem={'source_id':spec['id'],'source_page':pi,'blocks':blocks}
  if not blocks:pageitem['continuation_only']=True
  pages.append(pageitem)
 output=''.join(''.join(str(c) for row in b['rows'] for c in row) if b['type']=='table' else b.get('text','') for p in pages for b in p['blocks'])
 assert norm(output)==norm(''.join(source_text)),(spec['id'],'text reconciliation')
 result={'year':spec['year'],'title':spec['title'],'question_numbers':qnums,'pages':pages,'notes':[],'extraction':{'text_layer_reconciled':True,'removed_advert_pages':len(removed),'excluded_page_furniture':discard,'images':images}}
 (ROOT/f'source/{spec["year"]}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(spec['year'],len(pages),'images',len(images),'qnums',qnums,flush=True)
if __name__=='__main__':
 for spec in json.loads((ROOT/'sources.json').read_text()):
  if spec['year']<=2021:import_spec(spec)
