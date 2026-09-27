"""Build 206 offline, text-reflowing English papers and matching LaTeX."""
# Shared reader shell: inject before this generator computes the HTML digest.
import sys as _reader_sys
from pathlib import Path as _ReaderPath
_reader_ui = next(p / 'exam-library' for p in _ReaderPath(__file__).resolve().parents if (p / 'exam-library/enhance_readers.py').is_file())
if str(_reader_ui) not in _reader_sys.path: _reader_sys.path.insert(0, str(_reader_ui))
from enhance_readers import write_reader
from pathlib import Path
import sys,json,re,html,hashlib,subprocess,zipfile,statistics,unicodedata
import fitz
from concurrent.futures import ProcessPoolExecutor
from lxml import html as lh
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT.parent/'layout-tools'))
from extract import extract,markup,plain,SITE
from repair_archive import source_pdf
from encoding import get_unknown_glyphs
from layout import prepare,copy_flowchart,continues_paragraph
from recover_image_questions import recover_image_questions

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def e(s):return html.escape(str(s),quote=True)
def textext(s):
    mapping={'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}','→':r'\(\rightarrow\)','←':r'\(\leftarrow\)','√':r'\(\sqrt{}\)','∞':r'\(\infty\)','≤':r'\(\leq\)','≥':r'\(\geq\)','·':r'\textperiodcentered{}','­':'-'}
    mapping.update({'‒':r'\textendash{}','А':r'{\fontspec{FandolSong-Regular.otf}А}','а':r'{\fontspec{FandolSong-Regular.otf}а}','′':r'\(\prime\)','″':r'\(\prime\prime\)','₂':r'\textsubscript{2}','―':r'\textemdash{}','℉':r'\(^{\circ}\mathrm{F}\)','■':r'\(\blacksquare\)','□':r'\(\square\)','♦':r'\(\blacklozenge\)'})
    mapping.update({chr(0x2460+i):r'\textcircled{'+str(i+1)+'}' for i in range(20)})
    return ''.join(mapping.get(c,unicodedata.normalize('NFKC',c) if 0x2160<=ord(c)<=0x217f else c) for c in s)
def texruns(runs):
    result=[]
    for r in runs:
        if r.get('glyph'):
            result.append(r'\raisebox{'+str(round(r.get('glyph_baseline',-.12),3))+r'em}{\includegraphics[height='+str(round(r.get('glyph_height',1),3))+r'em]{'+r['glyph'].replace('.svg','.png')+r'}}\allowbreak{}');continue
        text=''.join(r'\par\noindent\rule{.95\linewidth}{.4pt}\par ' if re.fullmatch(r'_{15,}',part) else textext(part) for part in re.split(r'(_{15,})',r['text']));b,u,i=r['flags']
        if r'\par' in text:b=u=i=False
        if u:text=(r'\CJKunderline{' if re.search(r'[\u3400-\u9fff]',r['text']) else r'\uline{')+text+'}'
        if i:text=r'\textit{'+text+'}'
        if b:text=r'\textbf{'+text+'}'
        result.append(text)
    return ''.join(result)
def htmlruns(runs):
    out=[]
    for r in runs:
        if r.get('glyph'):out.append(f'<img class="inline-glyph" src="{e(r["glyph"])}" style="height:{r.get('glyph_height',1):.3f}em;vertical-align:{r.get('glyph_baseline',-.12):.3f}em" alt="原卷字形">')
        else:
            if r['flags'][1] and r['text'].strip().isdigit():out.append('<span class="blank">'+e(r['text'])+'</span>')
            else:out.append(markup([r]))
    return ''.join(out)
def source_chars(page):
    return get_unknown_glyphs(page)

def restore_cet4_2015_06_01_page_one(blocks):
    """Correct the caption's PDF text-map glyph against the printed page."""
    caption=blocks[4]
    assert caption['type']=='paragraph' and len(caption['runs'])==1
    assert caption['runs'][0]['text']=='“Why am 丨going to school if my phone already knows everything?”'
    # The printed character is a Latin capital I, not the mapped CJK stroke.
    caption['runs'][0]['text']='“Why am I going to school if my phone already knows everything?”'

def restore_cet4_2015_06_02_page_one(blocks):
    """Move two printed text fragments out of this paper's mixed figure crop."""
    writing=blocks[3]
    figure=blocks[4]
    listening=blocks[5]
    assert writing['type']=='paragraph' and ''.join(r['text'] for r in writing['runs']).endswith(' 120')
    assert figure['type']=='figure' and all(abs(a-b)<.1 for a,b in zip(figure['bbox'],[78.78,98.00,461.85,228.68]))
    assert listening['type']=='heading' and ''.join(r['text'] for r in listening['runs'])=='Part II'
    writing['runs'].append({'text':' words but no more than 180 words.','flags':[False,False,False]})
    # The source figure crop also contains this text and the listening heading.
    # Restrict it to the four-panel cartoon so both fragments appear only once.
    figure['bbox']=[110,110,402,212]
    listening['runs'][0]['text']='Part II Listening Comprehension (30 minutes)'

def restore_cet6_2014_12_01_page_one(blocks):
    """Separate the printed answer-sheet note from the classroom cartoon."""
    figure=blocks[3]
    following=blocks[4]
    assert figure['type']=='figure' and all(abs(a-b)<.1 for a,b in zip(figure['bbox'],[22.16,138.78,330.92,285.92]))
    assert following['type']=='paragraph' and ''.join(r['text'] for r in following['runs']).startswith('PartⅡ Listening Comprehension')
    # The left edge of the source crop includes the note; the right holds the art and its caption.
    figure['bbox']=[181.5,140,330.8,275.5]
    blocks.insert(4,{'type':'paragraph','runs':[{'text':'注意：此部分试题请在答题卡 1 上作答。','flags':[False,False,False]}]})

def restore_cet6_2014_12_03_page_one(blocks):
    """Restore the clipped word limit and keep it outside the cartoon crop."""
    writing=blocks[1]
    figure=blocks[2]
    assert writing['type']=='paragraph' and ''.join(r['text'] for r in writing['runs']).endswith('no more than')
    assert figure['type']=='figure' and all(abs(a-b)<.1 for a,b in zip(figure['bbox'],[53.56,132.80,373.76,460.90]))
    writing['runs'][-1]['text']+=' 200 words.'
    figure['bbox']=[64,161,371,461]

# Crops verified against the source PDFs. Keep these corrections in the
# generator so a later rebuild does not recreate clipped artwork or text.
FIGURE_CROP_REPAIRS = {
    ('cet4', '2015-06-01', 1, 3): ([175.56, 130.08, 358.68, 256.08], [175.56, 130.08, 358.68, 251.9]),
    ('cet4', '2015-06-03', 1, 3): ([219.54, 119.46, 385.38, 256.98], [219.54, 119.46, 385.38, 252.8]),
    ('cet6', '2015-12-01', 1, 3): ([20.94, 114.245, 350.46, 247.02], [157.26, 129.7, 350.46, 247.02]),
    ('cet6', '2015-12-02', 1, 3): ([23.22, 96.621, 346.26, 262.08], [163.14, 109.7, 346.26, 259.1]),
    ('cet6', '2015-12-03', 1, 3): ([201.72, 109.5, 381, 244.62], [201.72, 112.5, 381, 244.0]),
    ('cet6', '2021-06-01', 1, 3): ([141.909, 207.646, 488.429, 435.656], [141.909, 191.8, 488.429, 435.656]),
    ('cet6', '2021-06-03', 1, 3): ([175.757, 207.181, 432.334, 352.087], [175.757, 207.181, 432.334, 350.9]),
    ('kaoyan', '2022-02', 14, 6): ([147.1, 228.014, 395.4, 395.917], [147.1, 228.014, 451, 395.917]),
    ('kaoyan', '2023-02', 14, 6): ([124.92, 198.417, 471.48, 373.354], [124.92, 198.417, 471.48, 386]),
    ('kaoyan', '2024-01', 14, 13): ([91.92, 529.8, 283.32, 734.4], [91.92, 529.8, 472, 734.4]),
}

def repair_figure_crops(category, stem, page_number, blocks):
    repaired_figure_index = None
    for (paper_category, paper_stem, pn, index), (old, new) in FIGURE_CROP_REPAIRS.items():
        if (paper_category, paper_stem, pn) != (category, stem, page_number):
            continue
        matches = [(position, block) for position, block in enumerate(blocks)
                   if block['type'] == 'figure' and
                   all(abs(a-b) < .15 for a, b in zip(block['bbox'], old))]
        assert len(matches) == 1, (category, stem, page_number, old)
        repaired_figure_index, figure = matches[0]
        figure['bbox'] = new
    if (category, stem, page_number) == ('cet6', '2015-12-01', 1):
        assert ''.join(r['text'] for r in blocks[2]['runs']).endswith('at least 150')
        blocks[2]['runs'][-1]['text'] += ' words but no more than 200 words.'
    elif (category, stem, page_number) == ('cet6', '2015-12-02', 1):
        assert ''.join(r['text'] for r in blocks[2]['runs']).endswith('at least')
        blocks[2]['runs'][-1]['text'] += ' 150 words but no more than 200 words.'
    elif (category, stem, page_number) == ('kaoyan', '2022-02', 14):
        next_index = repaired_figure_index + 1
        assert blocks[next_index]['type'] == 'paragraph' and plain_text(blocks[next_index]) == '总体农村'
        blocks.pop(next_index)  # The legend is now inside the complete chart crop.
    elif (category, stem, page_number) == ('kaoyan', '2023-02', 14):
        next_index = repaired_figure_index + 1
        assert blocks[next_index]['type'] == 'paragraph' and plain_text(blocks[next_index]).startswith('2012 2013 2014')
        blocks.pop(next_index)  # The year labels are now inside the complete chart crop.
    elif (category, stem, page_number) == ('kaoyan', '2024-01', 14):
        labels = blocks[repaired_figure_index + 1:repaired_figure_index + 4]
        assert [block['type'] for block in labels] == ['paragraph'] * 3
        assert plain_text(labels[0]).startswith('某市近三年公园数量')
        del blocks[repaired_figure_index + 1:repaired_figure_index + 4]

def plain_text(block):
    return ''.join(run['text'] for run in block.get('runs', []))

def repair_cet4_matching_questions(category, stem, page_number, blocks):
    """Keep the ten printed matching prompts as questions, not section headings."""
    if (category, stem, page_number) not in {
        ('cet4', '2014-12-01', 5),
        ('cet4', '2014-12-02', 5),
    }:
        return
    prompts = [block for block in blocks
               if re.match(r'^\s*(?:4[6-9]|5[0-5])\.\s', plain_text(block))]
    assert len(prompts) == 10
    assert [re.match(r'^\s*(\d+)\.', plain_text(block)).group(1) for block in prompts] == [
        str(number) for number in range(46, 56)
    ]
    assert all(block['type'] == 'heading' for block in prompts)
    for block in prompts:
        block['type'] = 'question'

PDF_VERIFIED_SPACED_QUESTION_NUMBERS = {
    ('cet4', '2020-07-01', 7, 47): (
        '4 7. How are business transactions done in big modern stores?',
        '47. How are business transactions done in big modern stores?'),
    ('cet6', '2019-12-01', 10, 47): (
        '4 7. Why does the Harvard neuroscientist say that lying takes work?',
        '47. Why does the Harvard neuroscientist say that lying takes work?'),
    ('cet6', '2021-06-01', 7, 47): (
        '4 7. What does the author think of the recent research?',
        '47. What does the author think of the recent research?'),
    ('cet6', '2020-09-02', 4, 37): (
        '3 7. Many employers are eager to provide telemedicine service as a benefit to their employees because',
        '37. Many employers are eager to provide telemedicine service as a benefit to their employees because'),
}

# These 22 PDF-visible labels are separated by spurious spaces in the PDF
# text map. The original HTM SVG layer independently carries the same printed
# numbers; restrict promotion to the audited paper/page/number tuple.
PDF_VERIFIED_ADDITIONAL_QUESTION_LABELS = {
    ('cet4', '2021-12-01', 8): (47,),
    ('cet4', '2021-12-01', 10): (55,),
    ('cet4', '2021-12-03', 6): (47,),
    ('cet6', '2019-12-01', 2): (11, 13),
    ('cet6', '2019-12-01', 3): (15, 18),
    ('cet6', '2019-12-01', 8): (37,),
    ('cet6', '2019-12-01', 11): (51,),
    ('cet6', '2019-12-02', 2): (11, 13),
    ('cet6', '2019-12-02', 3): (15, 18),
    ('cet6', '2020-09-01', 2): (11, 13),
    ('cet6', '2020-09-01', 3): (18,),
    ('cet6', '2020-09-01', 8): (36,),
    ('cet6', '2020-09-01', 11): (51,),
    ('cet6', '2020-12-01', 7): (47,),
    ('cet6', '2021-12-02', 9): (47,),
    ('cet6', '2021-12-02', 11): (55,),
    ('cet6', '2021-12-03', 5): (47,),
}

SPACED_QUESTION_LABEL = re.compile(r'^\s*([1-5])\s+([0-9])\s*[.．]\s*')
INLINE_PRINTED_OPTION = re.compile(r'(?<![A-Za-z])([A-D])\s*[)）]\s*')

def repair_pdf_verified_additional_question_labels(category, stem, page_number, blocks):
    """Restore audited CET question boundaries and their printed A/C choices."""
    if (category, stem, page_number) == ('cet6', '2020-09-01', 3):
        # The adjacent Q15 already had a card, but its A–D choices remained
        # embedded in the stem and three paragraphs on the same printed page.
        matches = [index for index, block in enumerate(blocks)
                   if block['type'] == 'question' and
                   plain_text(block) == '15. A ) Their appreciation of help from the outsiders.']
        assert len(matches) == 1
        index = matches[0]
        blocks[index]['runs'] = [{'text': '15.', 'flags': [False, False, False]}]
        blocks.insert(index + 1, {'type': 'options', 'items': [{
            'label': 'A', 'runs': [{'text': 'Their appreciation of help from the outsiders.',
                                  'flags': [False, False, False]}]}]})
        for label, part in zip('BCD', blocks[index + 2:index + 5]):
            assert part['type'] == 'paragraph' and len(part['runs']) == 1
            value = plain_text(part)
            prefix = re.match(rf'^\s*{label}\s*[)）]\s*', value)
            assert prefix
            part['type'] = 'options'
            part['items'] = [{'label': label, 'runs': [{
                'text': value[prefix.end():].strip(), 'flags': [False, False, False]}]}]
            part.pop('runs')
    if (category, stem, page_number) == ('cet6', '2021-12-02', 7):
        old = ('wrongly believe in the causal relationship between music and IQ. '
               '3 7. The belief in the positive effects of music training appeals to many researchers who are')
        matches = [index for index, block in enumerate(blocks)
                   if block['type'] == 'paragraph' and plain_text(block) == old]
        assert len(matches) == 1
        index = matches[0]
        assert blocks[index - 1]['type'] == 'question' and plain_text(blocks[index - 1]).startswith('36.')
        assert blocks[index + 1]['type'] == 'paragraph' and plain_text(blocks[index + 1]) == 'musicians themselves.'
        blocks[index]['runs'] = [{'text': 'wrongly believe in the causal relationship between music and IQ.',
                                  'flags': [False, False, False]}]
        blocks.insert(index + 1, {'type': 'question', 'runs': [{
            'text': '37. The belief in the positive effects of music training appeals to many researchers who are',
            'flags': [False, False, False]}]})
    targets = PDF_VERIFIED_ADDITIONAL_QUESTION_LABELS.get((category, stem, page_number))
    if not targets:
        return
    found = []
    for index in range(len(blocks) - 1, -1, -1):
        block = blocks[index]
        if block['type'] != 'paragraph':
            continue
        source = plain_text(block)
        match = SPACED_QUESTION_LABEL.match(source)
        if not match:
            continue
        number = int(match.group(1) + match.group(2))
        if number not in targets:
            continue
        assert len(block['runs']) == 1, (category, stem, page_number, number)
        tail = source[match.end():]
        option_matches = list(INLINE_PRINTED_OPTION.finditer(tail))
        block['type'] = 'question'
        if option_matches:
            assert option_matches[0].group(1) == 'A' and not tail[:option_matches[0].start()].strip()
            items = []
            for position, choice in enumerate(option_matches):
                end = option_matches[position + 1].start() if position + 1 < len(option_matches) else len(tail)
                value = tail[choice.end():end].strip()
                assert value, (category, stem, page_number, number)
                items.append({'label': choice.group(1), 'runs': [
                    {'text': value, 'flags': [False, False, False]}]})
            assert [item['label'] for item in items] in (['A'], ['A', 'C'])
            block['runs'][0]['text'] = f'{number}.'
            blocks.insert(index + 1, {'type': 'options', 'items': items})
            if (category, stem, page_number, number) == ('cet6', '2020-09-01', 2, 13):
                following = blocks[index + 2:index + 5]
                assert len(following) == 3 and all(part['type'] == 'paragraph' for part in following)
                for label, part in zip('BCD', following):
                    value = plain_text(part)
                    prefix = re.match(rf'^\s*{label}\s*[)）]\s*', value)
                    assert prefix and len(part['runs']) == 1
                    part['type'] = 'options'
                    part['items'] = [{'label': label, 'runs': [{
                        'text': value[prefix.end():].strip(), 'flags': [False, False, False]}]}]
                    part.pop('runs')
        else:
            assert tail, (category, stem, page_number, number)
            block['runs'][0]['text'] = f'{number}. {tail}'
        found.append(number)
    assert sorted(found) == sorted(targets), (category, stem, page_number, targets, found)


CET6_LISTENING_NUMBERS = {
    ('cet6', '2015-06-03', 1): tuple(range(1, 11)),
    ('cet6', '2015-06-03', 2): tuple(range(11, 24)),
    ('cet6', '2015-06-03', 3): (24, 25),
    ('cet6', '2014-12-01', 3): (23, 24, 25),
}
CET6_CHINESE_QUESTION = re.compile(r'(?<!\d)(\d{1,2})、\s*')

def repair_cet6_pdf_listening_questions(category, stem, page_number, blocks):
    """Separate PDF-verified listening questions printed with 、 and inline choices."""
    targets = CET6_LISTENING_NUMBERS.get((category, stem, page_number))
    if not targets:
        return
    found = []
    for index in range(len(blocks) - 1, -1, -1):
        block = blocks[index]
        if block['type'] != 'paragraph':
            continue
        source = plain_text(block)
        markers = [m for m in CET6_CHINESE_QUESTION.finditer(source)
                   if int(m.group(1)) in targets]
        if not markers:
            continue
        replacement = []
        prefix = source[:markers[0].start()].strip()
        if prefix:
            assert (category, stem, page_number) == ('cet6', '2015-06-03', 1)
            replacement.append({'type': 'paragraph', 'runs': [{
                'text': prefix, 'flags': [False, False, False]}]})
        for position, marker in enumerate(markers):
            number = int(marker.group(1))
            tail = source[marker.end():markers[position + 1].start() if position + 1 < len(markers) else len(source)]
            choices = list(INLINE_PRINTED_OPTION.finditer(tail))
            assert choices and choices[0].group(1) == 'A' and not tail[:choices[0].start()].strip(), (category, stem, page_number, number, tail)
            items = []
            for choice_index, choice in enumerate(choices):
                end = choices[choice_index + 1].start() if choice_index + 1 < len(choices) else len(tail)
                value = tail[choice.end():end].strip()
                assert value, (category, stem, page_number, number, choice.group(1))
                items.append({'label': choice.group(1), 'runs': [{
                    'text': value, 'flags': [False, False, False]}]})
            replacement.extend((
                {'type': 'question', 'runs': [{'text': f'{number}.', 'flags': [False, False, False]}]},
                {'type': 'options', 'items': items},
            ))
            found.append(number)
        blocks[index:index + 1] = replacement
    assert sorted(found) == list(targets), (category, stem, page_number, sorted(found), targets)


# Five 15-word banks were visually checked on their original PDF pages. The
# PDF font map reads printed O) as zero and appends it to another column; keep
# the other 14 words untouched except the three independently checked OCR
# spellings below.
PDF_VERIFIED_WORD_BANKS = {
    ('cet6', '2021-06-02', 4): ({'J': 'overhaul 0) ultimately',
                                'K': 'perm;mentlyK) permanently'},
                               {'J': 'overhaul', 'K': 'permanently', 'O': 'ultimately'}),
    ('cet4', '2021-06-03', 1): ({'J': 'routinely 0) wonder'},
                               {'J': 'routinely', 'O': 'wonder'}),
    ('cet6', '2020-09-01', 5): ({'G': 'legacies 0) viciously',
                                'L': 'reahns', 'N': 'rum'},
                               {'G': 'legacies', 'L': 'realms', 'N': 'run', 'O': 'viciously'}),
    ('cet6', '2020-09-02', 1): ({'G': 'leverage 0) undoubtedly'},
                               {'G': 'leverage', 'O': 'undoubtedly'}),
    ('cet6', '2019-12-03', 2): ({'G': 'conceded 0) warrant',
                                'H': 'consc10usness'},
                               {'G': 'conceded', 'H': 'consciousness', 'O': 'warrant'}),
}

def repair_pdf_verified_word_bank(category, stem, page_number, blocks):
    case = (category, stem, page_number)
    if case not in PDF_VERIFIED_WORD_BANKS:
        return
    matches = [block for block in blocks if block['type'] == 'options'
               and [item['label'] for item in block['items']] == list('ABCDEFGHIJKLMN')]
    assert len(matches) == 1, case
    items = matches[0]['items']
    before, after = PDF_VERIFIED_WORD_BANKS[case]
    for item in items:
        label = item['label']
        if label not in before:
            continue
        assert plain_text(item) == before[label] and len(item['runs']) == 1, (case, label)
        item['runs'][0]['text'] = after[label]
    items.append({'label': 'O', 'runs': [{'text': after['O'],
                                       'flags': [False, False, False]}]})


def repair_pdf_verified_question_boundaries(category, stem, page_number, blocks):
    """Restore question labels visibly printed without PDF text-map spaces."""
    for (paper_category, paper_stem, pn, _), (old, new) in PDF_VERIFIED_SPACED_QUESTION_NUMBERS.items():
        if (category, stem, page_number) != (paper_category, paper_stem, pn):
            continue
        matches = [block for block in blocks if block['type'] == 'paragraph' and plain_text(block) == old]
        assert len(matches) == 1, (category, stem, page_number, old)
        block = matches[0]
        assert len(block['runs']) == 1
        block['type'] = 'question'
        block['runs'][0]['text'] = new

    if (category, stem, page_number) == ('cet6', '2020-12-01', 6):
        old = ('44 .. Agriculture proves very difficult to quantify because of the '
               'constantly changing conditions involved.')
        matches = [block for block in blocks if block['type'] == 'question' and plain_text(block) == old]
        assert len(matches) == 1 and len(matches[0]['runs']) == 1
        matches[0]['runs'][0]['text'] = old.replace('44 ..', '44.', 1)

    if (category, stem, page_number) != ('cet6', '2020-09-02', 4):
        return
    old = ("telemedicine services. 4 1 . Some supporters of telemedicine hope states will accept "
           "each other's medical practice licenses as valid. ---")
    matches = [index for index, block in enumerate(blocks)
               if block['type'] == 'paragraph' and plain_text(block) == old]
    assert len(matches) == 1
    index = matches[0]
    assert len(blocks[index]['runs']) == 1
    assert blocks[index - 1]['type'] == 'question' and plain_text(blocks[index - 1]).startswith('40.')
    assert blocks[index + 1]['type'] == 'question' and plain_text(blocks[index + 1]).startswith('42.')
    # The visual PDF has two separate lines: Q40's final words, then Q41.
    # The source text map inserts spaces in 41 and a nonprinted trailing rule.
    blocks[index]['runs'][0]['text'] = 'telemedicine services.'
    blocks.insert(index + 1, {'type': 'question', 'runs': [
        {'text': "41. Some supporters of telemedicine hope states will accept each other's "
                 'medical practice licenses as valid.', 'flags': [False, False, False]}
    ]})

def repair_pdf_verified_tail_choices(category, stem, page_number, blocks):
    """Keep three visually checked, irregular CET question/section boundaries."""
    case = (category, stem, page_number)
    if case == ('cet6', '2020-12-02', 1):
        matches = [i for i, block in enumerate(blocks)
                   if block['type'] == 'question' and plain_text(block) == '4.']
        assert len(matches) == 1
        index = matches[0]
        assert blocks[index + 1]['type'] == 'options'
        assert [(item['label'], plain_text(item)) for item in blocks[index + 1]['items']] == [
            ('A', 'Clearer road signs.')]
        crop = blocks[index + 2]
        assert crop['type'] == 'source_line'
        assert plain_text(crop).startswith(
            'B) More people driving safely.C) Stricter traffic rules.'
            'D_) More self-driving trucks on the road.')
        assert blocks[index + 3]['type'] == 'question' and plain_text(blocks[index + 3]) == '5.'
        # These three lines are printed inside the retained source crop. The
        # selectable PDF layer maps the printed D) as D_), so use the image.
        blocks.insert(index + 3, {'type': 'options', 'items': [
            {'label': label, 'runs': [{'text': value, 'flags': [False, False, False]}]}
            for label, value in (
                ('B', 'More people driving safely.'),
                ('C', 'Stricter traffic rules.'),
                ('D', 'More self-driving trucks on the road.'),
            )
        ]})

    if case == ('cet4', '2014-12-01', 7):
        matches = [i for i, block in enumerate(blocks)
                   if block['type'] == 'question' and plain_text(block).startswith(
                       '61. Alex Pang’s new book is aimed for readers who')]
        assert len(matches) == 1
        index = matches[0]
        group = blocks[index + 1]
        assert group['type'] == 'options'
        assert [item['label'] for item in group['items']] == list('ABC')
        last = group['items'][2]
        assert len(last['runs']) == 1
        assert last['runs'][0]['text'] == (
            'are fearful about using the cellphone or computer '
            'AD) can hardly tear themselves away from the Internet')
        last['runs'][0]['text'] = 'are fearful about using the cellphone or computer'
        # The PDF really prints "AD)" on a separate line. Keep that source
        # label distinct, without manufacturing a normal D choice.
        blocks.insert(index + 2, {'type': 'paragraph', 'runs': [
            {'text': 'AD) can hardly tear themselves away from the Internet',
             'flags': [False, False, False]}]})

    if case == ('cet4', '2018-06-01', 7):
        matches = [i for i, block in enumerate(blocks)
                   if block['type'] == 'question' and plain_text(block) == (
                       '45. Digital access codes are criticized because they are '
                       'profit-driven just like the textbook')]
        assert len(matches) == 1
        index = matches[0]
        merged, remainder, false_option = blocks[index + 1:index + 4]
        assert merged['type'] == remainder['type'] == 'paragraph'
        assert [run['text'] for run in merged['runs']] == [
            'business.Section C ', 'Directions:',
            ' There are 2 passages in this section. Each passage is followed by some questions']
        assert plain_text(remainder) == (
            'or unfinished statements. For each of them there are four choices marked A), B), C) and')
        assert false_option['type'] == 'options' and [item['label'] for item in false_option['items']] == ['D']
        assert plain_text(false_option['items'][0]).startswith('. You should decide on the best choice')
        assert blocks[index + 4]['type'] == 'heading' and plain_text(blocks[index + 4]) == 'Passage One'
        blocks[index]['runs'][0]['text'] += ' business.'
        direction_runs = merged['runs'][1:] + [
            {'text': ' ', 'flags': [False, False, True]}] + remainder['runs'] + [
            {'text': ' D)', 'flags': [False, False, True]}] + false_option['items'][0]['runs']
        blocks[index + 1:index + 4] = [
            {'type': 'heading', 'runs': [{'text': 'Section C', 'flags': [True, False, False]}]},
            {'type': 'instruction', 'runs': direction_runs},
        ]

def repair_split_option_labels(category, stem, page_number, blocks):
    """Repair a few PDF text-layer option labels checked against their four choices."""
    for index in range(len(blocks) - 2, -1, -1):
        question = blocks[index]
        if question['type'] != 'question' or not re.fullmatch(r'\d+[.．]', plain_text(question).strip()):
            continue
        groups = []
        for block in blocks[index + 1:]:
            if block['type'] != 'options':
                break
            groups.append(block)
        if len(groups) < 2:
            continue
        items = [item for group in groups for item in group['items']]
        labels = ''.join(item['label'] for item in items)
        key = (category, stem, page_number, plain_text(question).strip())
        if key in {
            ('cet6', '2015-12-02', 2, '8.'),
            ('cet4', '2014-06-03', 1, '7.'),
        }:
            assert labels == 'ABCC'
            items[-1]['label'] = 'D'
        elif key in {
            ('cet4', '2015-12-01', 1, '3.'),
            ('cet4', '2014-06-03', 1, '6.'),
        }:
            assert labels == 'ACCD'
            items[2]['label'] = 'B'
        elif key in {
            ('cet6', '2025-12-02', 2, '12.'),
            ('cet4', '2015-12-01', 1, '6.'),
            ('cet4', '2021-06-01', 3, '20.'),
        }:
            assert labels in {'ABCCD', 'ACBCD'}
            blanks = [(group, item) for group in groups for item in group['items']
                      if item['label'] == 'C' and not plain_text(item)]
            assert len(blanks) == 1
            blanks[0][0]['items'].remove(blanks[0][1])
        elif key == ('cet4', '2016-06-02', 3, '22.'):
            assert labels == 'ABCDD' and plain_text(items[2]) == 'Ph.'
            assert plain_text(items[3]) == 'candidates in dieting.'
            items[2]['runs'][0]['text'] = 'Ph.D. candidates in dieting.'
            next(group for group in groups if items[3] in group['items'])['items'].remove(items[3])
        elif key == ('kaoyan', '2012-02', 4, '22.'):
            assert labels == 'ALABCD' and not plain_text(items[1])
            assert plain_text(items[0]).startswith('Unified has made the rule about homework')
            question['runs'].append({'text': ' ' + plain_text(items[0]), 'flags': [False, False, False]})
            blocks.remove(groups[0])

# These exceptions were checked against the printed PDF pages. The expected
# source fragments make a future upstream extraction change fail visibly.
PDF_VERIFIED_OPTION_REPAIRS = {
    ('tem4', '2023', 10, 14): (
        '14. It is imperative that the local government ______ more investment into the burgeoning hi-tech industry.',
        [('options', 'ACD')],
        {'A': 'has to attract', 'B': 'shall attract'}, None),
    ('tem4', '2025', 10, 16): (
        '16. I went there in 2014, and that was the only occasion when I ________ the journey in exactly two days.',
        [('options', 'ABD'), ('paragraph', 'make C. must make')],
        {'A': 'was able to make', 'C': 'must make'}, None),
    ('tem8', '2025', 6, 22): (
        '22. When the author said “the view would be clear for miles around” (Para. 2), the boat ______',
        [('paragraph', 'A was at the bottom of the swells. B. was climbing up the swells.'), ('options', 'CD')],
        {'A': 'was at the bottom of the swells.', 'B': 'was climbing up the swells.'}, None),
    ('cet6', '2024-12-01', 8, 51): (
        '51. What do we learn about beauty in the digital arena?',
        [('paragraph', 'A It dictates the taste of digital media. C. It has ushered in a new awakening.'), ('options', 'BD')],
        {'A': 'It dictates the taste of digital media.', 'C': 'It has ushered in a new awakening.'}, None),
    ('cet6', '2024-12-01', 8, 53): (
        '53. What do we learn from the passage about the Instagram face?',
        [('paragraph', 'A It is now regarded as the new beauty ideal. C. It is being much talked about on social media.'), ('options', 'BD')],
        {'A': 'It is now regarded as the new beauty ideal.', 'C': 'It is being much talked about on social media.'}, None),
    ('cet6', '2020-12-02', 2, 19): (
        '19.', [('options', 'AB'), ('paragraph', '. C) It continues to bum up calories to help us stay in shape.'), ('options', 'D')],
        {'B': 'It remains inactive without burning calories noticeably.',
         'C': 'It continues to burn up calories to help us stay in shape.'}, None),
    ('cet6', '2020-07-01', 1, 2): (
        '2.', [('options', 'A'), ('source_line', 'B) How nutrition helps ��������� performance in competitions.'), ('options', 'CD')],
        {'B': 'How nutrition helps athletes’ performance in competitions.'}, None),
    ('cet6', '2020-07-01', 1, 4): (
        '4.', [('options', 'A'), ('source_line', 'B) It may lead to ��������� over reliance on equipment.'), ('options', 'CD')],
        {'B': 'It may lead to athletes’ over reliance on equipment.'}, None),
    ('cet6', '2020-09-01', 2, 12): (
        '12.', [('options', 'A'),
                ('paragraph', 'B ) He was trying to preserve the languages of the Indian tribes.'),
                ('paragraph', 'C ) His contact with a social worker had greatly aroused his interest in the tribe.'),
                ('paragraph', 'D ) His meeting with Gonzalez had made him eager to learn more about the tribe.')],
        {'B': 'He was trying to preserve the languages of the Indian tribes.',
         'C': 'His contact with a social worker had greatly aroused his interest in the tribe.',
         'D': 'His meeting with Gonzalez had made him eager to learn more about the tribe.'}, None),
    ('cet6', '2020-09-01', 2, 14): (
        '14.', [('options', 'A'), ('paragraph', 'B ) Unjustifiable. D ) Tedious.')],
        {'A': 'Unpredictable.', 'B': 'Unjustifiable.', 'C': 'Laborious.', 'D': 'Tedious.'}, None),
    ('cet4', '2020-12-02', 8, 54): (
        '54. What accounts for our increasing desire for forests?',
        [('options', 'ABC'), ('paragraph', '· D) Their stable supply of building materials.')],
        {'D': 'Their stable supply of building materials.'}, None),
    ('cet6', '2018-06-01', 2, 12): (
        '12. A )All services will be personalized.', [('options', 'BCD')],
        {'A': 'All services will be personalized.'}, '12.'),
    ('cet6', '2017-12-01', 2, 12): (
        '12. A )Moveable metal type began to be used in printing.', [('options', 'BCD')],
        {'A': 'Moveable metal type began to be used in printing.'}, '12.'),
    ('cet6', '2017-12-02', 2, 12): (
        '12. A )All of the acting nominees are white.', [('options', 'BCD')],
        {'A': 'All of the acting nominees are white.'}, '12.'),
    ('cet4', '2015-06-01', 7, 60): (
        '60. What does the author suggest to reduce melanoma rates?',
        [('options', 'AC'), ('paragraph', 'B ) Staying in the shade whenever possible. D) Applying the right amount of sunscreen.')],
        {'B': 'Staying in the shade whenever possible.', 'D': 'Applying the right amount of sunscreen.'}, None),
    ('cet6', '2013-06-02', 2, 13): (
        '13.', [('options', 'AC'), ('paragraph', ') B) It helps singers warm themselves up. D) It can do harm to singers’ vocal chords.')],
        {'B': 'It helps singers warm themselves up.', 'D': 'It can do harm to singers’ vocal chords.'}, None),
    ('cet6', '2012-12-01', 14, 69): (
        '69.', [('options', 'ABD')], {'B': 'marvelous', 'C': 'temporary'}, None),
    ('cet6', '2012-12-01', 14, 73): (
        '73.', [('options', 'AB')], {'B': 'depth', 'C': 'length', 'D': 'height'}, None),
    ('cet6', '2012-12-02', 12, 58): (
        "58. What did the author think of Professor Filreis's poetry session?",
        [('options', 'ABC')],
        {'C': 'It was extremely appealing to the students.',
         'D': 'It pulled students out of prose reading sessions.'}, None),
    ('cet4', '2021-06-01', 3, 25): (
        '25.', [('options', 'AC'),
                ('source_line', 'B) She married her husband in 1972. �� ��� ������ ��� ������� ������ �������')],
        {'B': 'She married her husband in 1972.',
         'D': 'She helped the village to become famous.'}, None),
    ('cet4', '2021-06-02', 2, 8): (
        '8.', [('options', 'ABD')],
        {'A': 'Find out where Jimmy is.', 'C': 'Make friends with Jimmy.'}, None),
    ('cet6', '2020-12-01', 8, 53): (
        "53. What do we learn from the Dietary Guidelines Advisory Committee's scientific report?",
        [('options', 'ABC'), ('paragraph', 'DLFarming consumes most of our natural resources.')],
        {'D': 'Farming consumes most of our natural resources.'}, None),
    ('cet6', '2020-07-01', 2, 13): (
        '13.', [('options', 'A'),
                ('source_line', 'B) It prevents the ������ fatty tissues from growing.'),
                ('options', 'CD')],
        {'B': 'It prevents the mice’s fatty tissues from growing.'}, None),
    ('cet6', '2020-07-01', 3, 14): (
        '14.', [('options', 'A'),
                ('source_line', 'B) Half of a �������� total weight variation can be controlled.'),
                ('options', 'CD')],
        {'B': 'Half of a person’s total weight variation can be controlled.'}, None),
    ('cet6', '2020-07-01', 3, 17): (
        '17.', [('options', 'AC'),
                ('source_line', 'B) The joy found in each ������� company. D) Emotional factors.')],
        {'B': 'The joy found in each other’s company.', 'D': 'Emotional factors.'}, None),
    ('cet6', '2020-07-01', 10, 49): (
        '49. What can be inferred from the passage about day-to-day stress?',
        [('source_line', 'A) It is harmful to ����� physical and mental health.'),
         ('options', 'BC'),
         ('source_line', 'D) It does not help build up ����� tolerance.')],
        {'A': 'It is harmful to one’s physical and mental health.',
         'D': 'It does not help build up one’s tolerance.'}, None),
    ('cet6', '2020-07-01', 11, 51): (
        '51. What does the author say sounds ironic?',
        [('options', 'AB'),
         ('source_line', 'C) The species of prey animals continue to vary despite ������� hunting.'),
         ('options', 'D')],
        {'C': 'The species of prey animals continue to vary despite humans’ hunting.'}, None),
    ('cet6', '2020-07-01', 12, 54): (
        '54. When is hunting morally justifiable according to Gary E. Varner?',
        [('options', 'AB'),
         ('source_line', 'C) When it is indispensable to ������� subsistence.'),
         ('options', 'D')],
        {'C': 'When it is indispensable to humans’ subsistence.'}, None),
    ('cet4', '2020-12-02', 3, 25): (
        '25.', [('options', 'AC'),
                ('source_line', '�� �� ��������� �o�� ��cessa�� ��������� D) It supplies the body with enough calories.')],
        {'B': 'It provides some necessary nutrients.',
         'D': 'It supplies the body with enough calories.'}, None),
    ('cet6', '2016-06-03', 8, 53): (
        '53. What does the author think the union should do to win popular support?',
        [('options', 'ABC')],
        {'C': 'Demand higher pay for teachers.',
         'D': 'Help teachers improve teaching.'}, None),
    ('cet4', '2015-12-02', 2, 17): (
        '17.', [('options', 'AC'),
                ('paragraph', 'They take drugs to get high. D) They keep drug use a secret.')],
        {'B': 'They take drugs to get high.', 'D': 'They keep drug use a secret.'}, None),
    ('cet6', '2013-12-02', 1, 7): (
        '7. A labor dispute at a bus company. C) A corporate takeover.',
        [('options', 'BD')],
        {'A': 'A labor dispute at a bus company.', 'C': 'A corporate takeover.'}, '7.'),
}

def repair_pdf_verified_options(category, stem, page_number, blocks):
    """Restore option structure only where the PDF and old blocks were checked."""
    for (paper_category, paper_stem, pn, number), (question_text, expected, changes, new_question) in PDF_VERIFIED_OPTION_REPAIRS.items():
        if (category, stem, page_number) != (paper_category, paper_stem, pn):
            continue
        found = [i for i, block in enumerate(blocks)
                 if block['type'] == 'question' and plain_text(block) == question_text]
        assert len(found) == 1, (category, stem, page_number, number)
        index = found[0]
        old = blocks[index + 1:index + 1 + len(expected)]
        actual = [(block['type'], ''.join(item['label'] for item in block['items'])
                   if block['type'] == 'options' else plain_text(block)) for block in old]
        assert actual == expected, (category, stem, page_number, number, actual)
        items = {item['label']: item for block in old if block['type'] == 'options'
                 for item in block['items']}
        assert len(items) == sum(len(block['items']) for block in old if block['type'] == 'options')
        for label, value in changes.items():
            items[label] = {'label': label, 'runs': [{'text': value, 'flags': [False, False, False]}]}
        assert set(items) == set('ABCD'), (category, stem, page_number, number)
        if new_question:
            blocks[index]['runs'] = [{'text': new_question, 'flags': [False, False, False]}]
        blocks[index + 1:index + 1 + len(expected)] = [
            {'type': 'options', 'items': [items[label] for label in 'ABCD']}
        ]

def repair_cet4_2020_12_01_listening_image(category, stem, page_number, blocks):
    """Transcribe the PDF-verified 12–15 choices from one corrupt text-map crop."""
    if (category, stem, page_number) != ('cet4', '2020-12-01', 2):
        return
    starts = [i for i, block in enumerate(blocks)
              if block['type'] == 'question' and plain_text(block) == '12.']
    assert len(starts) == 1
    index = starts[0]
    first, crop = blocks[index + 1:index + 3]
    assert first['type'] == 'options' and len(first['items']) == 1
    assert first['items'][0]['label'] == 'A'
    assert plain_text(first['items'][0]) == 'She is a real expert at house decorations.'
    assert crop['type'] == 'source_line'
    assert all(abs(actual - expected) < .15 for actual, expected in zip(
        crop['bbox'], [44.68, 350.24, 511.29, 542.02]))
    assert hashlib.sha256(plain_text(crop).encode()).hexdigest() == (
        'd474d60abc5d679e9db6d421488d2f1b0f4f4ab133a0a6a4a9521504c9b852e2')

    def options(values):
        return {'type': 'options', 'items': [
            {'label': label, 'runs': [{'text': value, 'flags': [False, False, False]}]}
            for label, value in zip('ABCD', values)
        ]}

    def question(number):
        return {'type': 'question', 'runs': [
            {'text': f'{number}.', 'flags': [False, False, False]}
        ]}

    # Printed page 2 has four complete A–D groups. The selectable PDF layer
    # merges them into one corrupt source_line; every value below was read
    # from the visible page, including question 13's unreadable D value.
    groups = {
        12: ('She is a real expert at house decorations.',
             "She is really impressed by the man's house.",
             'She is well informed about the design business.',
             'She is attracted by the color of the sitting room.'),
        13: ('From a construction businessman.',
             'From his younger brother Greg.',
             'From home design magazines.',
             'From a professional interior designer.'),
        14: ('The cost was affordable.', 'The style was fashionable.',
             'The effort was worthwhile.', 'The effect was unexpected.'),
        15: ("She'd like him to talk with Jonathan about a new project.",
             "She'd like to show him around her newly-renovated house.",
             'She wants to discuss the house decoration budget with him.',
             'She wants him to share his renovation experience with her.'),
    }
    replacement = [options(groups[12])]
    for number in (13, 14, 15):
        replacement.extend((question(number), options(groups[number])))
    blocks[index + 1:index + 3] = replacement

def make_paper(entry):
    src=source_pdf(entry);assert sha(src)==entry['source_pdf_sha256']
    category=entry['category'];stem=Path(entry['file']).stem
    target=ROOT/category/'papers'/f'{stem}.htm';target.parent.mkdir(parents=True,exist_ok=True)
    assets=target.with_suffix('.assets');assets.mkdir(exist_ok=True)
    doc=fitz.open(src);sections=[];tex=[];pages=[];glyphs=0;figure_total=0
    for pn,page in enumerate(doc,1):
        unknown=source_chars(page)
        data=extract(page,unknown_glyphs=unknown)
        data['blocks']=prepare(data['blocks'],page)
        if category=='cet4' and stem=='2015-06-01' and pn==1:
            restore_cet4_2015_06_01_page_one(data['blocks'])
        if category=='cet4' and stem=='2015-06-02' and pn==1:
            restore_cet4_2015_06_02_page_one(data['blocks'])
        if category=='cet6' and stem=='2014-12-01' and pn==1:
            restore_cet6_2014_12_01_page_one(data['blocks'])
        if category=='cet6' and stem=='2014-12-03' and pn==1:
            restore_cet6_2014_12_03_page_one(data['blocks'])
        repair_figure_crops(category, stem, pn, data['blocks'])
        repair_split_option_labels(category, stem, pn, data['blocks'])
        repair_cet4_matching_questions(category, stem, pn, data['blocks'])
        repair_pdf_verified_question_boundaries(category, stem, pn, data['blocks'])
        repair_pdf_verified_additional_question_labels(category, stem, pn, data['blocks'])
        repair_cet6_pdf_listening_questions(category, stem, pn, data['blocks'])
        recover_image_questions(category, stem, pn, data['blocks'],
                                ROOT.parent/'english-exams-web-2026-09-26'/entry['file'])
        repair_pdf_verified_tail_choices(category, stem, pn, data['blocks'])
        repair_pdf_verified_options(category, stem, pn, data['blocks'])
        repair_pdf_verified_word_bank(category, stem, pn, data['blocks'])
        repair_cet4_2020_12_01_listening_image(category, stem, pn, data['blocks'])
        rendered=[];textblocks=[];pageglyph=0
        note_pending=any(b['type']=='source_line' for b in data['blocks'])
        plain_text_end=''.join(r['text'] for r in pages[-1]['blocks'][-1].get('runs',[])).rstrip() if pages and pages[-1]['blocks'] else ''
        for bi,b in enumerate(data['blocks']):
            for rs in ([] if b['type']=='source_line' else [b['runs']] if 'runs'in b else [item['runs'] for item in b.get('items',[])]):
                for r in rs:
                    if r.get('glyph_box'):
                        pageglyph+=1;glyphs+=1;name=f'char-{pn:03}-{pageglyph:03}';box=fitz.Rect(r.pop('glyph_box'))
                        box=box+(-.3,-.3,.3,.3)
                        try:page.get_pixmap(dpi=300,clip=box & page.rect,alpha=False).save(assets/(name+'.png'))
                        except Exception as error:raise ValueError(f'{category}/{stem} page {pn} crop {box}: {error}') from None
                        r['glyph']=assets.name+'/'+name+'.png'
                        r['glyph_height']=box.height/r.pop('glyph_font_size',12);r['glyph_baseline']=(r.pop('glyph_origin_y',box.y1-2)-box.y1)/ (box.height/r['glyph_height'])
            if b['type']=='source_line':
                pageglyph+=1;glyphs+=1;name=f'char-{pn:03}-line-{bi:03}';box=fitz.Rect(b['bbox']).normalize()
                page.get_pixmap(dpi=220,clip=box,alpha=False).save(assets/(name+'.png'))
                width=box.width/b['font_size'];height=box.height/b['font_size']
                rendered.append(f'<div class="source-line"><img src="{assets.name}/{name}.png" style="width:{width:.3f}em" alt="原卷文字区域，文字层异常，保留原图"></div>')
                tex.append(r'\noindent\includegraphics[width=\linewidth,height=.8\textheight,keepaspectratio]{'+assets.name+'/'+name+r'.png}\par')
            elif b['type']=='flowchart':
                figure_total+=1;name=f'figure-{pn:03}-{bi:03}'
                copy_flowchart(page,b['bbox'],assets/name)
                rendered.append(f'<figure class="flowchart" style="width:{fitz.Rect(b["bbox"]).width/12:.3f}em"><img src="{assets.name}/{name}.svg" alt="'+e(' → '.join(b['tokens']))+'"></figure>')
                tex.append(r'\begin{center}\includegraphics[width=\linewidth]{'+assets.name+'/'+name+r'.pdf}\end{center}')
            elif b['type']=='choice_row':
                cells='<span class="choice-number">'+htmlruns(b['runs'])+'</span>'+''.join('<span class="choice-item"><strong>'+e(item['label'])+'.</strong> '+htmlruns(item['runs'])+'</span>' for item in b['items'])
                rendered.append('<div class="choice-scroll"><div class="choice-row">'+cells+'</div></div>')
                tex.append(r'\noindent\begin{tabularx}{\linewidth}{@{}lXXXX@{}}'+texruns(b['runs'])+' & '+' & '.join(r'\textbf{'+x['label']+'.} '+texruns(x['runs']) for x in b['items'])+r'\\\end{tabularx}\par')
            elif b['type']=='caption':
                caption='<figcaption>'+htmlruns(b['runs'])+'</figcaption>'
                if rendered and rendered[-1].endswith('</figure>'):rendered[-1]=rendered[-1][:-9]+caption+'</figure>'
                else:rendered.append('<p class="figure-caption">'+htmlruns(b['runs'])+'</p>')
                tex.append(r'\begin{center}'+texruns(b['runs'])+r'\end{center}')
            elif b['type']=='figure':
                figure_total+=1;name=f'figure-{pn:03}-{bi:03}';box=fitz.Rect(b['bbox'])
                temp=fitz.open();clip=box & page.rect;out=temp.new_page(width=clip.width,height=clip.height);out.show_pdf_page(out.rect,doc,pn-1,clip=clip)
                (assets/(name+'.svg')).write_text(temp[0].get_svg_image(text_as_path=True));temp[0].get_pixmap(dpi=160).save(assets/(name+'.png'));temp.close()
                rendered.append(f'<figure><img src="{assets.name}/{name}.svg" alt="原卷图表" loading="lazy"></figure>')
                tex.append(r'\begin{center}\includegraphics[width=.85\linewidth,height=.55\textheight,keepaspectratio]{'+assets.name+'/'+name+r'.png}\end{center}')
            elif b['type']=='options':
                long=any(sum(len(r['text']) for r in item['runs'])>85 for item in b['items'])
                rendered.append('<ul class="options'+(' single' if long else '')+'">'+''.join('<li><span class="option-label">'+e(item['label'])+'.</span><span>'+htmlruns(item['runs'])+'</span></li>' for item in b['items'])+'</ul>')
                tex.append(r'\begin{itemize}[leftmargin=2em,itemsep=.2em,topsep=.4em]'+''.join(r'\item['+item['label']+'.] '+texruns(item['runs'])+'\n' for item in b['items'])+r'\end{itemize}')
            else:
                tag='h2' if b['type']=='heading' else 'p'
                value=texruns(b['runs']).rstrip()
                join=(bi==0 and pages and pages[-1]['blocks'] and not note_pending
                    and continues_paragraph(pages[-1]['blocks'][-1],b)
                    and sections[-1].endswith('</p></section>'))
                if join:
                    separator='' if plain_text_end.endswith('-') else ' '
                    sections[-1]=sections[-1][:-14]+separator+f'<span data-source-page="{pn}">'+htmlruns(b['runs'])+'</span></p></section>'
                    tex[-1]=tex[-1].rstrip()+separator+value+'\n'
                    b['continues_previous_page']=True
                else:
                    rendered.append(f'<{tag} class="{b["type"]}">'+htmlruns(b['runs'])+f'</{tag}>')
                    tex.append((r'\subsection*{'+value+'}' if tag=='h2' else value)+'\n')
        note=f'<p class="notice">本页部分文字层异常，已保留原图文字区域；这些区域随窗口缩放，暂不能重新换行或复制。</p>' if pageglyph else ''
        sections.append(f'<section data-source-page="{pn}">{note}'+''.join(rendered)+'</section>')
        data.pop('source_text');data['unmapped_source_glyphs']=unknown;data['source_page']=pn;data['inline_glyphs']=pageglyph;pages.append(data)
    title=entry['title'];shared=''
    if entry.get('shared_with_second_paper'):
        second=stem.rsplit('-',1)[0]+'-02.htm';shared=f'<p class="notice">原资料只提供本套的独立部分，其余题目与第 2 套共用。<a href="{second}">打开第 2 套</a></p>'
    body='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+e(title)+'</title><link rel="stylesheet" href="../../style.css"></head><body><header><a href="../index.htm">← 分类目录</a><h1>'+e(title)+'</h1><p>文字重排 · 随窗口自动换行 · 可选中复制 · 离线阅读</p><nav><a href="'+stem+'.tex" download>下载 LaTeX 源码</a><a href="'+stem+'.json" download>下载结构化文本</a></nav>'+shared+'</header><main class="paper">'+''.join(sections)+'</main><footer>图表保留独立原图；不含听力音频及付费解析。</footer></body></html>'
    write_reader(target, body)
    texdoc=r'''\documentclass[UTF8,11pt]{ctexart}
\usepackage[a4paper,margin=22mm]{geometry}
\usepackage{graphicx,enumitem,amssymb,tabularx}
\usepackage[normalem]{ulem}
\usepackage{xeCJKfntef}
\setlength{\parindent}{0pt}
\setlength{\parskip}{.6em}
\sloppy
\begin{document}
'''+r'\section*{'+textext(title)+'}\n'+'\n\n'.join(tex)+'\n'+r'\end{document}'
    target.with_suffix('.tex').write_text(texdoc)
    target.with_suffix('.json').write_text(json.dumps({'title':title,'pages':pages},ensure_ascii=False,indent=2))
    return {'category':category,'year':entry['year'],'title':title,'file':str(target.relative_to(ROOT)),'pages':len(doc),'inline_glyphs':glyphs,'figures':figure_total,'source_pdf_sha256':entry['source_pdf_sha256'],'htm_sha256':sha(target),'source_word_count':entry.get('english_words')}

def catalogs(manifest,entries):
    categories=manifest['categories']
    for category in categories:
        code=category['category'];group=[e for e in entries if e['category']==code];blocks=[]
        for year in sorted({e['year'] for e in group},reverse=True):
            items=sorted((e for e in group if e['year']==year),key=lambda e:Path(e['file']).name,reverse=True)
            cards=''.join('<article class="entry"><h3><a href="'+str(Path(e['file']).relative_to(code))+'">'+e['title']+'</a></h3><p>'+str(e['pages'])+' 页 · 文字重排</p><a href="'+str(Path(e['file']).relative_to(code).with_suffix('.tex'))+'" download>LaTeX 源码</a></article>' for e in items)
            blocks.append(f'<section class="year"><h2>{year}</h2><div class="cards">{cards}</div></section>')
        (ROOT/code/'index.htm').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+category['name']+' · 重排版</title><link rel="stylesheet" href="../style.css"></head><body><header><a href="../index.htm">← 全部考试</a><h1>'+category['name']+'</h1><p>'+str(len(group))+' 套 · HTML 自适应正文与 LaTeX 源码</p></header><main class="catalog">'+''.join(blocks)+'</main></body></html>')
    cards=''.join('<a class="category" href="'+c['category']+'/index.htm"><strong>'+c['name']+'</strong><small>'+str(len([e for e in entries if e['category']==c['category']]))+' 套试卷</small></a>' for c in categories)
    (ROOT/'index.htm').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>英语真题 · 文字重排版</title><link rel="stylesheet" href="style.css"></head><body><header><h1>英语真题 · 文字重排版</h1><p>206 套公开试卷 · 正文随窗口换行 · 可选中复制 · 附 LaTeX 源码</p></header><main class="catalog categories">'+cards+'</main><footer>部分旧卷文字层异常，对应区域保留原图并在页内提示。旧版原卷文件不变。</footer></body></html>')

def main():
    manifest=json.loads((ROOT.parent/'english-exams-web-2026-09-26/manifest.json').read_text());entries=[]
    selected=manifest['papers']
    if '--sample' in sys.argv:
        selected=[x for x in selected if x['file'] in ['kaoyan/papers/2026-01.htm','kaoyan/papers/2000-01.htm','cet4/papers/2014-06-01.htm','cet6/papers/2012-06-01.htm','tem4/papers/2022.htm','tem8/papers/2022.htm']]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for i,result in enumerate(pool.map(make_paper,selected),1):
            entries.append(result);print(f'{i}/{len(selected)} {result["file"]} glyphs={result["inline_glyphs"]} figures={result["figures"]}',flush=True)
    catalogs(manifest,entries)
    (ROOT/'manifest.json').write_text(json.dumps({'papers':entries,'documents':len(entries),'pages':sum(e['pages'] for e in entries),'inline_glyphs':sum(e['inline_glyphs'] for e in entries),'figures':sum(e['figures'] for e in entries),'browser_tested':False},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
