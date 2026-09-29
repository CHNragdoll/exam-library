# English paragraph translation sidecars

Run `python3 scripts/build_english_paragraph_manifest.py` after rebuilding the
reflow JSON and `python3 scripts/build_structured_exams.py`. This writes
`data/sources/exam-library/structured/english-paragraphs.json` and one sidecar
at `structured/translations/<category>/<paper-stem>.json` for each canonical
English paper in the reflow manifest. It does not call a translator, change an
original paper, or touch the question database. `--check` audits without writes.

Each sidecar has `schema: english-paragraph-translations.v1`, `paperId`,
`category`, source JSON path and source PDF hash, `paragraphs`, `options`,
`sourceInventory`, `reconciliation`, and `issues`. The five English categories
are `kaoyan`, `cet4`, `cet6`, `tem4`, and `tem8`. The builder reads canonical
paths from the reflow manifest and rejects duplicate paper IDs, so stale files
such as `* 2.json` do not create papers.

Each paragraph has a globally unique `id`, `kind`, exact `sourceText`, and
`sourceHash` (lowercase SHA-256 hex of its UTF-8 bytes). `sourceBlockIds` are
fully qualified **structured paper** IDs such as `kaoyan:2026-01:b-1-5`.
`reflowBlockIds` are fully qualified raw reflow JSON IDs. These are separate
coordinate systems: structured blocks are numbered after HTML layout repair.
The builder resolves the raw IDs from exact `data-source-block-id` markers in
structured `contentHtml`; a single long lettered option without a marker must
match exactly one structured choices block on its source page. `paragraphIndex`
is zero; the parallel `source.blockIds` and `source.blockParagraphIndices`
arrays carry the local structured coordinates, while
`source.reflowBlockIds` carries raw coordinates. A source paragraph split
across pages may have multiple raw IDs but only one structured ID if the HTML
renderer joined it. `source.pages`, `source.sourceJson`, and
`source.pdfSha256` preserve provenance. The source text uses one space when
joining fragments, except after a hyphen, matching the reflow reader's join.

`options[]` inventories every structured English question choice and each
unique CET/TEM word-bank entry. Each record has `kind: answer_option` or
`word_bank_option`, fully qualified `questionId` and `optionId`, exact API
`sourceText` and SHA-256 `sourceHash`. A uniquely proven raw `options` or
`choice_row` item also has `reflowBlockId`, zero-based `reflowOptionIndex`, and
exact label-free `reflowSourceText`. The builder permits a difference between
structured and raw text only if every nonwhitespace character agrees; it then
sends the exact raw text to Google and retains both originals for independent
UI checks. An uncertain anchor is ineligible with an explicit reason. Repeated
word-bank/question choices with the same raw item use `covered_by_option` and
`translationRef`; a complete Part B choice already translated as a
`passage_option` uses `covered_by_paragraph`. The publisher resolves these
references only after verifying exact source identity, so each question can
show a translation without a second Google request. The public sidecar omits
option `translationInput` and its hash just as it does for paragraphs.
Eight Kaoyan English II Part B choice tables exist as raw PDF figures, with no
individual reflow option item. A reviewed PDF/figure/structured-choice fixture
proves each printed A–G choice once, then emits one eligible translation per
unique choice and four exact option aliases for the repeated Q41–45 uses.
`pdfVerifiedSource` records the checked PDF page/hash, real figure block, and
stable source option ID. The publisher revalidates the current PDF, raw figure,
and structured text before allowing these options without an item anchor.
The 2005 English I A choice split across two raw paragraphs is joined only
under the same source/PDF guard and reused by its five question options.
Forty-six CET word-bank entries whose reflow items merged columns, shifted
source blocks, or retained printed punctuation use a separate PDF-backed exact
word span. The derived English word is translated once; its raw item, PDF page,
and structured bank ID remain auditable in `pdfVerifiedSource`. A CET6 option
printed as prose before the next page's B–D list reuses its verified question
paragraph. The reflow reader attaches only options with a literal item match;
the practice reader can show PDF-verified bank translations by stable option ID.

`translationInput` is the exact English to translate, and
`translationInputHash` hashes that exact UTF-8 string. Both are `null` when
`translationEligible` is false. Ordinary English body text uses its
`sourceText`, including reading passages, Directions, writing prompts,
listening instructions, and full question stems. Short answer options are in
`options[]`; number-only artifacts, non-English material, and answer appendices
are excluded. Passage-like lettered paragraphs are `passage_option` records.
When a Chinese translation task shares a source block with complete English
Directions, `sourceText` retains the full bilingual block and
`translationInput` contains only the exact English instruction prefix.
Some CET Section B paragraphs begin in a one-item `options` source block and
continue in the following paragraph block; they form one record with both
source block IDs and one joined `sourceText`.
Four misparsed one-item `D. . You should decide...` blocks are classified as
instructions; their printed source text retains the prefix, while the exact
English instruction sentence alone is sent for translation. Page furniture
inside an otherwise verified cloze group is excluded per record. A passage
crossing an image-only source line is ineligible until that line is verified.
Non-cloze question prompts may retain visible blanks. Their exact underscore
tokens appear in `protectedBlanks`; a translator must preserve the same tokens
in its Chinese output and must not infer an answer.
Five PDF-verified CET6 bilingual completion prompts whose printed Chinese cue
was split into a following raw block are joined only while original PDF and
both raw block hashes match. The original two-block source remains in
`sourceBlockIds` and `reflowBlockIds`. `protectedCues` holds the exact complete
parenthetical Chinese cue; the Google client replaces both blanks and cues
with indexed markers, requires their exact order and count in the reply, then
restores the printed bytes. The publisher omits these private fields. Nine
source-verified numbered cloze fragments without full answer words are
ineligible; eight TEM cover `TIME LIMIT` headings are excluded as cover
metadata under paper/PDF/text guards.
If Google alters its first protected markers or leaves a protected prompt
untranslated, the client makes one bounded English-source retry using
`[BLANK_n]` and `[CUE_n]`. It sends the retry only when every Chinese character
is inside a protected complete cue; exact Google source echo, marker order,
count, original blank bytes, and original cue bytes are mandatory. A missing
or modified marker remains quarantined. The known incomplete Google output for
`cet6:2022-06-01:p:b-5-2` is blocked by exact source/output hashes at public
publication until it is replaced by a reviewed translation or quarantined.
For cloze, the original source remains in `sourceText`; only a separately
derived `translationInput` has numbered blanks replaced by answer words.
Restoration requires one uniquely located printed blank marker, one explicitly marked answer, and
one uniquely matching, nonempty option or word bank item per number. If any
blank, word bank, or source line is uncertain, the entire passage is ineligible
and `unresolvedBlanks` explains why. TEM4 cloze passages are recorded as
ineligible until their question and answer structure is verified.
An unstyled CET number is accepted as a blank only when its source run also
contains explicit surrounding underscore/parenthesis blank syntax; a bare
number is not enough. Any paragraph containing the Unicode replacement glyph
`�` is marked `source_unreadable`, with `translationInput: null` and an issue
that reports whether raw and rendered nonwhitespace characters differ.
Listening Section C dictation paragraphs after printed “hear a passage three
times / fill (in) the blanks” Directions are also ineligible when their
numbered 26–35 answer words have not been source-verified. The builder records
`unverified_listening_dictation` with the printed numbers and never sends bare
numbers such as `34` or `35` as completed English prose.
Passage-matched answer evidence may be supplied with `--verified-dictation`
from a private JSON file. Its `schema` must be
`verified-listening-dictation.v1`, and `papers` maps canonical paper IDs to
`sourceUrl`, `sourcePage`, `passageMatchEvidence`, and `answers` containing
exactly keys `26` through `35`, each with a nonempty `word`. The builder fills
only a complete, ordered printed 26–35 group. Missing, repeated, or out-of-order
numbers remain ineligible even when a key file is supplied. The original
`sourceText`/`sourceHash` never change; restored words appear only in the
derived `translationInput` and are covered by `translationInputHash`.

When raw English prose contains a printed Chinese `第 N 页共 M 页` footer, the
builder removes that exact footer from eligible `translationInput` only if `N`
matches one of its reflow source pages and `M` equals the paper's page count.
Three short `第 N 页` footers in CET6 2018 June Sets 2/3 are removed only for
their exact PDF hash and visually verified source pages (Set 2 page 6; Set 3
pages 4–5). Other short markers fail closed.
It keeps the footer in `sourceText` for provenance and records
`verified_page_footer`; a mismatch is ineligible as `unverified_page_footer`.
Changing the derived input changes its hash, so an earlier translation is
quarantined as stale and must be translated again before publication.

`translationZh` is initially `null`. On rebuild, a populated translation is
retained only if both source and translation input hashes still match and the
paragraph remains eligible. Changed translations are moved to
`staleTranslations` for recovery and noted in `issues`; they are never silently
reattached to changed English. A translation importer should reject a result
whose provider input hash differs from `translationInputHash`.

`scripts/translate_google_web.py --collection options` scopes dry runs and
`--execute` runs to eligible options, leaving pending paragraphs untouched.
Option requests use at most 50 short items per marker-validated batch and
5,000 UTF-16 units; identical inputs within one paper share the request while
each option keeps its own checkpoint and source identity. A failed marker,
source echo, or protected blank is rejected rather than assigned to an item.

The working sidecars contain restored cloze answer words in `translationInput`
and `restoredBlanks`. Once Google translation has finished and its writer has
stopped, run `python3 scripts/publish_english_paragraph_translations.py` for
read-only completeness validation, then run it with `--publish` to make public
sidecars. The preflight rebuilds the expected paragraph and option inventory
from all 206 current canonical structured/reflow papers and source PDF hashes.
It rejects missing, extra, or changed IDs, source text/hashes, translation
inputs, and provenance before checking translations. Supply the same private
listening evidence with `--verified-dictation` when one was used for manifest
generation; the local `.local/answer-keys/verified-listening-dictation.json`
is selected automatically when present. The publish step refuses any eligible paragraph without a nonempty
translation unless its ID is listed with a nonempty reason in a private
`--quarantine-file`. The file has schema
`english-paragraph-translation-quarantine.v1` and an `items` array of
`{"id": "<paragraph id>", "reason": "<review finding>"}` objects. A listed
record is published with `translationEligible: false`, `translationZh: null`,
and `translationStatus: quality_quarantined`; the detailed reason stays in the
private audit snapshot and the public record has only a generic review code.
It is never silently counted as translated. A manually corrected translation can instead be saved as a
nonempty `translationZh` with review provenance in the working record before
publishing. The command copies all full working sidecars to a private ignored `.local/`
snapshot and stages every redacted file outside the static server root. It
checks that working files have not changed, then atomically replaces each JSON;
if a replacement fails, it restores already replaced files from the private
snapshot and reports any rollback failure for manual recovery. Public records keep
source text/hashes, IDs, eligibility, and `translationZh`, but omit
`translationInput`, `translationInputHash`, `restoredBlanks`,
`protectedBlanks`, `unresolvedBlanks`,
`staleTranslations`, and other fields not
on the explicit public allowlist. The reader should fetch a sidecar only after
the user asks to reveal a translation; the translated cloze answer remains
visible in `translationZh` when revealed. Do not rerun the working-sidecar
builder after publication without repeating the publish step.

`sourceInventory` accounts for every nonempty raw source paragraph, heading,
instruction, or question stem as
included, excluded, or ineligible. The summary counts and issue list flag
unresolved cloze, source block mismatch, duplicate IDs, malformed joins, and
missing source blocks. `reasonCounts` distinguishes reading prose, passage
options, Directions, writing, listening, and other regions;
`kindCounts` gives the output paragraph mix. `otherSourceBlockCounts` separately
counts source blocks such as short answer choices and figures, plus structured
image-only source lines and their Chinese unreadable-source notices. Source
verification compares every nonwhitespace character, including punctuation;
layout whitespace alone is ignored. Incomplete cloze and unreadable-source
issues are explicit translation exclusions, while other issue codes make
`--check` fail. `staleTranslationCount` separately reports previously saved
translations that would be detached by a new source or eligibility decision;
the check never writes them. These checks are structural evidence, not a substitute
for comparing suspect OCR or paragraph boundaries against the original PDF.
