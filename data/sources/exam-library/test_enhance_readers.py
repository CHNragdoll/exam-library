"""Regression checks for source-backed reader metadata."""

from pathlib import Path
import hashlib
import json
import os
import re
import tempfile
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from enhance_readers import (ROOT, ENGLISH_CATEGORIES, enhance_html,
                             enhance_selected_readers, registry, strip_ui,
                             translation_paragraph_starts)


SOURCES = Path(__file__).resolve().parent.parent


class TranslationParagraphStartsTest(unittest.TestCase):
    def starts(self, paper):
        original = SOURCES / 'english-exams-web-2026-09-26/cet6/papers' / paper
        reflow = SOURCES / 'english-exams-reflow-latex/cet6/papers' / paper
        return translation_paragraph_starts(original, reflow)

    def test_chinese_passage_keeps_original_two_paragraph_starts(self):
        self.assertEqual(self.starts('2015-12-02.htm'), [
            '最近，中国政府决定将其工',
            '中国造产品越来越受欢迎。',
        ])

    def test_sentence_completion_does_not_use_answer_explanations(self):
        self.assertEqual(self.starts('2012-12-02.htm'), [])


class FullPaperReaderLinkTest(unittest.TestCase):
    def test_only_question_readers_receive_document_specific_relative_links(self):
        records = registry()
        self.assertEqual(len(records), 670)
        for target, config in records.items():
            with self.subTest(document=config['documentId'], mode=config['mode']):
                href = config.get('fullPaperHref')
                if config['kind'] not in {'questions', 'complete'}:
                    self.assertIsNone(href)
                    continue
                self.assertIsNotNone(href)
                parts = urlsplit(href)
                self.assertFalse(parts.scheme or parts.netloc or parts.fragment)
                self.assertEqual((target.parent / parts.path).resolve(),
                                 ROOT / 'practice/full-paper.htm')
                self.assertEqual(parse_qs(parts.query), {'paper': [config['documentId']]})

    def test_408_and_politics_both_versions_embed_the_link_without_changing_exam_markup(self):
        documents = {item['id']: item for item in json.loads((ROOT / 'documents.json').read_text())}
        for document_id in ('cs408:2023-questions', 'politics:2023-questions',
                            'cs408:2023-answers', 'politics:2023-answers'):
            document = documents[document_id]
            for mode in ('svg', 'reflow'):
                with self.subTest(document=document_id, mode=mode):
                    target = (ROOT / document[mode]).resolve()
                    original = target.read_text()
                    enhanced = enhance_html(original, target)
                    material_href = os.path.relpath(ROOT / 'ui/material.css', target.parent)
                    self.assertEqual(enhanced.count(f'<link rel="stylesheet" href="{material_href}">'), 1)
                    payload = re.search(r'<script type="application/json" id="exam-reader-config">([^<]*)</script>',
                                        enhanced)
                    self.assertIsNotNone(payload)
                    config = json.loads(payload.group(1))
                    self.assertEqual(config['documentId'], document_id)
                    self.assertEqual('fullPaperHref' in config, document['kind'] in {'questions', 'complete'})
                    self.assertEqual(enhance_html(enhanced, target), enhanced)


class SelectedEnglishReaderRefreshTest(unittest.TestCase):
    def test_refresh_writes_only_selected_readers_and_their_manifest_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = Path(tmp).resolve()
            base = '<!doctype html><html><head></head><body><main>Exam text</main></body></html>'
            records = {}
            names = (
                ('english-exams-web', 'cet6', 'svg'),
                ('english-exams-reflow-latex', 'cet6', 'reflow'),
                ('politics-original', 'politics', 'svg'),
            )
            for folder, category, mode in names:
                target = sources / folder / category / 'papers' / 'one.htm'
                target.parent.mkdir(parents=True)
                target.write_text(base, encoding='utf-8')
                records[target] = {
                    'title': 'Exam', 'category': category, 'categoryLabel': category,
                    'year': 2026, 'documentId': f'{category}:one', 'kind': 'questions',
                    'mode': mode, 'libraryHref': '#', 'categoryHref': '#',
                    'alternateHref': '#', 'alternateLabel': 'alternate',
                    'structuredToc': [{'label': 'old', 'level': 0,
                                       'pageIndex': 1, 'blockIndex': 1}],
                }
                (sources / folder / 'manifest.json').write_text(json.dumps({
                    'papers': [{'file': f'{category}/papers/one.htm', 'htm_sha256': 'old'}]
                }), encoding='utf-8')
            with (mock.patch('enhance_readers.SOURCES', sources),
                  mock.patch('enhance_readers.registry', return_value=records)):
                for target in records:
                    target.write_text(enhance_html(base, target), encoding='utf-8')
                politics = next(target for target, config in records.items()
                                if config['category'] == 'politics')
                politics_before = politics.read_bytes()
                politics_manifest = sources / 'politics-original/manifest.json'
                politics_manifest_before = politics_manifest.read_bytes()
                for config in records.values():
                    if config['category'] == 'cet6':
                        config['structuredToc'][0]['label'] = 'current'
                result = enhance_selected_readers({'cet6'})
                self.assertEqual(result, {'readers': 2, 'updated': 2,
                                          'manifestHashesUpdated': 2})
                for target, config in records.items():
                    if config['category'] != 'cet6':
                        continue
                    content = target.read_text(encoding='utf-8')
                    self.assertEqual(strip_ui(content), base)
                    self.assertEqual(json.loads(re.search(
                        r'<script type="application/json" id="exam-reader-config">([^<]*)</script>',
                        content).group(1))['structuredToc'][0]['label'], 'current')
                    manifest = json.loads((sources / target.relative_to(sources).parts[0] /
                                           'manifest.json').read_text(encoding='utf-8'))
                    self.assertEqual(manifest['papers'][0]['htm_sha256'],
                                     hashlib.sha256(target.read_bytes()).hexdigest())
                self.assertEqual(politics.read_bytes(), politics_before)
                self.assertEqual(politics_manifest.read_bytes(), politics_manifest_before)
                self.assertEqual(enhance_selected_readers({'cet6'})['updated'], 0)

    def test_live_english_config_uses_the_current_structured_toc(self):
        records = registry()
        english = [config for config in records.values()
                   if config['category'] in ENGLISH_CATEGORIES]
        self.assertEqual(len(english), 412)
        target = next(target for target, config in records.items()
                      if config['documentId'] == 'cet6:2026-06-02'
                      and config['mode'] == 'reflow')
        paper = json.loads((ROOT / 'structured/papers/cet6/2026-06-02.json').read_text())
        refreshed = enhance_html(target.read_text(encoding='utf-8'), target)
        config = json.loads(re.search(
            r'<script type="application/json" id="exam-reader-config">([^<]*)</script>',
            refreshed).group(1))
        self.assertEqual(len(config['structuredToc']), len(paper['toc']))
        self.assertIn('Writing', [item['label'] for item in config['structuredToc']])
        self.assertIn('Translation', [item['label'] for item in config['structuredToc']])


if __name__ == '__main__':
    unittest.main()
