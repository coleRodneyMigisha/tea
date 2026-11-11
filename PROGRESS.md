# Progress

Updated by the coding agent at the end of every milestone. A fresh session reads this first.

| Milestone | Status | Commit | Notes (what was verified, what was not) |
|---|---|---|---|
| M0 Scaffold | done | b27ecf9 | Clean clone: `make setup && make test && make lint` pass (7 tests); `--help` lists all section 12 commands (test_cli); CI YAML parses, runs lint+test (not run on GitHub yet); test_no_network passes. Unverified: CI on GitHub. |
| M1 Data layer | done | 0b4dbba | 137 tests pass, `make lint` clean, `make run` starts. AC1 test_db_schema (idempotent, matches DATA_MODEL.sql incl. indexes); AC2 test_repos, 100% line coverage of tea.db (unique bank_key, (blog_id,version), jobs PK; cascades; draft delete nulls handoff.draft_id); AC3 test_weeks (year ends, leap year, London DST weeks 167/169 h); AC4 test_settings round trip + first-run seed; AC5 test_clock grep. Wheel contents checked by `pip wheel` listing. Unverified: `pipx install` from the wheel end to end; TEA_NOW by hand. |
| M2 Hand-off core | done | 6cc1452 | 275 tests pass, `make lint` clean, `make run` starts. AC1 test_prompts (all 7 templates, header == placeholders, strict render); AC2 test_cli_handoff + manual run on sample data: weekly/weekly_pick/improve have 0 `{{` and 0 blank runs, pick adds <topic_pick>, improve has edited draft and only new answers; AC3 test_parse (every malformed fixture, fuzz, 1 MB reply; never raises); AC4 test_importer pick test + CLI round trip (focus, topic, title, auto_trending, 3 candidates); AC5 test_research_off_when_web_and_academic_off: research_off used, but fixed packet_draft.md text still mentions searching (DEVIATIONS); AC6 three packets read, notes below. handoff coverage 96%+. Unverified: a real Claude reply pasted from claude.ai. |
| M3 Theme, shell and snapshot tool | done | ed8b535 | 358 tests pass, `make lint` clean, app starts (offscreen smoke run). AC1 test_theme (both modes render, palette from tokens, System follows `colorSchemeChanged`, set via test slot); AC2 test_single_instance + smoke run with real processes (2nd launch and `--background` exit 0, first logs `ipc_message kind=show`), test_main_window close hides with tray; AC3 `.snapshots/*-empty-{light,dark}.png`, `this_week-paused-*`, `this_week-empty-dark-125.png` read by me and ui-checker, fixes in ed8b535; AC4 test_ui_hygiene (hex, named colors, font names, px and size literals); AC5 `tea doctor` prints UI/Reading font family and source, tray. Unverified: real GNOME Wayland (tray via AppIndicator, live dark/light switch, window position restore, raise/focus on 2nd launch), real-display font rendering. |
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
- 2026-11-11: Packets take a blog's week from the blog (`packets.week_of`), never from the caller, so improve/audit never pick up the current week's focus answers.
- 2026-11-11: Research is on only when the blog allows `web` or `academic` (`weekly_pick` always on). M5 must create weekly blogs with sensible `allowed_sources`; the schema default `[]` gives `research_off`.
- 2026-11-11: `import_reply(repos, handoff_id, text)` raises `LookupError` only for a missing hand-off or blog; bad replies return warnings (`no_topic` added for pick replies without a topic). M7 maps warning codes to plain words.
- 2026-11-11: Dev loop: `TEA_DATA_DIR=... python -m tea.devtools.sample_data --write-replies DIR`, then `tea packet --kind ...` and `tea import-reply DIR/reply_weekly.txt`.
- 2026-11-11: AC6 notes for the owner (prompt files untouched): empty `<my_style_notes>`, `<context></context>` and `<new_answers>` tags render as empty pairs; packet_draft always mentions research and web search; the writing standard's structure templates (section 4) are not in the prompt; WRITING_STANDARD says a thin-material note goes "above the draft" but the prompt (correctly, for parsing) puts it in flags; pick block says do not guess without search while research block says write from files and answers, so a no-search pick reply has no topic; scale answers render as "2 (on a scale from X to Y)" with no range until M4 fixes how scales are stored.
- 2026-11-11: Look follows the owner's Ghostty: dark mode = Synthwave tokens, UI font JetBrains Mono, reading Newsreader; light stays celadon. Dark steep ring uses `color.steep_stops_dark` (M5: use `theme.steep_stops()`).
- 2026-11-11: Widgets get every size, color and font from `Theme` (`size`, `space`, `type_px`, `color`, `font`, `icon`); `test_ui_hygiene` fails on literals. QSS rules go in `assets/theme.qss.tmpl`; comments are stripped before `{{token}}` substitution.
- 2026-11-11: Fonts are static instances (variable fonts register as one Regular style in Qt). Regenerate with `tools/make_static_fonts.py`.
- 2026-11-11: Snapshot states: `snap.register(screen, state, State(screen, seed=..., settings={...}))`. The offscreen screen is 800 x 600, so `restoreGeometry` clamps; geometry test uses scale 0.8.
- 2026-11-11: `SingleInstance.release()` must disconnect client sockets, or pytest-qt teardown segfaults. Paths: `config.runtime_dir()` (TEA_RUNTIME_DIR), `window.ini` in state dir.
- 2026-11-11: Not yet themed: `assets/tea.svg` keeps light colors in the dark rail (ui-checker minor). `Ctrl+Shift+C` and `Ctrl+Return` wait for M7/M4; tray "Answer questions now" just opens the window until M4. SIGTERM exits without saving geometry (normal quit and tray Quit save it).
