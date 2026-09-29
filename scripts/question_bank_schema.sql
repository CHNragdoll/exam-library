PRAGMA foreign_keys = ON;

CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE papers (
    id TEXT PRIMARY KEY,
    ordinal INTEGER NOT NULL UNIQUE CHECK (ordinal > 0),
    category TEXT NOT NULL,
    category_label TEXT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    year INTEGER,
    template TEXT,
    json_path TEXT NOT NULL UNIQUE,
    reader_path TEXT,
    source_original TEXT,
    source_reflow TEXT,
    pages INTEGER,
    question_count INTEGER NOT NULL CHECK (question_count >= 0),
    record_count INTEGER NOT NULL CHECK (record_count >= 0),
    block_count INTEGER NOT NULL CHECK (block_count >= 0),
    raw_json TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE questions (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    local_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    number TEXT,
    question_type TEXT,
    record_type TEXT NOT NULL,
    section_kind TEXT,
    section_title TEXT,
    stem TEXT,
    status TEXT,
    context_json TEXT,
    source_pages_json TEXT NOT NULL,
    subquestions_json TEXT,
    continuations_json TEXT,
    in_bank INTEGER NOT NULL CHECK (in_bank IN (0, 1)),
    raw_json TEXT NOT NULL,
    UNIQUE (paper_id, local_id),
    UNIQUE (paper_id, ordinal)
);

CREATE INDEX questions_paper_bank_order ON questions(paper_id, in_bank, ordinal);
CREATE INDEX questions_bank_type ON questions(in_bank, question_type);

-- Printed shared-material groups are separate from private answer choices.
CREATE TABLE labels (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    kind TEXT NOT NULL CHECK (kind IN
        ('cloze','reading','matching','translation','writing')),
    text TEXT NOT NULL,
    source_title TEXT NOT NULL,
    source_block_id TEXT NOT NULL REFERENCES source_blocks(id),
    UNIQUE (paper_id, source_block_id)
);

CREATE INDEX labels_kind_text ON labels(kind, text);

CREATE TABLE question_labels (
    question_id TEXT NOT NULL REFERENCES questions(id),
    label_id TEXT NOT NULL REFERENCES labels(id),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    PRIMARY KEY (question_id, ordinal),
    UNIQUE (question_id, label_id)
) WITHOUT ROWID;

CREATE INDEX question_labels_label ON question_labels(label_id);

CREATE TABLE source_blocks (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    local_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    page TEXT,
    source_page_index INTEGER,
    source_block_index INTEGER,
    role TEXT,
    text TEXT,
    content_html TEXT,
    formulas_json TEXT NOT NULL,
    images_json TEXT NOT NULL,
    status TEXT,
    question_id TEXT REFERENCES questions(id),
    raw_json TEXT NOT NULL,
    UNIQUE (paper_id, local_id),
    UNIQUE (paper_id, ordinal)
);

CREATE INDEX source_blocks_paper_order ON source_blocks(paper_id, ordinal);
CREATE INDEX source_blocks_question ON source_blocks(question_id);

CREATE TABLE question_source_blocks (
    question_id TEXT NOT NULL REFERENCES questions(id),
    block_id TEXT NOT NULL REFERENCES source_blocks(id),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    PRIMARY KEY (question_id, ordinal),
    UNIQUE (question_id, block_id)
) WITHOUT ROWID;

CREATE TABLE context_source_blocks (
    question_id TEXT NOT NULL REFERENCES questions(id),
    block_id TEXT NOT NULL REFERENCES source_blocks(id),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    PRIMARY KEY (question_id, ordinal),
    UNIQUE (question_id, block_id)
) WITHOUT ROWID;

CREATE TABLE options (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL REFERENCES questions(id),
    label TEXT NOT NULL,
    source_label TEXT,
    text TEXT NOT NULL,
    default_position INTEGER NOT NULL CHECK (default_position > 0),
    source_position INTEGER NOT NULL CHECK (source_position >= 0),
    is_correct INTEGER CHECK (is_correct IN (0, 1)),
    raw_json TEXT NOT NULL,
    UNIQUE (question_id, default_position),
    UNIQUE (question_id, source_position)
);

CREATE INDEX options_question_order ON options(question_id, default_position);

CREATE TABLE answers (
    question_id TEXT PRIMARY KEY REFERENCES questions(id),
    value TEXT,
    solution TEXT,
    explanation TEXT,
    commentary TEXT,
    knowledge TEXT,
    status TEXT NOT NULL,
    source_document_id TEXT REFERENCES papers(id),
    source_question_ids_json TEXT NOT NULL,
    source_blocks_json TEXT NOT NULL,
    source_pages_json TEXT NOT NULL,
    ambiguity_reason TEXT,
    raw_json TEXT NOT NULL
) WITHOUT ROWID;

-- Additive semantic model. The v2 tables above remain the stable API contract.
CREATE TABLE semantic_nodes (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    parent_id TEXT REFERENCES semantic_nodes(id),
    node_type TEXT NOT NULL CHECK (node_type IN
        ('paper','section','passage','material','question','subquestion','option','answer')),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    title TEXT,
    question_id TEXT REFERENCES questions(id),
    option_id TEXT REFERENCES options(id),
    answer_question_id TEXT REFERENCES answers(question_id),
    source_json_path TEXT,
    UNIQUE (paper_id, id)
);

CREATE INDEX semantic_nodes_parent_order ON semantic_nodes(parent_id, ordinal);
CREATE INDEX semantic_nodes_question ON semantic_nodes(question_id);

CREATE TABLE content_units (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    node_id TEXT NOT NULL REFERENCES semantic_nodes(id),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    unit_type TEXT NOT NULL CHECK (unit_type IN
        ('paragraph','instruction','figure','code','formula','other')),
    text TEXT,
    content_html TEXT,
    UNIQUE (node_id, ordinal)
);

CREATE INDEX content_units_paper ON content_units(paper_id);

CREATE TABLE unit_provenance (
    content_unit_id TEXT PRIMARY KEY REFERENCES content_units(id),
    paper_id TEXT NOT NULL REFERENCES papers(id),
    source_block_id TEXT REFERENCES source_blocks(id),
    json_path TEXT,
    source_hash TEXT NOT NULL CHECK (length(source_hash) = 64),
    CHECK ((source_block_id IS NOT NULL) <> (json_path IS NOT NULL))
) WITHOUT ROWID;

CREATE INDEX unit_provenance_block ON unit_provenance(source_block_id);

CREATE TABLE semantic_links (
    from_node_id TEXT NOT NULL REFERENCES semantic_nodes(id),
    to_node_id TEXT NOT NULL REFERENCES semantic_nodes(id),
    link_type TEXT NOT NULL CHECK (link_type IN ('shared_context','continuation')),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    source_json_path TEXT NOT NULL,
    PRIMARY KEY (from_node_id, to_node_id, link_type)
) WITHOUT ROWID;

CREATE TABLE quality_issues (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    node_id TEXT NOT NULL REFERENCES semantic_nodes(id),
    issue_code TEXT NOT NULL,
    detail TEXT,
    source_json_path TEXT NOT NULL
);

CREATE INDEX quality_issues_node ON quality_issues(node_id);

CREATE TABLE scoreability (
    question_id TEXT PRIMARY KEY REFERENCES questions(id),
    scoreable INTEGER NOT NULL CHECK (scoreable IN (0, 1)),
    reason TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE input_hashes (
    relative_path TEXT PRIMARY KEY,
    input_kind TEXT NOT NULL CHECK (input_kind IN ('audit','bank','paper')),
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    byte_length INTEGER NOT NULL CHECK (byte_length >= 0)
) WITHOUT ROWID;

CREATE TABLE paper_forms (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    label TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('default','explicit','unresolved_year_conflict')),
    printed_year INTEGER,
    source_block_id TEXT REFERENCES source_blocks(id),
    raw_heading TEXT,
    UNIQUE (paper_id, ordinal),
    UNIQUE (paper_id, label)
);

CREATE TABLE question_paper_forms (
    question_id TEXT PRIMARY KEY REFERENCES questions(id),
    form_id TEXT NOT NULL REFERENCES paper_forms(id),
    evidence_block_id TEXT REFERENCES source_blocks(id),
    assignment_status TEXT NOT NULL CHECK (assignment_status IN ('default','explicit_boundary'))
) WITHOUT ROWID;

CREATE INDEX question_paper_forms_form ON question_paper_forms(form_id);

CREATE TABLE choice_sets (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id),
    form_id TEXT NOT NULL REFERENCES paper_forms(id),
    kind TEXT NOT NULL CHECK (kind IN ('word_bank','paragraph_bank')),
    status TEXT NOT NULL CHECK (status IN ('explicit','unresolved_source_labels')),
    source_block_id TEXT NOT NULL REFERENCES source_blocks(id),
    raw_text TEXT NOT NULL
);

CREATE TABLE choice_set_options (
    id TEXT PRIMARY KEY,
    choice_set_id TEXT NOT NULL REFERENCES choice_sets(id),
    label TEXT NOT NULL,
    source_position INTEGER NOT NULL CHECK (source_position > 0),
    text TEXT NOT NULL,
    source_block_id TEXT NOT NULL REFERENCES source_blocks(id),
    UNIQUE (choice_set_id, source_position),
    UNIQUE (choice_set_id, label)
);

CREATE TABLE question_choice_sets (
    question_id TEXT NOT NULL REFERENCES questions(id),
    choice_set_id TEXT NOT NULL REFERENCES choice_sets(id),
    PRIMARY KEY (question_id, choice_set_id)
) WITHOUT ROWID;

CREATE TABLE answer_references (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL REFERENCES questions(id),
    source_field TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    literal_text TEXT NOT NULL,
    target_year INTEGER,
    target_form TEXT,
    target_section TEXT,
    target_number TEXT,
    target_question_id TEXT REFERENCES questions(id),
    status TEXT NOT NULL CHECK (status IN ('resolved','unresolved','ambiguous')),
    ambiguity_reason TEXT,
    source_json_path TEXT NOT NULL,
    UNIQUE (question_id, source_field, ordinal)
);

CREATE INDEX answer_references_target ON answer_references(target_question_id);

-- Existing PDF/SVG extraction locates a block, not reliable character ranges.
CREATE TABLE source_spans (
    source_block_id TEXT PRIMARY KEY REFERENCES source_blocks(id),
    paper_id TEXT NOT NULL REFERENCES papers(id),
    page TEXT,
    source_page_index INTEGER,
    source_block_index INTEGER,
    source_json_path TEXT NOT NULL,
    precision TEXT NOT NULL CHECK (precision = 'block')
) WITHOUT ROWID;

CREATE TABLE quality_issue_source_spans (
    issue_id TEXT NOT NULL REFERENCES quality_issues(id),
    source_block_id TEXT NOT NULL REFERENCES source_spans(source_block_id),
    PRIMARY KEY (issue_id, source_block_id)
) WITHOUT ROWID;
