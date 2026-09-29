"""Printed CET option anomalies must not become complete three-choice cards."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build
from scripts import build_structured_exams as structured


SOURCE_ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = {item['id']: item for item in json.loads(
    (SOURCE_ROOT / 'exam-library/documents.json').read_text())}
ENTRIES = {item['file']: item for item in json.loads(
    (SOURCE_ROOT / 'english-exams-web-2026-09-26/manifest.json').read_text())['papers']}


class PdfVerifiedFourChoicesTest(unittest.TestCase):
    def build_question(self, category, stem, number, *, apply_repair=True):
        entry = ENTRIES[f'{category}/papers/{stem}.htm']
        document = DOCUMENTS[f'{category}:{stem}'].copy()
        repair = build.repair_pdf_verified_tail_choices if apply_repair else lambda *args: None
        with tempfile.TemporaryDirectory(dir=SOURCE_ROOT) as source_dir, \
                tempfile.TemporaryDirectory() as output_dir, \
                patch.object(build, 'ROOT', Path(source_dir)), \
                patch.object(build, 'write_reader', lambda target, content: target.write_text(content)), \
                patch.object(build, 'repair_pdf_verified_tail_choices', repair), \
                patch.object(structured, 'OUT', Path(output_dir)):
            build.make_paper(entry)
            paper_path = Path(source_dir) / entry['file']
            source = json.loads(paper_path.with_suffix('.json').read_text())
            document['reflow'] = os.path.relpath(paper_path, structured.ROOT)
            row = structured.build_one(document)
            paper = json.loads((Path(output_dir) / row['json']).read_text())
        questions = {question['number']: question for question in paper['questions']}
        return source, questions[number], questions[str(int(number) + 1)]

    def test_cet4_2014_12_question_61_keeps_printed_ad_label_as_uncertain_fourth_choice(self):
        source, question, following = self.build_question('cet4', '2014-12-01', '61')
        self.assertEqual([option['label'] for option in question['options']],
                         ['A.', 'B.', 'C.', 'D.'])
        self.assertEqual(question['options'][3]['sourceLabel'], 'AD)')
        self.assertEqual(question['options'][3]['text'],
                         'can hardly tear themselves away from the Internet')
        self.assertEqual(question['status'], 'partial')
        self.assertEqual(len(following['options']), 4)
        page = source['pages'][6]
        self.assertTrue(any(block['type'] == 'options' and len(block['items']) == 4
                            and block['items'][3].get('source_label') == 'AD)'
                            for block in page['blocks']))

    def test_cet6_2015_12_question_56_restores_stem_and_four_printed_choice_lines(self):
        source, question, following = self.build_question('cet6', '2015-12-01', '56')
        self.assertEqual(question['stem'],
                         '56. What do some most influential medical groups recommend doctors do?')
        self.assertEqual([option['label'] for option in question['options']],
                         ['A.', 'B.', 'C.', 'D.'])
        self.assertEqual([option['sourceLabel'] for option in question['options']],
                         ['56.', 'A)', 'B)', 'C)'])
        self.assertEqual([option['text'] for option in question['options']], [
            'Reflect on the responsibilities they are supposed to take.',
            'Pay more attention to the effectiveness of their treatments.',
            'Take costs into account when making treatment decisions.',
            'Readjust their practice in view of the cuts in health care.',
        ])
        self.assertEqual(question['status'], 'partial')
        self.assertEqual(len(following['options']), 4)
        page = source['pages'][6]
        self.assertEqual(sum('What do some most influential medical groups recommend doctors do?'
                             in ''.join(run['text'] for run in block.get('runs', []))
                             for block in page['blocks']), 1)

    def test_unrepaired_three_choice_cet_questions_cannot_be_marked_complete(self):
        for category, stem, number in [('cet4', '2014-12-01', '61'),
                                       ('cet6', '2015-12-01', '56')]:
            with self.subTest(category=category, stem=stem):
                _, question, _ = self.build_question(category, stem, number,
                                                     apply_repair=False)
                self.assertEqual(len(question['options']), 3)
                self.assertEqual(question['status'], 'partial')


if __name__ == '__main__':
    unittest.main()
