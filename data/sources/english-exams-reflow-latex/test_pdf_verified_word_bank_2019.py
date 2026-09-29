"""Keep every printed CET-6 2019-06 Set 1 word-bank choice."""
import copy
import json
import unittest

import build


def item(label, word):
    return {'label': label, 'runs': [{'text': word, 'flags': [False, False, False]}]}


class WordBank2019Test(unittest.TestCase):
    def test_two_printed_words_are_restored_in_label_order(self):
        blocks = [
            {'type': 'options', 'items': [item(*pair) for pair in
                [('A', 'adverse'), ('B', 'championed'),
                 ('I', 'minimum'), ('J', 'radiating')]]},
            {'type': 'paragraph', 'runs': [{'text': 'C clinical K) ration',
                                           'flags': [False, False, False]}]},
            {'type': 'options', 'items': [item(*pair) for pair in
                [('D', 'contrary'), ('E', 'contribute'), ('F', 'intimate'),
                 ('G', 'lumped'), ('H', 'magnified'), ('L', 'shooting'),
                 ('M', 'subscribe'), ('N', 'systematic'), ('O', 'weighing')]]},
        ]
        build.repair_cet6_2019_06_01_word_bank('cet6', '2019-06-01', 3, blocks)
        self.assertEqual(len(blocks), 1)
        self.assertEqual([choice['label'] for choice in blocks[0]['items']], list('ABCDEFGHIJKLMNO'))
        self.assertEqual(build.plain_text(blocks[0]['items'][2]), 'clinical')
        self.assertEqual(build.plain_text(blocks[0]['items'][10]), 'ration')

    def test_other_papers_are_untouched(self):
        blocks = [{'type': 'paragraph', 'runs': [{'text': 'C clinical K) ration',
                                                'flags': [False, False, False]}]}]
        build.repair_cet6_2019_06_01_word_bank('cet6', '2019-06-02', 3, blocks)
        self.assertEqual(len(blocks), 1)

    def test_cet4_2021_12_02_printed_o_is_not_left_inside_g(self):
        words = ['captured', 'classical', 'conclusively', 'emergence', 'exact',
                 'generated', 'particular 0) systematically', 'position',
                 'precision', 'probably', 'quality', 'scarcity', 'senior', 'separated']
        blocks = [{'type': 'options', 'items': [item(label, word)
                   for label, word in zip('ABCDEFGHIJKLMN', words)]}]
        blocks[0]['items'][6]['runs'] = [
            {'text': text, 'flags': (bold, False, False)}
            for text, bold in [('particular', True), (' ', False),
                               ('0) systematically', True)]]
        build.repair_pdf_verified_word_bank('cet4', '2021-12-02', 4, blocks)
        choices = blocks[0]['items']
        self.assertEqual([choice['label'] for choice in choices], list('ABCDEFGHIJKLMNO'))
        self.assertEqual(build.plain_text(choices[6]), 'particular')
        self.assertEqual(build.plain_text(choices[14]), 'systematically')

    def test_cet4_2020_12_01_pdf_prints_separate_j_and_o(self):
        archive = build.ROOT.parent / 'english-exams-web-2026-09-26'
        manifest = json.loads((archive / 'manifest.json').read_text())
        entry = next(entry for entry in manifest['papers']
                     if entry['category'] == 'cet4' and entry['file'].endswith('2020-12-01.htm'))
        expected_pdf_hash = '5ae3d9b5333e3cf3d02922dc4bc329e016dd2c3738307fe12a525a4e55535f37'
        self.assertEqual(entry['source_pdf_sha256'], expected_pdf_hash)
        self.assertEqual(build.sha(build.source_pdf(entry)), expected_pdf_hash)

        words = ['constantly', 'credible', 'essential', 'exploring', 'gather',
                 'load', 'miserable', 'pressure', 'properly', 'records 0) watching',
                 'removed', 'stacks', 'suspicion', 'tracked']
        blocks = [{'type': 'options', 'items': [item(label, word)
                   for label, word in zip('ABCDEFGHIJKLMN', words)]}]
        blocks[0]['items'][9]['runs'] = [
            {'text': text, 'flags': flags} for text, flags in [
                ('records', [True, False, False]),
                (' ', [False, False, False]),
                ('0) watching', [True, False, False])]]
        original = copy.deepcopy(blocks)
        build.repair_pdf_verified_word_bank('cet4', '2020-12-01', 4, blocks)
        choices = blocks[0]['items']
        self.assertEqual([choice['label'] for choice in choices], list('ABCDEFGHIJKLMNO'))
        self.assertEqual(build.plain_text(choices[9]), 'records')
        self.assertEqual(build.plain_text(choices[14]), 'watching')
        self.assertEqual(choices[9]['runs'][0]['flags'], [True, False, False])
        self.assertEqual(choices[14]['runs'][0]['flags'], [True, False, False])
        self.assertEqual(choices[:9], original[0]['items'][:9])
        self.assertEqual(choices[10:14], original[0]['items'][10:14])

    def test_cet4_2020_12_01_wrong_merged_word_rejects_repair(self):
        blocks = [{'type': 'options', 'items': [item(label, 'records 0) watching'
                   if label == 'J' else label)
                   for label in 'ABCDEFGHIJKLMN']}]
        with self.assertRaises(AssertionError):
            build.repair_pdf_verified_word_bank('cet4', '2020-12-01', 4, blocks)


if __name__ == '__main__':
    unittest.main()
