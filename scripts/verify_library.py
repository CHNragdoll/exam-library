"""Read-only checks of the published catalog and its local reader resources."""
from pathlib import Path
from urllib.parse import urlsplit, unquote
import argparse
import json
import os
import subprocess
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'data/sources/exam-library'
SOURCES = ROOT / 'data/sources'


def verify(tracked=False):
    documents = json.loads((CATALOG / 'documents.json').read_text())
    assert len(documents) == 335, len(documents)
    readers = {(CATALOG / row[mode]).resolve() for row in documents for mode in ('svg', 'reflow')}
    assert len(readers) == 670
    tracked_files = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')) if tracked else None
    reflow_readers = {(CATALOG / row['reflow']).resolve() for row in documents}
    redraw_manifest = CATALOG / 'image-redraws.json'
    redraws = {}
    if redraw_manifest.exists():
        if tracked:
            assert str(redraw_manifest.relative_to(ROOT)) in tracked_files, ('unpublished redraw manifest', redraw_manifest)
        payload = json.loads(redraw_manifest.read_text())
        assert isinstance(payload, dict) and payload.get('version') == 1 and isinstance(payload.get('images'), list)

        def source_reference(value):
            assert isinstance(value, str) and value and not Path(value).is_absolute(), value
            target = (SOURCES / value).resolve()
            assert target.is_relative_to(SOURCES), ('redraw path outside sources', value)
            assert target.is_file(), ('missing redraw resource', value)
            if tracked:
                assert str(target.relative_to(ROOT)) in tracked_files, ('unpublished redraw resource', value)
            return target

        ids = set()
        originals = set()
        figure_sources_by_document = {}
        for entry in payload['images']:
            assert isinstance(entry, dict) and all(isinstance(entry.get(key), str) and entry[key]
                                                  for key in ('id', 'document', 'original', 'replacement', 'alt')), entry
            assert entry['id'] not in ids, ('duplicate redraw id', entry['id'])
            ids.add(entry['id'])
            document = source_reference(entry['document'])
            original = source_reference(entry['original'])
            replacement = source_reference(entry['replacement'])
            assert document in reflow_readers, ('redraw document is not a reflow reader', entry['document'])
            assert original != replacement, ('redraw equals original', entry['id'])
            assert (document, original) not in originals, ('duplicate redraw original', entry['id'])
            originals.add((document, original))
            if document not in figure_sources_by_document:
                figure_sources_by_document[document] = {
                    (document.parent / unquote(urlsplit(src).path)).resolve()
                    for src in html.fromstring(document.read_text()).xpath('//main//figure//img[not(ancestor::picture)]/@src')
                    if not urlsplit(src).scheme and not urlsplit(src).netloc and urlsplit(src).path
                }
            figure_sources = figure_sources_by_document[document]
            assert original in figure_sources, ('redraw original is not a figure image', entry['id'])
            relative = lambda path: os.path.relpath(path, document.parent)
            redraws.setdefault(document, []).append({
                'id': entry['id'], 'originalHref': relative(original),
                'replacementHref': relative(replacement), 'alt': entry['alt'],
            })
    pages = readers | {p.resolve() for p in CATALOG.rglob('*.htm') if 'work' not in p.relative_to(CATALOG).parts}
    checked = 0
    for page in sorted(pages):
        assert page.is_file(), page
        if tracked:
            assert str(page.relative_to(ROOT)) in tracked_files, ('untracked page', page)
        tree = html.fromstring(page.read_text())
        for value in tree.xpath('//@href | //@src'):
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (page.parent / unquote(parsed.path)).resolve()
            assert target.is_file(), ('broken local resource', str(page), value)
            assert target.is_relative_to(ROOT), ('outside project', str(page), value)
            if tracked:
                assert str(target.relative_to(ROOT)) in tracked_files, ('unpublished resource', str(page), value)
            checked += 1
    for row in documents:
        for mode, other in [('svg', 'reflow'), ('reflow', 'svg')]:
            page = (CATALOG / row[mode]).resolve()
            tree = html.fromstring(page.read_text())
            config = json.loads(tree.get_element_by_id('exam-reader-config').text)
            assert config['mode'] == mode
            assert (page.parent / config['alternateHref']).resolve() == (CATALOG / row[other]).resolve()
            if mode == 'reflow':
                assert config.get('imageRedraws', []) == redraws.get(page, []), ('stale redraw config', page)
            else:
                assert not config.get('imageRedraws'), ('redraws in SVG reader', page)
    result = {'documents': len(documents), 'reader_pages': len(readers), 'checked_pages': len(pages), 'local_resources': checked, 'image_redraws': sum(map(len, redraws.values())), 'tracked_resources_checked': tracked, 'browser_tested': False}
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tracked', action='store_true')
    args = parser.parse_args()
    verify(args.tracked)
