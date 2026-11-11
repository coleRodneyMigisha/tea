# Progress

Updated by the coding agent at the end of every milestone. A fresh session reads this first.

| Milestone | Status | Commit | Notes (what was verified, what was not) |
|---|---|---|---|
| M0 Scaffold | done | b27ecf9 | Clean clone: `make setup && make test && make lint` pass (7 tests); `--help` lists all section 12 commands (test_cli); CI YAML parses, runs lint+test (not run on GitHub yet); test_no_network passes. Unverified: CI on GitHub. |
| M1 Data layer | done | 0b4dbba | 137 tests pass, `make lint` clean, `make run` starts. AC1 test_db_schema (idempotent, matches DATA_MODEL.sql incl. indexes); AC2 test_repos, 100% line coverage of tea.db (unique bank_key, (blog_id,version), jobs PK; cascades; draft delete nulls handoff.draft_id); AC3 test_weeks (year ends, leap year, London DST weeks 167/169 h); AC4 test_settings round trip + first-run seed; AC5 test_clock grep. Wheel contents checked by `pip wheel` listing. Unverified: `pipx install` from the wheel end to end; TEA_NOW by hand. |
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
- 2026-11-11: Owner dropped the AI disclosure feature. Settings has no disclosure fields; M7 and M10 should skip the disclosure insert, toggle and notice (see DEVIATIONS).
- 2026-11-11: Use `ON CONFLICT DO NOTHING`, never `INSERT OR IGNORE`: OR IGNORE also swallows CHECK violations.
- 2026-11-11: Repos take `(conn, clock)`; `Repos(conn, clock)` bundles all eight; timestamps are `clock.iso()` strings with offset; week starts are `date` values. Compare stored times with `julianday()`, not string order.
- 2026-11-11: Subtract aware datetimes in UTC when measuring durations: Python ignores offsets when both share one tzinfo.
