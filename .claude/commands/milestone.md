---
description: Start a tea build milestone (for example /milestone M3)
argument-hint: M0 .. M11
---
Work on milestone $ARGUMENTS.

1. Read `CLAUDE.md`, `PROGRESS.md` and `plan/$ARGUMENTS.md`. Then read only the docs and sections that plan file lists under "Read first". If an earlier milestone is not marked done in `PROGRESS.md`, stop and tell me.
2. Give me a short plan: files you will create or change, the order, the tests you will write first, and anything in the docs that is unclear or conflicts. Ask your questions now, all at once. Then wait for my go-ahead before editing anything.
3. After I approve: write the tests first and run them to see them fail. Implement. Run `make test` and `make lint` until clean. For any UI work, render snapshots with `python -m tea.devtools.snap` and look at them against `docs/UI_DESIGN.md` (once M3 has built that tool).
4. Check every acceptance criterion in the plan file and record the evidence for each.
5. Update `PROGRESS.md`. Commit in logical pieces with conventional messages. Do not push.
6. Run `/review $ARGUMENTS`, fix what it finds, then give me a summary of at most 15 lines: what is done, what you could not verify, what I should try by hand.
