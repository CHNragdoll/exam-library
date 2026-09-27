"""Read-only checks of the published catalog and its local reader resources."""
from pathlib import Path
from urllib.parse import urlsplit, unquote
import argparse
import json
import subprocess
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'data/sources/exam-library'


def verify(tracked=False):
    documents = json.loads((CATALOG / 'documents.json').read_text())
    assert len(documents) == 335, len(documents)
    readers = {(CATALOG / row[mode]).resolve() for row in documents for mode in ('svg', 'reflow')}
    assert len(readers) == 670
    tracked_files = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')) if tracked else None
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
    result = {'documents': len(documents), 'reader_pages': len(readers), 'checked_pages': len(pages), 'local_resources': checked, 'tracked_resources_checked': tracked, 'browser_tested': False}
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tracked', action='store_true')
    args = parser.parse_args()
    verify(args.tracked)
