# Progress

Updated by the coding agent at the end of every milestone. A fresh session reads this first.

| Milestone | Status | Commit | Notes (what was verified, what was not) |
|---|---|---|---|
| M0 Scaffold | done | b27ecf9 | Clean clone: `make setup && make test && make lint` pass (7 tests); `--help` lists all section 12 commands (test_cli); CI YAML parses, runs lint+test (not run on GitHub yet); test_no_network passes. Unverified: CI on GitHub. |
| M1 Data layer | not started | | |
| M2 Hand-off core | not started | | |
| M3 Theme, shell and snapshot tool | not started | | |
| M4 Question system | not started | | |
| M5 Weekly flow, scheduler, notifications | not started | | |
| M6 Attachments | not started | | |
| M7 Hand-off dialog, draft view, Medium copy | not started | | |
| M8 Manual mode | not started | | |
| M9 Pick mode and carry-over | not started | | |
| M10 Settings, install, doctor | not started | | |
| M11 Hardening | not started | | |

## Decisions and discoveries worth remembering

(Add short dated lines here. Anything that changes how later milestones work goes here and in `docs/DEVIATIONS.md`.)

- 2026-11-11: Dev machine is Ubuntu 26.04 / Python 3.14 (see DEVIATIONS). CI uses 3.12.
- 2026-11-11: ruff 0.17 formats Python blocks inside Markdown; `[tool.ruff] include` limits it to `.py`/`.pyi` so `make fmt` never touches `docs/`.
