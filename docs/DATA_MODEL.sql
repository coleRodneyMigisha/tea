-- tea schema, migration 001. SQLite. PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1');

-- One piece of writing: weekly or manual.
CREATE TABLE blogs (
  id               INTEGER PRIMARY KEY,
  title            TEXT NOT NULL,
  topic            TEXT NOT NULL,                       -- may be '' while a pick-mode topic is not chosen yet
  scope_notes      TEXT NOT NULL DEFAULT '',
  audience         TEXT NOT NULL DEFAULT '',
  length           TEXT NOT NULL DEFAULT 'standard' CHECK (length IN ('short','standard','long')),
  allowed_sources  TEXT NOT NULL DEFAULT '[]',          -- JSON array: "own_documents","web","academic"
  origin           TEXT NOT NULL CHECK (origin IN ('weekly','manual')),
  topic_origin     TEXT NOT NULL DEFAULT 'owner' CHECK (topic_origin IN ('owner','auto_trending')),
  status           TEXT NOT NULL DEFAULT 'queued'
                   CHECK (status IN ('scoping','queued','prompt_ready','ready','posted','shelved')),
  carried_weeks    INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT NOT NULL,                       -- ISO 8601, local time with offset
  updated_at       TEXT NOT NULL
);

-- One row per ISO week that has a focus or is in pick mode.
CREATE TABLE weeks (
  week_start         TEXT PRIMARY KEY,                  -- Monday date, YYYY-MM-DD
  focus_text         TEXT,                              -- NULL until set or picked
  topic_origin       TEXT NOT NULL DEFAULT 'owner' CHECK (topic_origin IN ('owner','auto_trending')),
  pick_mode          INTEGER NOT NULL DEFAULT 0,        -- 1 = Friday's prompt asks Claude to pick the topic
  focus_set_at       TEXT,
  blog_id            INTEGER REFERENCES blogs(id) ON DELETE CASCADE,
  trend_candidates   TEXT                               -- JSON from the imported reply: candidates, angles, reasons, urls
);

-- Files the owner attaches to the Claude chat. tea stores a copy and the list; it never reads them.
CREATE TABLE attachments (
  id               INTEGER PRIMARY KEY,
  blog_id          INTEGER NOT NULL REFERENCES blogs(id) ON DELETE CASCADE,
  filename         TEXT NOT NULL,
  stored_path      TEXT NOT NULL,
  kind             TEXT NOT NULL,                       -- extension without dot, lowercase
  size_bytes       INTEGER NOT NULL,
  include_in_list  INTEGER NOT NULL DEFAULT 1,          -- 0 = owner will not attach it
  added_at         TEXT NOT NULL
);
CREATE INDEX idx_attachments_blog ON attachments(blog_id);

CREATE TABLE questions (
  id               INTEGER PRIMARY KEY,
  text             TEXT NOT NULL,
  kind             TEXT NOT NULL CHECK (kind IN ('text','choice','scale')),
  options          TEXT NOT NULL DEFAULT '[]',          -- JSON; choice options, or [low, high] labels for scale
  category         TEXT NOT NULL CHECK (category IN
                   ('voice','audience','structure','evidence','experience','boundaries','scope','improve')),
  origin           TEXT NOT NULL CHECK (origin IN ('bank','week','blog','improve')),
  week_start       TEXT REFERENCES weeks(week_start) ON DELETE CASCADE,
  blog_id          INTEGER REFERENCES blogs(id) ON DELETE CASCADE,
  active           INTEGER NOT NULL DEFAULT 1,
  asked_count      INTEGER NOT NULL DEFAULT 0,
  last_asked_at    TEXT,
  template_key     TEXT,                                -- id from a template file (generated rows) or bank_key (seed rows)
  bank_key         TEXT UNIQUE
);
CREATE INDEX idx_questions_week ON questions(week_start);
CREATE INDEX idx_questions_blog ON questions(blog_id);

CREATE TABLE answers (
  id               INTEGER PRIMARY KEY,
  question_id      INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
  context          TEXT NOT NULL CHECK (context IN ('login','blog_scope','monday')),
  week_start       TEXT,
  blog_id          INTEGER REFERENCES blogs(id) ON DELETE CASCADE,
  answer_text      TEXT NOT NULL DEFAULT '',
  skipped          INTEGER NOT NULL DEFAULT 0,
  answered_at      TEXT NOT NULL
);
CREATE INDEX idx_answers_blog ON answers(blog_id);
CREATE INDEX idx_answers_week ON answers(week_start);

CREATE TABLE drafts (
  id                 INTEGER PRIMARY KEY,
  blog_id            INTEGER NOT NULL REFERENCES blogs(id) ON DELETE CASCADE,
  version            INTEGER NOT NULL,
  kind               TEXT NOT NULL DEFAULT 'new' CHECK (kind IN ('new','improved','regenerated','checked')),
  title              TEXT NOT NULL,
  body_markdown      TEXT NOT NULL,                     -- as imported, never overwritten
  edited_markdown    TEXT,                              -- owner's edits; NULL if untouched
  raw_reply          TEXT NOT NULL,                     -- exactly what was pasted
  sources            TEXT NOT NULL DEFAULT '[]',        -- JSON list from <sources>
  verification       TEXT NOT NULL DEFAULT '[]',        -- JSON list of {status, claim, source, note}
  flags              TEXT NOT NULL DEFAULT '[]',        -- JSON list of strings from <flags>
  changes            TEXT NOT NULL DEFAULT '[]',        -- JSON list from <changes> (improve only)
  parse_warnings     TEXT NOT NULL DEFAULT '[]',        -- JSON list of codes
  prompt_versions    TEXT NOT NULL,                     -- JSON {"packet_draft":1,...}
  imported_at        TEXT NOT NULL,
  copied_at          TEXT,                              -- set by Copy for Medium; counts as "used"
  posted_at          TEXT,                              -- set by Mark as posted; counts as "used"
  UNIQUE (blog_id, version)
);
CREATE INDEX idx_drafts_blog ON drafts(blog_id);

-- One round trip with Claude.
CREATE TABLE handoffs (
  id               INTEGER PRIMARY KEY,
  kind             TEXT NOT NULL CHECK (kind IN ('weekly','weekly_pick','manual','improve','audit')),
  blog_id          INTEGER REFERENCES blogs(id) ON DELETE CASCADE,
  week_start       TEXT NOT NULL DEFAULT '',
  packet_text      TEXT NOT NULL,
  packet_words     INTEGER NOT NULL,
  prompt_versions  TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'prompt_ready'
                   CHECK (status IN ('prompt_ready','copied','imported','superseded')),
  created_at       TEXT NOT NULL,
  copied_at        TEXT,
  imported_at      TEXT,
  draft_id         INTEGER REFERENCES drafts(id) ON DELETE SET NULL,
  reminder_count   INTEGER NOT NULL DEFAULT 0,
  last_reminder_at TEXT
);
CREATE INDEX idx_handoffs_blog ON handoffs(blog_id);
CREATE INDEX idx_handoffs_status ON handoffs(status);

CREATE TABLE jobs (
  kind             TEXT NOT NULL CHECK (kind IN
                   ('focus_prompt','pick_mode','login_questions','weekly_packet','improve_packet','no_focus_notice')),
  week_start       TEXT NOT NULL DEFAULT '',
  blog_id          INTEGER NOT NULL DEFAULT 0,
  status           TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done','dismissed')),
  last_attempt_at  TEXT,
  snoozed_until    TEXT,
  PRIMARY KEY (kind, week_start, blog_id)
);
