"""Source-backed regressions for reconstruction errors found during review."""
import json,fitz
import build
m=json.loads((build.ROOT.parent/'english-exams-web-2026-09-26/manifest.json').read_text())
def page(file,pn):
    e=next(e for e in m['papers'] if e['file']==file);d=fitz.open(build.source_pdf(e));p=d[pn-1]
    return build.extract(p,unknown_glyphs=build.source_chars(p))
def strings(data):return [''.join(r['text'] for r in b.get('runs',[])) for b in data['blocks']]
a=page('cet6/papers/2015-12-02.htm',5)
assert any('from coal-powered' in s for s in strings(a))
a=page('cet4/papers/2015-06-01.htm',1)
assert any('In this section, you will hear 8 short conversations' in s for s in strings(a))
a=page('cet4/papers/2014-06-01.htm',1)
assert any([i['label'] for i in b.get('items',[])]==list('ABCD') for b in a['blocks'])
a=page('kaoyan/papers/2026-01.htm',14)
fig=[b for b in a['blocks'] if b['type']=='figure'];assert len(fig)==1 and fig[0]['bbox'][0]<85 and fig[0]['bbox'][2]>430
a=page('kaoyan/papers/2026-02.htm',14)
fig=[b for b in a['blocks'] if b['type']=='figure'];assert len(fig)==1 and fig[0]['bbox'][1]<508 and fig[0]['bbox'][3]>650
print('5 source-backed extraction regressions passed')
