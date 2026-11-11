# Milestone plans

Build in order. Each file is self-contained: what to read, what to build, what to test first, and how to know it is done. Start a milestone with `/milestone M<n>` in a fresh session (`/clear` first). Update `PROGRESS.md` at the end.

| ID | Milestone | Depends on |
|---|---|---|
| M0 | Scaffold | none |
| M1 | Data layer | M0 |
| M2 | Hand-off core: prompts, packets, reply parser, importer | M1 |
| M3 | Theme, shell and snapshot tool | M0 |
| M4 | Question system | M1, M3 |
| M5 | Weekly flow, scheduler, notifications | M1, M2, M3, M4 |
| M6 | Attachments | M1, M3 |
| M7 | Hand-off dialog, draft view, Medium copy | M2, M3, M6 |
| M8 | Manual mode | M4, M6, M7 |
| M9 | Pick mode and carry-over | M2, M5, M7 |
| M10 | Settings, install, doctor | all above |
| M11 | Hardening | all above |

Every plan ends the same way: all acceptance criteria checked with evidence, `make test` and `make lint` clean, `PROGRESS.md` updated, `/review M<n>` run, summary of at most 15 lines.

tea has **no network code and no API**. If a milestone seems to need one, stop and run `/deviation`.
