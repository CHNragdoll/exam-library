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
