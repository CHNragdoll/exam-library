"""Attach the shared offline reader shell without rewriting any exam markup.

Generators call write_reader() before computing their existing HTML hashes.
The catalog calls enhance_all() to reconcile already-generated readers.
"""
from pathlib import Path
import gzip
import hashlib
import html
import json
import os
import re
from collections import Counter, defaultdict
from urllib.parse import quote

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT.parent
MARKERS = re.compile(r'<!-- exam-ui:(head|body) -->.*?<!-- /exam-ui:\1 -->', re.S)
_cache = (None, {})
ENGLISH_CATEGORIES = frozenset({'kaoyan', 'cet4', 'cet6', 'tem4', 'tem8'})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def strip_ui(content):
    return MARKERS.sub('', content)


def translation_paragraph_starts(original, reflow):
    """Find source paragraph starts belonging to this paper's translation passage.

    Some older CET papers use sentence-completion translation questions and have
    answer/explanation pages after the question. Those pages must not supply
    paragraph anchors for the reflow reader.
    """
    reflow_soup = BeautifulSoup(strip_ui(reflow.read_text(encoding='utf-8')), 'html.parser')
    passage = ''
    for heading in reflow_soup.select('main h2, main h3'):
        if not re.search(r'\bPart\s*(?:IV|Ⅳ|4)\b.*\bTranslation\b',
                         heading.get_text(' ', strip=True), re.I):
            continue
        pieces = []
        for node in heading.find_all_next(['h2', 'h3', 'p']):
            if node.name in {'h2', 'h3'}:
                break
            text = node.get_text(' ', strip=True)
            if re.match(r'注意\s*[：:]', text):
                break
            pieces.append(text)
        content = ' '.join(pieces)
        directions = re.search(r'Answer\s+Sheet\s*2\s*\.', content, re.I)
        if directions:
            passage = re.sub(r'\s+', '', content[directions.end():])
        break
    if len(re.findall(r'[\u3400-\u9fff]', passage)) < 30:
        return []

    soup = BeautifulSoup(original.read_text(encoding='utf-8'), 'html.parser')
    active = False
    anchors = []
    for page in soup.select('main .page-wrap'):
        lines = defaultdict(list)
        for node in page.select('svg.text-overlay text[x][y]'):
            try:
                lines[round(float(node['y']), 1)].append((float(node['x']), node.get_text()))
            except ValueError:
                continue
        chinese = []
        for y in sorted(lines):
            parts = sorted(lines[y])
            line = ''.join(text for _, text in parts)
            if re.search(r'Translation', line, re.I) and ('Part' in line or 'minutes' in line):
                active = True
                continue
            if not active:
                continue
            if re.match(r'\s*注意\s*[：:]', line):
                active = False
                break
            if re.search(r'[\u3400-\u9fff]', line):
                chinese.append((parts[0][0], line))
        if len(chinese) < 2:
            continue
        baseline = Counter(round(x, 1) for x, _ in chinese).most_common(1)[0][0]
        for x, line in chinese:
            if x >= baseline + 8:
                anchor = re.sub(r'\s+', '', line)[:12]
                if anchor and anchor in passage and anchor not in anchors:
                    anchors.append(anchor)
    return anchors


def kaoyan_source_layout(original):
    """Match long lettered passages and email alignment to the source text layer."""
    soup = BeautifulSoup(original.read_text(encoding='utf-8'), 'html.parser')
    markers = []
    signoff_right = False
    for page in soup.select('main .page-wrap'):
        lines = defaultdict(list)
        for node in page.select('svg.text-overlay text[x][y]'):
            try:
                lines[round(float(node['y']), 1)].append((float(node['x']), node.get_text()))
            except ValueError:
                continue
        for parts in lines.values():
            parts.sort()
            line = ''.join(text for _, text in parts)
            match = re.match(r'^\s*([A-O])([.)])\s*(\w.{30,})', line)
            if match:
                preview = re.sub(r'\s+', '', match.group(3)).lower()[:24]
                markers.append({'letter': match.group(1), 'marker': match.group(2),
                                'preview': preview})
            if re.match(r'^\s*Yours,\s*$', line) and parts[0][0] > 200:
                signoff_right = True
    return {'letteredParagraphMarkers': markers, 'emailSignoffRight': signoff_right}


def reading_paragraph_starts(original, reflow):
    """Find source-indented prose starts trapped inside a reflow paragraph.

    A source line must have a first-line indent relative to its page's text
    margin and a unique, exact text match. Lettered matching-passage lines
    use a hanging indent, so the line after A) must not count as a start.
    Uncertain lines are left unchanged rather than guessed from punctuation.
    """
    source = BeautifulSoup(original.read_text(encoding='utf-8'), 'html.parser')
    target = BeautifulSoup(reflow.read_text(encoding='utf-8'), 'html.parser')
    sections = target.select('main section[data-source-page]')
    answer_start_page = next((int(section['data-source-page']) for section in sections
                              if any(re.search(r'(?:真题|试卷)?答案(?:与详解|与解析|解析)?|参考答案|答案详解',
                                               heading.get_text())
                                     for heading in section.select('h2.heading'))), None)
    paragraphs = []
    for section in sections:
        page_index = int(section['data-source-page'])
        if answer_start_page is not None and page_index >= answer_start_page:
            continue
        for block_index, block in enumerate(section.find_all(recursive=False)):
            if block.name == 'p' and 'paragraph' in block.get('class', []):
                content = block.get_text()
                if re.match(r'^\s*(?:[A-O]\s*[.)]|[MW]\s*:)', content):
                    continue
                # Some combined PDFs append Chinese answer explanations to
                # the question pages. These are not reading-passage prose.
                if len(re.findall(r'[\u3400-\u9fff]', content)) > len(content) * .2:
                    continue
                paragraphs.append((page_index, block_index + 1,
                                   re.sub(r'\s+', '', content)))
    starts = []
    seen = set()
    for source_page_index, page in enumerate(source.select('main .page-wrap'), 1):
        lines = defaultdict(list)
        for node in page.select('svg.text-overlay text[x][y]'):
            try:
                lines[round(float(node['y']), 1)].append((float(node['x']), node.get_text()))
            except ValueError:
                continue
        ordered = []
        for y, parts in sorted(lines.items()):
            parts.sort()
            ordered.append((y, parts[0][0], ''.join(text for _, text in parts)))
        margins = [x for _, x, line in ordered if len(line) >= 35]
        if not margins:
            continue
        margin = min(margins)
        for line_index, (y, x, line) in enumerate(ordered):
            if not (margin + 18.5 <= x <= margin + 35) or len(line) < 45:
                continue
            if not re.match(r'[A-Z“‘]', line):
                continue
            previous = next((ordered[index] for index in range(line_index - 1, -1, -1)
                             if len(ordered[index][2]) >= 35), None)
            if previous:
                previous_y, previous_x, previous_line = previous
                if re.match(r'^\s*[A-O][.)]\s+', previous_line):
                    continue
                # Wrapped lines in hanging-indented matching passages keep
                # the same x coordinate. A real new prose paragraph returns
                # from the left body margin to an indented first line.
                if abs(previous_x - x) < 3 and y - previous_y < 25:
                    continue
            anchor = re.sub(r'\s+', '', line)[:35]
            matches = [(page_index, block_index, text.find(anchor))
                       for page_index, block_index, text in paragraphs if anchor in text]
            if len(matches) != 1 or matches[0][2] <= 0:
                continue
            page_index, block_index, offset = matches[0]
            target_text = next(text for candidate_page, candidate_block, text in paragraphs
                               if candidate_page == page_index and candidate_block == block_index)
            # A first-line indent alone is not proof of a new paragraph: it
            # can be a wrapped proper name or an option. Require the preceding
            # reflow text to finish a sentence (possibly inside a quote).
            before = re.sub(r'["\'”’）)]+$', '', target_text[:offset])
            if not re.search(r'[.!?。！？]$', before):
                continue
            key = (page_index, block_index, anchor)
            if key in seen:
                continue
            seen.add(key)
            starts.append({'anchor': anchor, 'sourcePageIndex': source_page_index,
                           'sourceLineIndex': line_index, 'sourceY': y,
                           'reflowPageIndex': page_index, 'reflowBlockIndex': block_index})
    return starts


def registry():
    global _cache
    path = ROOT / 'documents.json'
    redraw_path = ROOT / 'image-redraws.json'
    structured_path = ROOT / 'structured/audit.json'
    if not path.exists():
        return {}
    stamp = (path.stat().st_mtime_ns,
             redraw_path.stat().st_mtime_ns if redraw_path.exists() else None,
             structured_path.stat().st_mtime_ns if structured_path.exists() else None)
    if _cache[0] == stamp:
        return _cache[1]
    data = json.loads(path.read_text())
    records = data if isinstance(data, list) else data['documents']
    documents_by_id = {item['id']: item for item in records}
    redraws = {}
    if redraw_path.exists():
        redraw_data = json.loads(redraw_path.read_text())
        assert redraw_data['version'] == 1 and isinstance(redraw_data['images'], list)

        def source_path(value):
            assert isinstance(value, str) and value and not Path(value).is_absolute(), value
            target = (SOURCES / value).resolve()
            assert target.is_relative_to(SOURCES), value
            return target

        ids = set()
        originals = set()
        for entry in redraw_data['images']:
            assert isinstance(entry, dict) and all(isinstance(entry.get(key), str) and entry[key]
                       for key in ('id', 'document', 'original', 'replacement', 'alt')), entry
            assert entry['id'] not in ids, ('duplicate redraw id', entry['id'])
            ids.add(entry['id'])
            document = source_path(entry['document'])
            original = source_path(entry['original'])
            assert (document, original) not in originals, ('duplicate redraw original', entry['id'])
            originals.add((document, original))
            redraws.setdefault(document, []).append((entry, original, source_path(entry['replacement'])))
    result = {}
    translation_cache = {}
    reading_cache = {}
    kaoyan_cache = {}
    for item in records:
        for mode, other in [('svg', 'reflow'), ('reflow', 'svg')]:
            target = (ROOT / item[mode]).resolve()
            assert target.is_relative_to(SOURCES), target
            alternate = (ROOT / item[other]).resolve()
            rel = lambda p: os.path.relpath(p, target.parent)
            config = {
                'title': item['title'], 'category': item['category'],
                'categoryLabel': item['categoryLabel'], 'year': item['year'],
                'documentId': item['id'], 'kind': item['kind'], 'mode': mode,
                'libraryHref': rel(ROOT / 'index.htm'),
                'categoryHref': rel(ROOT / item['category'] / 'index.htm'),
                'alternateHref': rel(alternate),
                'alternateLabel': 'SVG 原版' if other == 'svg' else 'LaTeX 重排',
            }
            if item['kind'] in {'questions', 'complete'}:
                config['fullPaperHref'] = f"{rel(ROOT / 'practice/full-paper.htm')}?paper={quote(item['id'], safe='')}"
            if mode == 'reflow':
                structured = ROOT / 'structured/papers' / item['category'] / (target.stem + '.json')
                if structured.exists():
                    paper = json.loads(structured.read_text(encoding='utf-8'))
                    toc = []
                    for entry in paper['toc']:
                        block_id = entry.get('sourceBlockId')
                        match = re.fullmatch(r'b-(\d+)-(\d+)', block_id or '')
                        if match:
                            toc.append({'label': entry['label'], 'level': entry['level'],
                                        'pageIndex': int(match.group(1)), 'blockIndex': int(match.group(2))})
                    config['structuredToc'] = toc
                    if item['kind'] != 'answers':
                        answer_items = []
                        for question in paper['questions']:
                            if question['recordType'] != 'question':
                                continue
                            source = question['answer']
                            answer = {key: source.get(key) for key in (
                                'status', 'value', 'solution', 'explanation', 'commentary',
                                'knowledge', 'ambiguityReason', 'sourceBlocks', 'sourceQuestionIds')}
                            source_doc = documents_by_id.get(source.get('sourceDocumentId'))
                            if source_doc:
                                answer['sourceHref'] = rel((ROOT / source_doc['reflow']).resolve())
                            answer_item = {'sourceBlocks': question['sourceBlocks'], 'answer': answer}
                            if item['category'] in {'kaoyan', 'math3', 'cs408', 'politics'}:
                                answer_item.update(questionId=question['id'], number=question['number'])
                            answer_items.append(answer_item)
                        config['structuredAnswers'] = answer_items
                if item['category'] in {'cet4', 'cet6'} and item['kind'] == 'questions':
                    source = (ROOT / item['svg']).resolve()
                    if source not in translation_cache:
                        translation_cache[source] = translation_paragraph_starts(source, target)
                    if translation_cache[source]:
                        config['translationParagraphStarts'] = translation_cache[source]
                    if source not in reading_cache:
                        reading_cache[source] = reading_paragraph_starts(source, target)
                    if reading_cache[source]:
                        config['readingParagraphStarts'] = reading_cache[source]
                if item['category'] == 'kaoyan' and item['kind'] == 'questions':
                    source = (ROOT / item['svg']).resolve()
                    if source not in kaoyan_cache:
                        kaoyan_cache[source] = kaoyan_source_layout(source)
                    config.update(kaoyan_cache[source])
            if mode == 'reflow' and target in redraws:
                config['imageRedraws'] = [
                    {'id': entry['id'], 'originalHref': rel(original),
                     'replacementHref': rel(replacement), 'alt': entry['alt']}
                    for entry, original, replacement in redraws[target]
                ]
            result[target] = config
    reflow_readers = {target for target, config in result.items() if config['mode'] == 'reflow'}
    assert set(redraws).issubset(reflow_readers), ('redraw document is not a reflow reader', set(redraws) - reflow_readers)
    _cache = (stamp, result)
    return result


def enhance_html(content, target):
    target = Path(target).resolve()
    config = registry().get(target)
    if not config:
        return content
    base = strip_ui(content)
    assert base.count('</head>') == base.count('</body>') == 1, target
    rel = lambda name: html.escape(os.path.relpath(ROOT / 'ui' / name, target.parent), quote=True)
    answers_path = ROOT / 'ui/answers.js'
    answers_href = rel('answers.js')
    if answers_path.is_file():
        answers_href += '?v=' + sha(answers_path.read_bytes())[:12]
    head = ('<!-- exam-ui:head -->'
            f'<link rel="stylesheet" href="{rel("tokens.css")}">'
            f'<link rel="stylesheet" href="{rel("reader.css")}">'
            f'<link rel="stylesheet" href="{rel("material.css")}">'
            f'<link rel="stylesheet" href="{rel("code-highlight.css")}">'
            f'<link rel="stylesheet" href="{rel("answers.css")}">'
            '<!-- /exam-ui:head -->')
    payload = json.dumps(config, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    technical = (f'<script defer src="{rel("technical-subquestions.js")}"></script>'
                 if config['category'] == 'cs408' and config['mode'] == 'reflow' and config['kind'] != 'answers'
                 else '')
    body = ('<!-- exam-ui:body -->'
            f'<script type="application/json" id="exam-reader-config">{payload}</script>'
            f'<script defer src="{rel("code-highlight.js")}"></script>'
            f'{technical}'
            f'<script defer src="{rel("answer-math.js")}"></script>'
            f'<script defer src="{answers_href}"></script>'
            f'<script defer src="{rel("reader.js")}"></script>'
            '<!-- /exam-ui:body -->')
    updated = base.replace('</head>', head + '</head>').replace('</body>', body + '</body>')
    assert strip_ui(updated) == base, target
    return updated


def write_reader(target, content, **kwargs):
    """Use in generators in place of target.write_text(content)."""
    target = Path(target)
    target.write_text(enhance_html(content, target), **kwargs)


def update_manifest(folder, changed):
    path = folder / 'manifest.json'
    if not path.exists():
        return 0
    data = json.loads(path.read_text())
    count = 0

    def visit(node):
        nonlocal count
        if isinstance(node, list):
            for child in node:
                visit(child)
        elif isinstance(node, dict):
            value = node.get('htm', node.get('file'))
            if isinstance(value, str) and value.endswith(('.htm', '.html')):
                target = (folder / value).resolve()
                if target in changed:
                    key = 'htm_sha256' if 'htm_sha256' in node else 'sha256' if 'htm' in node and 'sha256' in node else None
                    if key:
                        node[key] = changed[target]
                        count += 1
            for child in node.values():
                if isinstance(child, (dict, list)):
                    visit(child)

    visit(data)
    if count:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    return count


def write_source_notices():
    """Keep full-paper practice warnings identical to source reader notices.

    Notices are presentation metadata, not question text or invented answers.
    Include warnings from linked answer papers, which full-paper practice can
    reveal inline without showing their original page header.
    """
    records = [item for item in json.loads((ROOT / 'documents.json').read_text())
               if item['category'] in {'kaoyan', 'math3', 'cs408', 'politics'}]
    own_notes = {}
    for item in records:
        source = (ROOT / item['reflow']).resolve()
        soup = BeautifulSoup(source.read_text(encoding='utf-8'), 'html.parser')
        own_notes[item['id']] = [p.get_text(' ', strip=True)
                                 for p in soup.select('header aside.notice p')]
    notices = {}
    for item in records:
        notes = list(own_notes[item['id']])
        source = (ROOT / item['reflow']).resolve()
        structured = ROOT / 'structured/papers' / item['category'] / (source.stem + '.json')
        if structured.exists() and item['kind'] != 'answers':
            paper = json.loads(structured.read_text())
            answer_ids = sorted({q.get('answer', {}).get('sourceDocumentId')
                                 for q in paper['questions']
                                 if q.get('answer', {}).get('sourceDocumentId')})
            for answer_id in answer_ids:
                if answer_id != item['id']:
                    notes.extend('参考答案原稿：' + note for note in own_notes.get(answer_id, []))
        if notes:
            notices[item['id']] = list(dict.fromkeys(notes))
    payload = {'schema': 'exam-source-notices-v1', 'papers': notices}
    (ROOT / 'source-notices.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return len(notices)


def enhance_selected_readers(categories):
    """Refresh selected readers after their structured papers are rebuilt.

    A standalone source generator cannot know whether the existing structured
    paper is current. Run this after building the structured papers, so the
    embedded navigation and answer metadata come from the same generation.
    Only selected source HTML and corresponding source manifests are written;
    unrelated subjects, structured papers, and the database are not.
    """
    categories = set(categories)
    if not categories:
        raise ValueError('select at least one category')
    records = {target: config for target, config in registry().items()
               if config['category'] in categories}
    found = {config['category'] for config in records.values()}
    if found != categories:
        raise ValueError(f'unknown or missing categories: {sorted(categories - found)}')
    changed = {}
    updated = 0
    for target in records:
        before = target.read_text(encoding='utf-8')
        after = enhance_html(before, target)
        assert strip_ui(after) == strip_ui(before), target
        assert enhance_html(after, target) == after, ('not idempotent', target)
        if after != before:
            target.write_text(after, encoding='utf-8')
            updated += 1
        changed[target] = sha(after.encode('utf-8'))
    manifests = 0
    for folder in sorted({SOURCES / target.relative_to(SOURCES).parts[0]
                          for target in changed}):
        count = update_manifest(folder, changed)
        expected = sum(target.is_relative_to(folder) for target in changed)
        assert count == expected, ('unrecorded reader hash', folder, count, expected)
        manifests += count
    if categories & {'kaoyan', 'math3', 'cs408', 'politics'}:
        write_source_notices()
    return {'readers': len(records), 'updated': updated,
            'manifestHashesUpdated': manifests}


def enhance_all(check_baseline=False):
    required = [ROOT / 'ui' / name for name in ['tokens.css', 'reader.css', 'material.css', 'reader.js', 'code-highlight.css', 'code-highlight.js', 'answers.css', 'answers.js', 'answer-math.js', 'vendor/mathjax-3.2.2-tex-svg-full.js', 'technical-subquestions.js']]
    if not all(p.exists() for p in required):
        return {'status': 'waiting-for-reader-assets'}
    records = registry()
    assert len(records) == 670, ('reader coverage', len(records))
    baseline_path = ROOT / 'work/before-ui-redesign/reader-baseline.json'
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    changed = {}
    checks = []
    for target, config in records.items():
        before = target.read_text()
        after = enhance_html(before, target)
        base = strip_ui(after)
        key = str(target.relative_to(SOURCES))
        if check_baseline and key in baseline:
            assert sha(base.encode()) == baseline[key]['sha256'], ('unexpected exam content modification', key)
        assert enhance_html(after, target) == after, ('not idempotent', key)
        if after != before:
            target.write_text(after)
        changed[target] = sha(after.encode())
        for field in ['libraryHref', 'categoryHref', 'alternateHref']:
            assert (target.parent / config[field]).is_file(), (key, field)
        checks.append({'file': key, 'mode': config['mode'], 'sha256': changed[target],
                       'original_html_sha256': sha(base.encode()), 'original_html_unchanged': key in baseline and sha(base.encode()) == baseline[key]['sha256']})
    count = 0
    for folder in sorted({SOURCES / p.relative_to(SOURCES).parts[0] for p in records}):
        manifest = folder / 'manifest.json'
        backup = ROOT / 'work/before-ui-redesign/manifests' / folder.name / 'manifest.json'
        if manifest.exists() and not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(manifest.read_bytes())
        count += update_manifest(folder, changed)
    report = {'reader_pages': len(checks), 'html_hash_records_updated': count,
              'source_notice_papers': write_source_notices(),
              'exam_html_byte_preserved': all(c['original_html_unchanged'] for c in checks),
              'injection_idempotent': True, 'browser_tested': False, 'checks': checks}
    (ROOT / 'ui-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print('Reader shell:', len(checks), 'pages;', count, 'HTML manifest hashes reconciled')
    return report


if __name__ == '__main__':
    import sys
    if '--english-only' in sys.argv:
        if len(sys.argv) != 2:
            raise SystemExit('usage: enhance_readers.py --english-only')
        result = enhance_selected_readers(ENGLISH_CATEGORIES)
        assert result['readers'] == 412, result
        print('English reader shell:', result)
    else:
        enhance_all(check_baseline='--verify-baseline' in sys.argv)
