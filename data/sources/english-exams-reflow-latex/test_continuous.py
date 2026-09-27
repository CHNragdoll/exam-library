"""Regressions for reading instructions misparsed as options and split passages."""
import json,fitz
import build
m=json.load(open('../english-exams-web-2026-09-26/manifest.json'))
def extract(file,n):
 e=next(x for x in m['papers'] if x['file']==file)
 d=fitz.open(build.source_pdf(e));p=d[n-1]
 return build.extract(p,unknown_glyphs=build.source_chars(p))
def text(b):return ''.join(r['text'] for r in b.get('runs',[]))
a=extract('kaoyan/papers/2014-01.htm',2)
assert any('choosing A, B, C or D. Mark your answers' in text(b) for b in a['blocks']), 'D in directions must not become an option'
a=extract('kaoyan/papers/2014-01.htm',12)
assert any('Ground surveys allow' in text(b) and 'Most ground surveys involve' in text(b) for b in a['blocks']), 'lettered passage must stay together'
assert any('To find their sites' in text(b) and 'variety of high-technology' in text(b) for b in a['blocks'])
print('Instruction enumeration and wrapped lettered passages preserved')

from layout import continues_paragraph
p=lambda s:{'type':'paragraph','runs':[{'text':s,'flags':(False,False,False)}]}
assert continues_paragraph(p('A long paragraph reaches the physical page boundary and continues into the'),p('next page of the same sentence.'))
assert not continues_paragraph(p('This long paragraph reaches the physical page boundary and ends here.'),p('another paragraph'))
assert not continues_paragraph(p('A long paragraph reaches the physical page boundary and continues into the'),{'type':'question','runs':[]})
