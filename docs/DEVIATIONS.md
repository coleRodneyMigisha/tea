# Deviations and open questions

The coding agent records here anything in the docs that was unclear, impossible, or wrong, with the choice it made. The owner reviews this file after each milestone.

| Date | Milestone | Issue | Choice made |
|---|---|---|---|
| 2026-11-11 | M0 | Docs target Ubuntu 24.04 with Python 3.12 (`python3.12-venv`); this machine runs Ubuntu 26.04 with Python 3.14 and no 3.12. | Local venv uses system `python3` (3.14, meets `requires-python >=3.12`, PySide6 6.12 installs). `make setup` takes `PY=...` to override. CI stays on ubuntu-24.04 with Python 3.12 so both versions are exercised. |
