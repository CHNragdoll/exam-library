"""Regression checks for choice grouping in both Mathematics III reflow sets."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

from lxml import html


SOURCES = Path(__file__).resolve().parents[1]
SETS = ("math3-latex-1987-2009", "math3-latex-2009-2019")


def load_builder(directory):
    sys.path.insert(0, str(directory))
    try:
        spec = importlib.util.spec_from_file_location(directory.name.replace("-", "_"), directory / "build.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class OptionLayoutTest(unittest.TestCase):
    def test_source_paragraphs_and_generated_choices(self):
        for name in SETS:
            directory = SOURCES / name
            builder = load_builder(directory)
            total_groups = 0
            with self.subTest(set=name):
                for path in sorted((directory / "source").glob("????.json")):
                    source = json.loads(path.read_text())
                    output = directory / "papers" / f"{source['year']}-questions.htm"
                    tree = html.fromstring(output.read_text(), parser=html.HTMLParser(huge_tree=True))
                    for page in (item for item in source["pages"] if item["kind"] == "questions"):
                        sections = tree.xpath(f'//main/section[@data-source-page="{page["source_page"]}"]')
                        self.assertEqual(len(sections), 1)
                        expected = []
                        for block in page["blocks"]:
                            if block["type"] != "paragraph":
                                continue
                            split = builder.split_options(block["text"])
                            if split:
                                prefix, choices = split
                                self.assertEqual(prefix + "".join(label + value for label, value in choices), block["text"])
                                expected.append([label for label, _ in choices])
                        actual = [group.xpath('./div[@role="listitem"]/span[@class="math-option-label"]/text()')
                                  for group in sections[0].xpath('.//div[@class="math-options"]')]
                        self.assertEqual(actual, expected, f"{name} {source['year']} page {page['source_page']}")
                        total_groups += len(expected)
            self.assertGreater(total_groups, 0)

    def test_references_to_options_are_not_split(self):
        for name in SETS:
            builder = load_builder(SOURCES / name)
            self.assertIsNone(builder.split_options("选项（A）、（B）、（C）、（D）见图。"))
            self.assertIsNone(builder.split_options("过 A、B 两点的直线。"))
            self.assertIsNone(builder.split_options("商品 A 的价格为 10。"))


if __name__ == "__main__":
    unittest.main()
