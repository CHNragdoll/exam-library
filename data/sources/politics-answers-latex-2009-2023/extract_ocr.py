"""Import OCR line geometry into editable flowing answer paragraphs."""
from pathlib import Path
import json,re,difflib
ROOT=Path(__file__).resolve().parent
HEADING=re.compile(r'^(?:[一二三四五六七八九十]+[、．.]|\d{4}\s*年.*(?:考试|试题|政治)|招生考试.*详解|【(?:考点|试题|解析))')
ANSWER=re.compile(r'^\s*(\d{1,2})[.．、]?\s*【(?:标准)?[答笞]案】\s*([A-D]+)')
NUMBER=re.compile(r'^\s*(\d{1,2})[.．、]\s*')
FOOT=re.compile(r'^(?:[•·.\-—\s]*\d+[•·.\-—\s]*|\d{4}\s*年.*第\s*\d+\s*页.*)$')
def norm(t):return re.sub(r'\s+','',t)
def join(a,b):return a+(' ' if a and b and a[-1].isascii() and b[0].isascii() and a[-1].isalnum() and b[0].isalnum() else '')+b
def build(spec):
 pages=[];allblocks=[];dropped=[];answer_key={};headings=[];trace=[]
 for pn in range(1,spec['pages']+1):
  path=ROOT/f'work/page-images/{spec["id"]}/{pn:03}.ocr.json';rows=json.loads(path.read_text());rows.sort(key=lambda r:(round(r['bbox'][1]*200),r['bbox'][0]))
  blocks=[];prev=None
  for i,row in enumerate(rows):
   t=row['text'].strip();x,y,x1,y1=row['bbox']
   if FOOT.fullmatch(t) and (y>.90 or y1<.06):dropped.append([pn,t]);continue
   # Some source OCR layers use a crossed 1; recognise only beside answer marker.
   if re.match(r'^[士十-]\s*【标准[答笞]案】',t):t=re.sub(r'^[士十-]\s*','1.',t);trace.append([pn,row['text'],t])
   t=t.replace('【标准笞案】','【标准答案】')
   m=ANSWER.match(t)
   if m:answer_key[m[1]]=m[2]
   number=NUMBER.match(t);h=HEADING.match(t)
   new=bool(m or number or h or re.match(r'^[（(]\d+[）)]',t))
   previous=blocks[-1] if blocks else (allblocks[-1] if allblocks else None)
   # PDF line indent and vertical gap mark paragraphs; no hard page boundaries.
   if prev and y-prev['bbox'][3]>.009:new=True
   if not new and previous and previous['type']=='paragraph':previous['text']=join(previous['text'],t)
   else:
    b={'type':'heading' if m or (h and len(t)<60) else 'paragraph','text':t}
    blocks.append(b);allblocks.append(b)
    if m or number:headings.append([pn,t[:70]])
   prev=row
  pages.append({'source_id':spec['id'],'source_page':pn,'blocks':blocks,**({'continuation_only':True} if not blocks else {})})
 result={'year':spec['year'],'title':spec['title'],'answer_key':answer_key,'pages':pages,'notes':[], 'extraction':{'method':'local Vision OCR; awaiting source comparison','excluded_page_furniture':dropped,'label_corrections':trace,'answer_headings':headings}}
 (ROOT/f'source/{spec["year"]}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(spec['year'],len(answer_key),len(headings),len(dropped),flush=True)
if __name__=='__main__':
 for spec in json.loads((ROOT/'sources.json').read_text()):build(spec)
