"""Source-backed regressions for reconstruction errors found during review."""
import json,fitz
from lxml import html
import build
from extract import HEADING
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
writing_index=next(i for i,block in enumerate(blocks)
                   if block['type']=='paragraph' and
                   build.plain_text(block).endswith('120 words but no more than 180 words.'))
assert blocks[writing_index+1]['bbox']==[110,110,402,212]
assert build.plain_text(blocks[writing_index+2])=='Part II Listening Comprehension (30 minutes)'
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
for stem in ('2014-12-01', '2014-12-02'):
    entry=next(e for e in m['papers'] if e['file']==f'cet4/papers/{stem}.htm')
    with fitz.open(build.source_pdf(entry)) as doc:
        source=doc[4]
        data=build.extract(source,unknown_glyphs=build.source_chars(source))
        blocks=build.prepare(data['blocks'],source)
    expected=[f'{number}.' for number in range(46,56)]
    before=[build.plain_text(block) for block in blocks]
    build.repair_cet4_matching_questions('cet4',stem,5,blocks)
    prompts=[block for block in blocks if block['type']=='question' and
             build.plain_text(block).startswith(tuple(expected))]
    assert [build.plain_text(block).split(' ',1)[0] for block in prompts]==expected
    assert [build.plain_text(block) for block in blocks]==before
entry=next(e for e in m['papers'] if e['file']=='cet4/papers/2014-06-01.htm')
with fitz.open(build.source_pdf(entry)) as doc:
    source=doc[6]
    data=build.extract(source,unknown_glyphs=build.source_chars(source))
paragraphs=[build.plain_text(block) for block in data['blocks'] if block['type']=='paragraph']
for opening in (
    'Part of the reason this happens',
    'We’ve all met the type',
    'Truth is, they’re nothing',
    'Many business executives confuse',
    'True leaders understand',
    'If you’re too concerned',
):
    assert sum(text.startswith(opening) for text in paragraphs)==1,opening
assert not HEADING.match('Part of the reason this happens')
for (category, stem, pn, number), (question_text, _, changes, new_question) in build.PDF_VERIFIED_OPTION_REPAIRS.items():
    entry=next(e for e in m['papers'] if e['file']==f'{category}/papers/{stem}.htm')
    with fitz.open(build.source_pdf(entry)) as doc:
        source=doc[pn-1]
        data=build.extract(source,unknown_glyphs=build.source_chars(source))
        blocks=build.prepare(data['blocks'],source)
    build.repair_pdf_verified_options(category,stem,pn,blocks)
    matching=[i for i,b in enumerate(blocks) if b['type']=='question' and
              build.plain_text(b)==(new_question or question_text)]
    assert len(matching)==1,(category,stem,pn,number)
    choices=blocks[matching[0]+1]
    assert choices['type']=='options' and [item['label'] for item in choices['items']]==list('ABCD')
    for item in choices['items']:
        if item['label'] in changes:
            assert build.plain_text(item)==changes[item['label']]
    tree=html.fromstring((build.ROOT/category/'papers'/f'{stem}.htm').read_text())
    printed=tree.xpath(f'//section[@data-source-page="{pn}"]//p[@class="question" and normalize-space()="{new_question or question_text}"]')
    assert len(printed)==1,(category,stem,pn,number)
    rendered=printed[0].getnext()
    assert rendered.tag=='ul' and 'options' in rendered.get('class','').split()
    assert [item.text_content().split('.',1)[0] for item in rendered.xpath('./li/span[@class="option-label"]')]==list('ABCD')
entry=next(e for e in m['papers'] if e['file']=='cet4/papers/2020-12-01.htm')
with fitz.open(build.source_pdf(entry)) as doc:
    source=doc[1]
    data=build.extract(source,unknown_glyphs=build.source_chars(source))
    blocks=build.prepare(data['blocks'],source)
build.repair_cet4_2020_12_01_listening_image('cet4','2020-12-01',2,blocks)
for number in (12,13,14,15):
    question=next(i for i,b in enumerate(blocks) if b['type']=='question' and
                  build.plain_text(b)==f'{number}.')
    assert [item['label'] for item in blocks[question+1]['items']]==list('ABCD')
assert build.plain_text(blocks[next(i for i,b in enumerate(blocks)
       if b['type']=='question' and build.plain_text(b)=='13.')+1]['items'][3])=='From a professional interior designer.'
assert not any(b['type']=='source_line' and 'She is really impressed' in build.plain_text(b) for b in blocks)
tree=html.fromstring((build.ROOT/'cet4/papers/2020-12-01.htm').read_text())
page=tree.xpath('//section[@data-source-page="2"]')[0]
for number in (12,13,14,15):
    prompt=page.xpath(f'./p[@class="question" and normalize-space()="{number}."]')
    assert len(prompt)==1
    assert len(prompt[0].getnext().xpath('./li'))==4

for (category, stem, pn, number), (old, new) in build.PDF_VERIFIED_SPACED_QUESTION_NUMBERS.items():
    entry=next(e for e in m['papers'] if e['file']==f'{category}/papers/{stem}.htm')
    with fitz.open(build.source_pdf(entry)) as doc:
        source=doc[pn-1]
        assert old in source.get_text().replace('\n',' ')
        data=build.extract(source,unknown_glyphs=build.source_chars(source))
        blocks=build.prepare(data['blocks'],source)
    joined_tail = (' of its convenience.' if number == 37 else '')
    assert sum(b['type']=='paragraph' and build.plain_text(b)==old + joined_tail
               for b in blocks)==1
    build.repair_pdf_verified_question_boundaries(category,stem,pn,blocks)
    question=next(i for i,b in enumerate(blocks)
                  if b['type']=='question' and build.plain_text(b)==new + joined_tail)
    if number==47:
        assert blocks[question+1]['type']=='options'
        assert [item['label'] for item in blocks[question+1]['items']]==list('ABCD')
    else:
        assert build.plain_text(blocks[question]).endswith('of its convenience.')
        assert [build.plain_text(b) for b in blocks if b['type']=='question' and
                build.plain_text(b).startswith(tuple(f'{n}.' for n in range(36,46)))][1:3]==[
                    new + joined_tail,'38. Different states have markedly different regulations for telemedicine.']
        q40=next(i for i,b in enumerate(blocks)
                 if b['type']=='question' and build.plain_text(b).startswith('40.'))
        assert build.plain_text(blocks[q40+1])=='telemedicine services.'
        assert build.plain_text(blocks[q40+2])==(
            "41. Some supporters of telemedicine hope states will accept each other's "
            'medical practice licenses as valid.')
        assert blocks[q40+2]['type']=='question'
    saved=json.loads((build.ROOT/category/'papers'/f'{stem}.json').read_text())
    page_blocks=saved['pages'][pn-1]['blocks']
    assert sum(b['type']=='question' and build.plain_text(b)==new + joined_tail
               for b in page_blocks)==1
    if number==37:
        assert [b['type'] for b in page_blocks if build.plain_text(b).startswith('41.')]==['question']

entry=next(e for e in m['papers'] if e['file']=='cet6/papers/2020-12-01.htm')
old='44 .. Agriculture proves very difficult to quantify because of the constantly changing conditions involved.'
new=old.replace('44 ..','44.',1)
with fitz.open(build.source_pdf(entry)) as doc:
    source=doc[5]
    assert old in source.get_text().replace('\n',' ')
    data=build.extract(source,unknown_glyphs=build.source_chars(source))
    blocks=build.prepare(data['blocks'],source)
assert sum(b['type']=='question' and build.plain_text(b)==old for b in blocks)==1
build.repair_pdf_verified_question_boundaries('cet6','2020-12-01',6,blocks)
assert sum(b['type']=='question' and build.plain_text(b)==new for b in blocks)==1
saved=json.loads((build.ROOT/'cet6/papers/2020-12-01.json').read_text())
assert sum(b['type']=='question' and build.plain_text(b)==new
           for b in saved['pages'][5]['blocks'])==1
print(f'{15 + len(build.PDF_VERIFIED_OPTION_REPAIRS) + len(build.PDF_VERIFIED_SPACED_QUESTION_NUMBERS)} source-backed extraction regressions passed')
