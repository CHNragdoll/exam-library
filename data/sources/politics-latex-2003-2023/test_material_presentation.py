"""Keep printed politics material labels and attributions easy to scan."""

from pathlib import Path
import unittest

from bs4 import BeautifulSoup

from build import material_paragraph_class, visible_material_parts, visible_question_text


ROOT = Path(__file__).resolve().parent


class MaterialPresentationTests(unittest.TestCase):
    def test_classification_uses_complete_source_paragraphs(self):
        self.assertEqual(material_paragraph_class("材料1"), "paragraph material-label")
        self.assertEqual(material_paragraph_class("材料 2"), "paragraph material-label")
        self.assertEqual(material_paragraph_class("摘自《邓小平文选》第二卷"),
                         "paragraph material-source")
        self.assertEqual(material_paragraph_class("摘编自《人民日报》（2022年）"),
                         "paragraph material-source")
        self.assertEqual(material_paragraph_class("材料2提出的政策"), "paragraph")
        self.assertEqual(material_paragraph_class("摘自原文的句子说明……"), "paragraph")
        self.assertEqual(visible_question_text("第36题（续）：材料3"), "材料3")
        self.assertEqual(visible_material_parts(["第36题（续）：", "材料3 2022年1月30日，讲话指出。"]),
                         [("第36题（续）：", ""), ("", "材料3"),
                          ("", "2022年1月30日，讲话指出。")])

    def test_2023_question_36_and_peer_materials_render_as_separate_paragraphs(self):
        soup = BeautifulSoup((ROOT / "papers/2023-questions.htm").read_text(), "html.parser")
        page8 = soup.select_one('main > section[data-source-page="8"]')
        page9 = soup.select_one('main > section[data-source-page="9"]')
        self.assertEqual([p.get_text(" ", strip=True) for p in page8.select("p.material-label")],
                         ["材料1", "材料2"])
        self.assertEqual([p.get_text(" ", strip=True) for p in page9.select("p.material-label")],
                         ["材料3", "材料1"])
        for marker in ("摘自《毛泽东文集》第三卷", "摘自《邓小平文选》第二卷"):
            self.assertEqual(len([p for p in page8.select("p.material-source")
                                  if p.get_text(" ", strip=True) == marker]), 1)
        self.assertTrue(any(p.get_text(" ", strip=True).startswith("摘自《习近平谈治国理政》")
                            for p in page9.select("p.material-source")))
        self.assertFalse(any("-8 -" in p.get_text(" ", strip=True)
                             for p in page8.select("p.paragraph")))

    def test_2022_peer_materials_use_same_classes(self):
        soup = BeautifulSoup((ROOT / "papers/2022-questions.htm").read_text(), "html.parser")
        self.assertTrue(soup.select("p.material-label"))
        self.assertTrue(soup.select("p.material-source"))


if __name__ == "__main__":
    unittest.main()
