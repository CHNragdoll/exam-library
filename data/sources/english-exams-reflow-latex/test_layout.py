"""Regressions for screenshot-reported stem, caption, diagram and choice layout."""
import json,fitz
from pathlib import Path
from collections import Counter
import build
from layout import prepare
m=json.loads((build.ROOT.parent/'english-exams-web-2026-09-26/manifest.json').read_text())
def load(file,pn):
 e=next(x for x in m['papers'] if x['file']==file);d=fitz.open(build.source_pdf(e));p=d[pn-1];data=build.extract(p,unknown_glyphs=build.source_chars(p));return d,p,data

d,p,a=load('kaoyan/papers/2000-01.htm',13)
assert any(b['type']=='question' and '3) Suggest counter-measures.'==''.join(r['text'] for r in b.get('runs',[])) for b in a['blocks'])
assert any(b['type']=='caption' and 'A Brief History' in str(b) for b in a['blocks'])
assert not any('counter-measures' in p.get_text(clip=fitz.Rect(b['bbox'])) for b in a['blocks'] if b['type']=='figure')
d,p,a=load('kaoyan/papers/2026-01.htm',12)
b=prepare(a['blocks'],p)
assert next(x['tokens'] for x in b if x['type']=='flowchart')==['F','41.','42.','H','43.','C','44.','45.']
def letters(blocks):
 c=Counter()
 for b in blocks:
  for r in b.get('runs',[]):c.update(x for x in r['text'] if x.isalnum())
  for item in b.get('items',[]):
   c.update(item['label'])
   for r in item['runs']:c.update(x for x in r['text'] if x.isalnum())
 return c
for file in ['kaoyan/papers/2001-01.htm','kaoyan/papers/2026-01.htm']:
 d,p,a=load(file,2);before=letters(a['blocks']);after=prepare(a['blocks'],p);assert before==letters(after)
 rows=[x for x in after if x['type']=='choice_row'];assert rows
 assert all([i['label'] for i in b['items']]==list('ABCD') for b in rows)
print('Stem, caption, flowchart, one-line choices and text-preservation checks passed')

for file in ['cet4/papers/2015-06-02.htm','cet6/papers/2015-12-02.htm']:
 d,p,a=load(file,1)
 assert not any(b['type']=='caption' and ('Directions' in str(b) or 'Part' in str(b) or '注意' in str(b)) for b in a['blocks'])
print('Directions, section headings and answer-sheet notes are not figure captions')
