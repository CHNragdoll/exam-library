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

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT.parent
MARKERS = re.compile(r'<!-- exam-ui:(head|body) -->.*?<!-- /exam-ui:\1 -->', re.S)
_cache = (None, {})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def strip_ui(content):
    return MARKERS.sub('', content)


def registry():
    global _cache
    path = ROOT / 'documents.json'
    redraw_path = ROOT / 'image-redraws.json'
    if not path.exists():
        return {}
    stamp = (path.stat().st_mtime_ns,
             redraw_path.stat().st_mtime_ns if redraw_path.exists() else None)
    if _cache[0] == stamp:
        return _cache[1]
    data = json.loads(path.read_text())
    records = data if isinstance(data, list) else data['documents']
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
    head = ('<!-- exam-ui:head -->'
            f'<link rel="stylesheet" href="{rel("tokens.css")}">'
            f'<link rel="stylesheet" href="{rel("reader.css")}">'
            '<!-- /exam-ui:head -->')
    payload = json.dumps(config, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    body = ('<!-- exam-ui:body -->'
            f'<script type="application/json" id="exam-reader-config">{payload}</script>'
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


def enhance_all(check_baseline=False):
    required = [ROOT / 'ui' / name for name in ['tokens.css', 'reader.css', 'reader.js']]
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
              'exam_html_byte_preserved': all(c['original_html_unchanged'] for c in checks),
              'injection_idempotent': True, 'browser_tested': False, 'checks': checks}
    (ROOT / 'ui-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print('Reader shell:', len(checks), 'pages;', count, 'HTML manifest hashes reconciled')
    return report


if __name__ == '__main__':
    import sys
    enhance_all(check_baseline='--verify-baseline' in sys.argv)
