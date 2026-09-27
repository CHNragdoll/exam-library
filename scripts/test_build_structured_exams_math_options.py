"""Focused display checks for structured mathematics choices."""

import unittest
from pathlib import Path

from bs4 import BeautifulSoup

from scripts.build_structured_exams import display_block, options_from


class MathOptionDisplayTests(unittest.TestCase):
    def test_source_choice_order_is_available_before_default_order_normalization(self):
        source = BeautifulSoup('''<div class="math-options">
          <div class="math-option"><span class="math-option-label">(B)</span>second</div>
          <div class="math-option"><span class="math-option-label">(A)</span>first</div>
        </div>''', "html.parser").div
        self.assertEqual([option["label"] for option in options_from(source)], ["B.", "A."])

    def render(self, markup: str, math_questions: bool = False):
        source = BeautifulSoup(markup, "html.parser").div
        original = str(source)
        rendered = BeautifulSoup(display_block(source, Path("source.htm"), Path("review.htm"),
                                                 math_questions=math_questions), "html.parser").div
        self.assertEqual(str(source), original)
        return source, rendered

    def test_short_choices_use_four_columns_and_keep_source_data(self):
        source, rendered = self.render('''<div class="math-options">
          <div class="math-option"><span class="math-option-label">（A）</span><span class="math-option-content">1.5.</span></div>
          <div class="math-option"><span class="math-option-label">(B)</span><span class="math-option-content"><span class="formula" data-tex="(-\\infty,-4)"><mjx-container><svg width="9.68ex"></svg></mjx-container></span>.</span></div>
          <div class="math-option"><span class="math-option-label">（C）</span><span class="math-option-content">3。　</span></div>
          <div class="math-option"><span class="math-option-label">(D)</span><span class="math-option-content">4．</span></div>
        </div>''')
        self.assertIn("compact-math-options", rendered["class"])
        self.assertEqual([node.get_text(strip=True) for node in rendered.select(".math-option-label")],
                         ["A.", "B.", "C.", "D."])
        self.assertEqual([node.get_text(strip=True) for node in rendered.select(".math-option-content")],
                         ["1.5", "", "3", "4"])
        self.assertEqual(rendered.select_one(".formula")["data-tex"], "(-\\infty,-4)")
        self.assertEqual(options_from(source)[0], {"label": "A.", "sourceLabel": "（A）", "text": "1.5."})

    def test_long_choices_stay_in_two_column_layout(self):
        _, rendered = self.render('''<div class="math-options">
          <div class="math-option"><span class="math-option-label">（A）</span><span class="math-option-content">函数在区间内有两个极值点。</span></div>
          <div class="math-option"><span class="math-option-label">（B）</span><span class="math-option-content">另一个较长的选择内容。</span></div>
          <div class="math-option"><span class="math-option-label">（C）</span><span class="math-option-content">3。</span></div>
          <div class="math-option"><span class="math-option-label">（D）</span><span class="math-option-content">4。</span></div>
        </div>''')
        self.assertNotIn("compact-math-options", rendered["class"])
        self.assertEqual(rendered.select_one(".math-option-content").get_text(strip=True), "函数在区间内有两个极值点")

    def test_only_math_question_final_stop_changes(self):
        markup = '''<div class="paragraph question">（12）已知 <span class="formula" data-tex="x^2.0"><mjx-container><svg width="4ex"></svg></mjx-container></span>，则结果是（　）。</div>'''
        source, rendered = self.render(markup, math_questions=True)
        self.assertEqual(rendered.select_one(".math-question-number")["data-digits"], "2")
        self.assertEqual(rendered.select_one(".math-question-number").get_text(), "（12）")
        self.assertTrue(rendered.get_text(strip=True).endswith("（　）."))
        self.assertEqual(rendered.select_one(".formula")["data-tex"], "x^2.0")
        self.assertTrue(source.get_text(strip=True).endswith("（　）。"))
        _, other = self.render(markup)
        self.assertTrue(other.get_text(strip=True).endswith("（　）。"))


if __name__ == "__main__":
    unittest.main()
