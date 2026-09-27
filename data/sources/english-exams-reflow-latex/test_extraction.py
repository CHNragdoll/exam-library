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
e=next(e for e in m['papers'] if e['file']=='cet4/papers/2015-06-01.htm')
d=fitz.open(build.source_pdf(e));p=d[0]
a=build.extract(p,unknown_glyphs=build.source_chars(p))
blocks=build.prepare(a['blocks'],p)
build.restore_cet4_2015_06_01_page_one(blocks)
assert ''.join(r['text'] for r in blocks[4]['runs'])=='“Why am I going to school if my phone already knows everything?”'
e=next(e for e in m['papers'] if e['file']=='cet4/papers/2015-06-02.htm')
d=fitz.open(build.source_pdf(e));p=d[0]
a=build.extract(p,unknown_glyphs=build.source_chars(p))
blocks=build.prepare(a['blocks'],p)
build.restore_cet4_2015_06_02_page_one(blocks)
assert ''.join(r['text'] for r in blocks[3]['runs']).endswith('120 words but no more than 180 words.')
assert blocks[4]['bbox']==[110,110,402,212]
assert ''.join(r['text'] for r in blocks[5]['runs'])=='Part II Listening Comprehension (30 minutes)'
for stem,repair in (
    ('2014-12-01',build.restore_cet6_2014_12_01_page_one),
    ('2014-12-03',build.restore_cet6_2014_12_03_page_one),
):
    e=next(e for e in m['papers'] if e['file']==f'cet6/papers/{stem}.htm')
    d=fitz.open(build.source_pdf(e));p=d[0]
    data=build.extract(p,unknown_glyphs=build.source_chars(p))
    blocks=build.prepare(data['blocks'],p)
    repair(blocks)
    if stem=='2014-12-01':
        assert blocks[3]['bbox']==[181.5,140,330.8,275.5]
        assert ''.join(r['text'] for r in blocks[4]['runs'])=='注意：此部分试题请在答题卡 1 上作答。'
        assert blocks[5]['type']=='paragraph' and ''.join(r['text'] for r in blocks[5]['runs']).startswith('PartⅡ Listening Comprehension')
    else:
        assert ''.join(r['text'] for r in blocks[1]['runs']).endswith('no more than 200 words.')
        assert blocks[2]['bbox']==[64,161,371,461]
        assert blocks[3]['type']=='paragraph' and ''.join(r['text'] for r in blocks[3]['runs']).startswith('注意：此部分试题')
print('9 source-backed extraction regressions passed')
