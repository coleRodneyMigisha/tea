# Deviations and open questions

The coding agent records here anything in the docs that was unclear, impossible, or wrong, with the choice it made. The owner reviews this file after each milestone.

| Date | Milestone | Issue | Choice made |
|---|---|---|---|
| 2026-11-11 | M0 | Docs target Ubuntu 24.04 with Python 3.12 (`python3.12-venv`); this machine runs Ubuntu 26.04 with Python 3.14 and no 3.12. | Local venv uses system `python3` (3.14, meets `requires-python >=3.12`, PySide6 6.12 installs). `make setup` takes `PY=...` to override. CI stays on ubuntu-24.04 with Python 3.12 so both versions are exercised. |
| 2026-11-11 | M1 | Owner: "we don't need the disclosure". This conflicts with DECISIONS D10, ARCHITECTURE 7 and 9, SPEC 7 and 8, UI_DESIGN (Settings > Writing, draft checklist, notice) and MEDIUM_NOTES 2. | `Settings` has no disclosure fields (a test checks this). Later milestones (M7 `domain/medium.py`, M10 Settings screen) should leave out the disclosure insert, toggle and notice unless the owner says otherwise. Docs left unedited for the owner to update. |
| 2026-11-11 | M1 | No default or range given for "maximum answer words in a packet". | `max_answer_words` default 1500, range 200 to 5000. Schedule days are configurable as weekday 0 to 6 (owner approved). |
| 2026-11-11 | M1 | ARCHITECTURE 2 lists a single `db/repos.py`; all eight repos would exceed the 400-line rule. | `db/repos.py` (blogs, weeks, questions, answers, attachments, `Repos` bundle), `db/repos_flow.py` (drafts, handoffs, jobs), `db/rows.py` (row dataclasses), `db/base.py` (shared helpers). Import everything from `tea.db.repos`. |
| 2026-11-11 | M1 | `data/` and `prompts/` sit at the repo root, so `pipx install .` would not include them. | `pyproject.toml` force-includes them in the wheel as `tea/data` and `tea/prompts`; `config.resource_dir()` uses the bundled copy if present, else the repo root (owner approved). |
