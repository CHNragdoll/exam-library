import hashlib
from contextlib import closing, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs

import translate_google_web as translator


def sidecar(path: Path, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"paperId": "kaoyan:2026-01", "paragraphs": [
        {"id": key, "translationEligible": True, "translationInput": source,
         "translationInputHash": hashlib.sha256(source.encode()).hexdigest(),
         "translationZh": None, "sourceText": source,
         "sourceHash": hashlib.sha256(source.encode()).hexdigest(),
         "protectedBlanks": list(translator.blank_tokens(source))}
        for key, source in rows
    ]}, ensure_ascii=False), encoding="utf-8")


class FakeClient:
    workers = 1

    def __init__(self, break_markers=False):
        self.calls = []
        self.break_markers = break_markers

    def translate(self, source):
        self.calls.append(source)
        if "<<<GTSEG" in source:
            if self.break_markers:
                return "译文一 译文二"
            return "<<<GTSEG000001>>>\n第一段译文。\n\n<<<GTSEG000002>>>\n第二段译文。"
        return "第一段译文。" if "first" in source else "第二段译文。"


class TranslatorTests(unittest.TestCase):
    def test_bilingual_prompt_protects_exact_blank_and_chinese_cue(self):
        source = "85. Only after many failures______________________ (我才认识到仅凭运气是不能成功的)."
        blanks = translator.blank_tokens(source)
        cues = translator.verified_cues(source, ["(我才认识到仅凭运气是不能成功的)"], "prompt")
        protected, replacements = translator.protect_source(source, blanks, cues)
        self.assertNotIn(cues[0], protected)
        self.assertNotIn(blanks[0], protected)
        self.assertEqual(len(replacements), 2)
        translated = f"只有在多次失败后{replacements[0][0]} {replacements[1][0]}。"
        restored = translator.restore_blanks(translated, replacements)
        translator.validate_blanks(blanks, restored)
        translator.validate_cues(cues, restored)
        with self.assertRaises(translator.PlaceholderError):
            translator.restore_blanks(translated.replace(replacements[1][0], ""), replacements)
        with self.assertRaises(translator.TranslationError):
            translator.verified_cues(source, ["(错误的中文提示)"], "prompt")

    def test_option_batches_and_same_paper_dedup_keep_each_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kaoyan" / "2026-01.json"
            sidecar(path, [])
            value = json.loads(path.read_text())
            source = "The careful student chose another answer."
            value["options"] = [
                {"id": f"kaoyan:2026-01:q-{number}-1:A", "kind": "answer_option",
                 "sourceText": source, "sourceHash": translator.sha256(source),
                 "translationInput": source, "translationInputHash": translator.sha256(source),
                 "translationEligible": True, "translationZh": None,
                 "protectedBlanks": []}
                for number in (1, 2)
            ]
            path.write_text(json.dumps(value), encoding="utf-8")
            pending, complete = translator.eligible_paragraphs([path])
            self.assertEqual((len(pending), complete), (2, 0))
            self.assertTrue(all(row.collection == "options" for row in pending))
            representatives, aliases = translator.deduplicate_option_requests(pending)
            self.assertEqual(len(representatives), 1)
            self.assertEqual(len(aliases[representatives[0].id]), 2)
            client = FakeClient()
            state = Path(directory) / "checkpoint.sqlite3"
            self.assertEqual(translator.run([path], state, client, None), (2, 0))
            self.assertEqual(len(client.calls), 1)
            translated = json.loads(path.read_text())["options"]
            self.assertTrue(all(row["translationZh"] == "第二段译文。" for row in translated))
            self.assertEqual(translator.run([path], state, client, None), (0, 0))

    def test_short_option_batches_have_separate_fifty_record_limit(self):
        path = Path("paper.json")
        options = [translator.Paragraph(path, f"option-{n}", f"Choice number {n}.",
                                        str(n), collection="options") for n in range(51)]
        self.assertEqual([len(batch) for batch in translator.build_batches(options)], [50, 1])
        paragraph = translator.Paragraph(path, "paragraph", "This is a paragraph.", "p")
        self.assertEqual([len(batch) for batch in translator.build_batches(options[:2] + [paragraph])],
                         [2, 1])

    def test_options_only_scope_preserves_pending_paragraph(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kaoyan" / "2026-01.json"
            sidecar(path, [("kaoyan:2026-01:p:b-1-1", "An English paragraph.")])
            value = json.loads(path.read_text())
            option_text = "Another answer."
            value["options"] = [{"id": "kaoyan:2026-01:q-1-1:A", "kind": "answer_option",
                                 "sourceText": option_text, "sourceHash": translator.sha256(option_text),
                                 "translationInput": option_text,
                                 "translationInputHash": translator.sha256(option_text),
                                 "translationEligible": True, "translationZh": None,
                                 "protectedBlanks": []}]
            path.write_text(json.dumps(value), encoding="utf-8")
            scoped, _ = translator.eligible_paragraphs([path], "options")
            self.assertEqual([record.id for record in scoped], ["kaoyan:2026-01:q-1-1:A"])
            client = FakeClient()
            self.assertEqual(translator.run([path], Path(directory) / "state.sqlite3", client,
                                            None, collection_filter="options"), (1, 0))
            result = json.loads(path.read_text())
            self.assertIsNone(result["paragraphs"][0]["translationZh"])
            self.assertEqual(result["options"][0]["translationZh"], "第二段译文。")

    def test_one_untranslated_option_does_not_discard_other_batch_results(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kaoyan" / "2026-01.json"
            sidecar(path, [])
            value = json.loads(path.read_text())
            inputs = tuple("CDW" if index == 11 else f"Answer number {index}."
                           for index in range(50))
            value["options"] = [
                {"id": f"kaoyan:2026-01:q-1-1:option-{index}", "kind": "answer_option",
                 "sourceText": source, "sourceHash": translator.sha256(source),
                 "translationInput": source, "translationInputHash": translator.sha256(source),
                 "translationEligible": True, "translationZh": None, "protectedBlanks": []}
                for index, source in enumerate(inputs)
            ]
            path.write_text(json.dumps(value), encoding="utf-8")

            class PartlyUntranslated:
                workers = 1

                def translate(self, source):
                    if "<<<GTSEG" in source:
                        return "\n\n".join(
                            f"<<<GTSEG{index + 1:06d}>>>\n" +
                            ("CDW" if index == 11 else f"第{index}项。")
                            for index in range(len(inputs)))
                    return source

            state = Path(directory) / "checkpoint.sqlite3"
            with redirect_stderr(io.StringIO()) as messages:
                self.assertEqual(translator.run([path], state, PartlyUntranslated(), None,
                                                collection_filter="options"), (49, 1))
            self.assertIn("Failed kaoyan:2026-01:q-1-1:option-11", messages.getvalue())
            saved = json.loads(path.read_text())["options"]
            self.assertEqual(sum(row["translationZh"] is not None for row in saved), 49)
            self.assertIsNone(saved[11]["translationZh"])
            self.assertEqual(saved[49]["translationZh"], "第49项。")
            with closing(translator.open_checkpoint(state)) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM translations").fetchone()[0], 49)

            class Recovered:
                workers = 1

                def translate(self, source):
                    return "光盘刻录机。" if source == "CDW" else "unexpected"

            with redirect_stderr(io.StringIO()):
                self.assertEqual(translator.run([path], state, Recovered(), None,
                                                collection_filter="options"), (1, 0))
            self.assertEqual([row["translationZh"] for row in
                              json.loads(path.read_text())["options"]][11], "光盘刻录机。")

    def test_transport_decodes_only_complete_html_entities(self):
        self.assertEqual(translator.transport_source("Harland &amp; Wolff"), "Harland & Wolff")
        self.assertEqual(translator.transport_source("A & B; plus &unknown;"), "A & B; plus &unknown;")

    def test_rate_limiter_rechecks_cooldown_after_sleep(self):
        now = [0.0]
        sleeps = []
        limiter = None

        def sleep(delay):
            sleeps.append(delay)
            if len(sleeps) == 1:
                limiter.defer(30.0)
            now[0] += delay

        limiter = translator.RateLimiter(1.0, clock=lambda: now[0], sleep=sleep)
        limiter.wait()  # First request starts at 0.
        limiter.wait()  # Concurrent 429 extends its original 1-second wait.
        self.assertEqual(now[0], 30.0)
        self.assertEqual(sleeps, [1.0, 29.0])

    def test_http_403_stops_without_retrying_the_corpus(self):
        calls = []

        def forbidden(request, timeout):
            calls.append(request)
            raise HTTPError(request.full_url, 403, "Forbidden", {}, None)

        client = translator.GoogleTranslateClient(translator.RateLimiter(0),
                                                   attempts=4, opener=forbidden)
        with self.assertRaises(translator.FatalTranslationError):
            client.translate("The first sentence.")
        self.assertEqual(len(calls), 1)

    def test_numbered_and_fullwidth_blanks_are_exact_tokens(self):
        source = "Choose (26)_______ and then fill ＿ ＿ or __."
        self.assertEqual(translator.blank_tokens(source),
                         ("(26)_______", "＿ ＿", "__"))
        protected, markers = translator.protect_blanks(source, translator.blank_tokens(source))
        self.assertNotIn("(26)_______", protected)
        translated = "选择 " + "、".join(marker for marker, _ in markers) + "。"
        restored = translator.restore_blanks(translated, markers)
        translator.validate_blanks(translator.blank_tokens(source), restored)
        with self.assertRaises(translator.PlaceholderError):
            translator.restore_blanks(translated.replace(markers[1][0], "____"), markers)
        with self.assertRaises(translator.PlaceholderError):
            translator.validate_blanks(translator.blank_tokens(source), "选择 ____ 或 __。")

    def test_stray_ocr_underscore_is_not_protected_but_verified_single_is(self):
        source = "The _genders vary; students express________ ideas."
        self.assertEqual(translator.blank_tokens(source), ("________",))
        self.assertEqual(translator.verified_blanks(source, ["________"], "one"),
                         ("________",))
        protected, markers = translator.protect_blanks(source, ("________",))
        self.assertIn("_genders", protected)
        self.assertEqual(len(markers), 1)
        printed = "This may result in_."
        self.assertEqual(translator.verified_blanks(printed, ["_"], "two"), ("_",))
        protected, markers = translator.protect_blanks(printed, ("_",))
        self.assertEqual(len(markers), 1)

    def test_protected_prompt_retries_changed_marker_then_fails_closed(self):
        source = "Complete (26)_______ and ＿ ＿."
        paragraph = translator.Paragraph(Path("paper.json"), "one", source, "a",
                                          translator.blank_tokens(source))

        class MarkerClient:
            def __init__(self, good_on_second):
                self.calls = 0
                self.good_on_second = good_on_second

            def translate(self, request, *, source_language="auto"):
                self.calls += 1
                if self.good_on_second and self.calls == 2:
                    return "完成 " + " 和 ".join(translator.PROTECTED_MARKER.format(i) for i in (1, 2)) + "。"
                return "完成 ____ 和 ____。"

        recovered = MarkerClient(True)
        self.assertEqual(translator.translate_batch([paragraph], recovered),
                         ["完成 (26)_______ 和 ＿ ＿。"])
        self.assertEqual(recovered.calls, 2)
        failed = MarkerClient(False)
        with self.assertRaises(translator.PlaceholderError):
            translator.translate_batch([paragraph], failed)
        self.assertEqual(failed.calls, 3)

    def test_readable_fallback_uses_english_only_and_preserves_blank_and_cue(self):
        source = "85. Only after failures______________________ (我才认识到仅凭运气是不能成功的)."
        cue = "(我才认识到仅凭运气是不能成功的)"
        paragraph = translator.Paragraph(Path("paper.json"), "prompt", source,
                                          translator.sha256(source), translator.blank_tokens(source),
                                          "paragraphs", (cue,))

        class Client:
            def __init__(self):
                self.calls = []

            def translate(self, request, *, source_language="auto"):
                self.calls.append((source_language, request))
                if source_language == "auto":
                    return "译文中标记损坏"
                return "只有在失败之后[BLANK_1] [CUE_1]。"

        client = Client()
        self.assertEqual(translator.translate_batch([paragraph], client),
                         ["只有在失败之后______________________ " + cue + "。"])
        self.assertEqual([language for language, _ in client.calls], ["auto", "auto", "en"])
        self.assertIn("[BLANK_1]", client.calls[-1][1])
        self.assertIn("[CUE_1]", client.calls[-1][1])
        self.assertNotIn(cue, client.calls[-1][1])
        with self.assertRaises(translator.PlaceholderError):
            translator.restore_readable_source("[CUE_1] [BLANK_1]", (
                ("[BLANK_1]", "______"), ("[CUE_1]", cue)))
        with self.assertRaises(translator.PlaceholderError):
            translator.restore_readable_source("[BLANK_1]", (
                ("[BLANK_1]", "______"), ("[CUE_1]", cue)))
        with self.assertRaises(translator.PlaceholderError):
            translator.protect_readable_source(source + "额外中文", paragraph.protected_blanks,
                                                paragraph.protected_cues)

    def test_http_response_requires_exact_source_echo(self):
        class Response(io.BytesIO):
            headers = {"Content-Type": "application/json; charset=utf-8"}

        source = "The first sentence."
        requests = []

        def good_open(request, timeout):
            requests.append(request)
            return Response(json.dumps([[["第一句。", source]]]).encode())

        client = translator.GoogleTranslateClient(translator.RateLimiter(0),
                                                   attempts=1, opener=good_open)
        self.assertEqual(client.translate(source), "第一句。")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].full_url, translator.ENDPOINT)
        self.assertEqual(requests[0].get_method(), "POST")

        wrong_calls = []

        def wrong_open(request, timeout):
            wrong_calls.append(request)
            return Response(json.dumps([[["错误译文。", "Another source."]]]).encode())

        bad_client = translator.GoogleTranslateClient(translator.RateLimiter(0),
                                                       attempts=2, opener=wrong_open,
                                                       sleep=lambda _: None)
        with self.assertRaises(translator.SourceEchoMismatch):
            bad_client.translate(source)
        self.assertEqual(len(wrong_calls), 1)

        entity_source = "Harland &amp; Wolff built the ships."

        def decoded_open(request, timeout):
            sent = parse_qs(request.data.decode())["q"][0]
            self.assertEqual(sent, "Harland & Wolff built the ships.")
            return Response(json.dumps([[["哈兰德与沃尔夫建造了这些船。", sent]]]).encode())

        entity_client = translator.GoogleTranslateClient(translator.RateLimiter(0),
                                                          attempts=1, opener=decoded_open)
        self.assertEqual(entity_client.translate(entity_source), "哈兰德与沃尔夫建造了这些船。")

    def test_batch_markers_and_segment_validation(self):
        path = Path("paper.json")
        rows = [translator.Paragraph(path, "one", "The first sentence.", "a"),
                translator.Paragraph(path, "two", "The second sentence.", "b")]
        client = FakeClient()
        self.assertEqual(translator.translate_batch(rows, client), ["第一段译文。", "第二段译文。"])
        self.assertEqual(len(client.calls), 1)
        broken = FakeClient(break_markers=True)
        self.assertEqual(translator.translate_batch(rows, broken), ["第一段译文。", "第二段译文。"])
        self.assertEqual(len(broken.calls), 3)
        with self.assertRaises(translator.SegmentationError):
            translator.parse_batch_result("<<<GTSEG000002>>>\n译文", 2)

    def test_utf16_limit_split_preserves_source(self):
        source = "A sentence. " * 470 + "🦊" * 100
        parts = translator.split_long_text(source)
        self.assertEqual("".join(parts), source)
        self.assertTrue(all(translator.utf16_length(part) <= 5000 for part in parts))

    def test_request_estimate_groups_prose_and_isolates_protected_prompt(self):
        path = Path("paper.json")
        rows = [translator.Paragraph(path, "one", "The first sentence.", "a"),
                translator.Paragraph(path, "two", "The second sentence.", "b"),
                translator.Paragraph(path, "three", "Fill (26)_______.", "c", ("(26)_______",))]
        batches = translator.build_batches(rows)
        self.assertEqual([len(batch) for batch in batches], [2, 1])
        self.assertEqual(translator.minimum_request_count(batches), 2)
        other_paper = translator.Paragraph(Path("another.json"), "four", "Another sentence.", "d")
        self.assertEqual([len(batch) for batch in translator.build_batches(rows[:2] + [other_paper])], [2, 1])

    def test_checkpoint_resume_and_in_place_atomic_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paper = root / "kaoyan" / "2026-01.json"
            state = root / "checkpoint.sqlite3"
            sidecar(paper, [("one", "The first sentence."), ("two", "The second sentence.")])
            client = FakeClient()
            self.assertEqual(translator.run([paper], state, client, None), (2, 0))
            data = json.loads(paper.read_text(encoding="utf-8"))
            self.assertEqual([r["translationZh"] for r in data["paragraphs"]],
                             ["第一段译文。", "第二段译文。"])
            self.assertEqual(len(client.calls), 1)
            # A sidecar regenerated with empty translations recovers from the
            # committed checkpoint without another network request.
            sidecar(paper, [("one", "The first sentence."), ("two", "The second sentence.")])
            self.assertEqual(translator.run([paper], state, client, None), (0, 0))
            self.assertEqual(len(client.calls), 1)
            data = json.loads(paper.read_text(encoding="utf-8"))
            self.assertEqual(data["paragraphs"][0]["translationZh"], "第一段译文。")

    def test_storage_failure_stops_and_checkpoint_can_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paper = root / "kaoyan" / "2026-01.json"
            state = root / "checkpoint.sqlite3"
            sidecar(paper, [("one", "The first sentence.")])
            client = FakeClient()
            with patch.object(translator, "atomic_json_write", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    translator.run([paper], state, client, None)
            self.assertIsNone(json.loads(paper.read_text())["paragraphs"][0]["translationZh"])
            self.assertEqual(translator.run([paper], state, client, None), (0, 0))
            self.assertEqual(len(client.calls), 1)

    def test_fatal_provider_error_stops_before_next_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paper = root / "kaoyan" / "2026-01.json"
            state = root / "checkpoint.sqlite3"
            sidecar(paper, [(str(i), "The first sentence.") for i in range(8)])

            class ForbiddenClient:
                workers = 1
                calls = 0

                def translate(self, source):
                    self.calls += 1
                    raise translator.FatalTranslationError("Google Translate HTTP 403")

            client = ForbiddenClient()
            with self.assertRaises(translator.FatalTranslationError):
                translator.run([paper], state, client, None)
            self.assertEqual(client.calls, 1)

    def test_batch_echo_mismatch_falls_back_and_quarantines_exact_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paper = root / "kaoyan" / "2026-01.json"
            state = root / "checkpoint.sqlite3"
            sidecar(paper, [("good", "The first sentence."), ("bad", "The bad sentence.")])

            class EchoClient:
                workers = 1
                calls = []

                def translate(self, source):
                    self.calls.append(source)
                    if "GTSEG" in source or "bad" in source:
                        raise translator.SourceEchoMismatch("echo changed")
                    return "第一句。"

            client = EchoClient()
            log = io.StringIO()
            with redirect_stderr(log):
                self.assertEqual(translator.run([paper], state, client, None), (1, 1))
            data = json.loads(paper.read_text())["paragraphs"]
            self.assertEqual(data[0]["translationZh"], "第一句。")
            self.assertIsNone(data[1]["translationZh"])
            self.assertIn("'good', 'bad'", log.getvalue())
            self.assertIn("Quarantined bad", log.getvalue())
            pending, _ = translator.eligible_paragraphs([paper])
            self.assertIn(translator.paragraph_key(pending[0]), translator.read_quarantined_keys(state))

    def test_changed_source_is_not_reused_and_hash_mismatch_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paper = root / "kaoyan" / "2026-01.json"
            state = root / "checkpoint.sqlite3"
            sidecar(paper, [("one", "The first sentence.")])
            first = FakeClient()
            self.assertEqual(translator.run([paper], state, first, None), (1, 0))
            sidecar(paper, [("one", "The second sentence.")])
            second = FakeClient()
            self.assertEqual(translator.run([paper], state, second, None), (1, 0))
            self.assertEqual(len(second.calls), 1)
            data = json.loads(paper.read_text(encoding="utf-8"))
            data["paragraphs"][0]["translationInput"] = "Changed without hash update"
            paper.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(translator.TranslationError):
                translator.eligible_paragraphs([paper])

    def test_quarantine_skips_exact_id_and_hash_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paper = root / "kaoyan" / "2026-01.json"
            state = root / "checkpoint.sqlite3"
            sidecar(paper, [("one", "The first sentence.")])
            pending, _ = translator.eligible_paragraphs([paper])
            with closing(translator.open_checkpoint(state)) as db:
                translator.quarantine(db, pending[0], "Google mistranslated a domain term", "错误译文。")
            self.assertIn(translator.paragraph_key(pending[0]), translator.read_quarantined_keys(state))
            client = FakeClient()
            self.assertEqual(translator.run([paper], state, client, None), (0, 0))
            self.assertEqual(client.calls, [])
            self.assertIsNone(json.loads(paper.read_text())["paragraphs"][0]["translationZh"])

    def test_rejects_twin_sidecar_filename_and_wrong_paper_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            twin = root / "kaoyan" / "2026-01 2.json"
            sidecar(twin, [("one", "The first sentence.")])
            with self.assertRaises(translator.TranslationError):
                translator.json_paths(twin)
            canonical = root / "kaoyan" / "2026-02.json"
            sidecar(canonical, [("two", "The second sentence.")])
            with self.assertRaises(translator.TranslationError):
                translator.json_paths(canonical)


if __name__ == "__main__":
    unittest.main()
