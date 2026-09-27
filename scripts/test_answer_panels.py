"""Focused checks for structured review answer states and source links."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from scripts import build_structured_exams as builder


class AnswerPanelTests(unittest.TestCase):
    def test_every_question_gets_a_collapsed_panel(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            folder = output / 'papers/math3'
            folder.mkdir(parents=True)
            question_id = 'math3:fixture-questions'
            answer_id = 'math3:fixture-answers'
            empty = lambda: {
                'status': 'missing', 'value': None, 'solution': None,
                'explanation': None, 'commentary': None, 'knowledge': None,
                'sourceDocumentId': None, 'sourceQuestionIds': [],
                'sourceBlocks': [], 'sourcePages': [],
            }
            questions = [
                {'id': f'q-{number}-1', 'number': str(number), 'recordType': 'question',
                 'answer': empty()} for number in range(1, 4)
            ]
            question_paper = {'id': question_id, 'category': 'math3', 'kind': 'questions',
                              'questions': questions, 'audit': {}}
            answer_paper = {'id': answer_id, 'category': 'math3', 'kind': 'answers',
                            'questions': [], 'blocks': [{'id': 'b-1-1', 'page': '1'}]}
            (folder / 'fixture-questions.json').write_text(json.dumps(question_paper))
            (folder / 'fixture-answers.json').write_text(json.dumps(answer_paper))
            (folder / 'fixture-questions.htm').write_text(
                '<html><body><main>' + ''.join(
                    f'<article class="question-card" id="q-{number}-1"><p>第 {number} 题</p></article>'
                    for number in range(1, 4)) + '</main></body></html>')
            rows = [
                {'id': question_id, 'json': 'papers/math3/fixture-questions.json',
                 'reader': 'papers/math3/fixture-questions.htm'},
                {'id': answer_id, 'json': 'papers/math3/fixture-answers.json',
                 'reader': 'papers/math3/fixture-answers.htm'},
            ]
            source = {
                '1': {'value': 'B', 'solution': '步骤一\n步骤二', 'explanation': '解析文本',
                      'commentary': '点评文本', 'knowledge': '知识文本',
                      'sourceQuestionIds': ['a-1'], 'sourceBlocks': ['b-1-1']},
                '3': {'value': 'C', 'solution': None, 'explanation': None,
                      'commentary': None, 'knowledge': None,
                      'sourceQuestionIds': ['a-3', 'a-3-duplicate'], 'sourceBlocks': ['b-1-1']},
            }
            with patch.object(builder, 'OUT', output), patch.object(builder, 'answer_entries', return_value=source):
                builder.attach_answers(rows)
            soup = BeautifulSoup((folder / 'fixture-questions.htm').read_text(), 'html.parser')
            cards = soup.select('.question-card')
            self.assertEqual(len(cards), 3)
            self.assertTrue(all(card.select_one('details.answer-panel') for card in cards))
            self.assertTrue(all(not card.select_one('details.answer-panel').has_attr('open') for card in cards))
            self.assertTrue(all(card.select_one('summary').get_text() == '点击查看答案' for card in cards))
            self.assertEqual([node.get_text() for node in cards[0].select('.answer-field strong')],
                             ['标准答案', '解答过程', '解析', '点评', '考点知识'])
            self.assertIn('步骤一\n步骤二', cards[0].get_text())
            self.assertEqual(cards[0].select_one('.answer-source')['href'], 'fixture-answers.htm#a-1')
            self.assertIn('暂无可用答案', cards[1].get_text())
            self.assertIn('题号在试卷或答案中重复', cards[2].get_text())
            self.assertFalse(cards[1].select_one('.answer-source'))
            self.assertFalse(cards[2].select_one('.answer-source'))
            self.assertTrue(soup.select_one('script[src$="answer-math.js"]'))
            linked = json.loads((folder / 'fixture-questions.json').read_text())
            self.assertEqual([q['answer']['status'] for q in linked['questions']],
                             ['explicit', 'missing', 'ambiguous'])


if __name__ == '__main__':
    unittest.main()
