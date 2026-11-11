# Decisions (final, from the owner)

These override anything else in the docs. If you find a conflict, log it with `/deviation`.

| # | Topic | Decision |
|---|---|---|
| D1 | Planned blogs | Not a feature. Other blogs are written one at a time through New blog. |
| D2 | No topic by Thursday | tea keeps asking Monday to Wednesday. If there is still no focus at Thursday 09:00 (configurable), that week goes into **pick mode**: Friday's prompt asks Claude to find a currently trending topic close to the owner's interests and then write the post. The owner can set their own focus any time before they paste the prompt into Claude. |
| D3 | Draft not used | An unused weekly draft is kept for one more week (configurable, 0 to 3). Questions continue, including some aimed at improving that draft. On the next Friday tea prepares an **improvement prompt** for it. After the carry-over limit it is shelved, not deleted. "Used" means the owner copied it for Medium or marked it posted. |
| D4 | Source files | tea does not read or upload files. The owner attaches them to the Claude chat themselves. tea stores a copy, keeps the list, and reminds the owner which files to attach. tea's own limits: 50 MB per file, 20 files per blog. Claude's chat has its own file limits; the owner checks those. |
| D5 | Academic citations | PDFs cited by page, plus the DOI when Claude sees one. Web research cited by URL and title. This is written into the prompt. |
| D6 | When the draft doesn't arrive | tea has nothing to retry, since the owner does the paste. Instead: notify when a prompt is ready, and remind at each login (2-hour pause between reminders) until the reply is imported. **Regenerate** prepares a fresh prompt. If a pasted reply can't be fully parsed, tea keeps the raw text, shows what is missing, and lets the owner fix or re-import. |
| D7 | Scheduling mechanism | A resident background app with catch-up logic, not systemd timers. |
| D8 | Default times | Focus prompt Monday 09:00. Pick mode Thursday 09:00. Prompt ready Friday 18:00. All configurable. |
| D9 | Writing engine | **Manual copy-paste with Claude (claude.ai).** No API key, no paid API, and tea makes no network calls at all. tea builds the prompt; the owner pastes it into a Claude chat and pastes the reply back. The hand-off sits behind a provider interface so an automated provider could be added later, but none is built now. |
| D10 | AI disclosure | On by default when copying for Medium, wording editable. |
| D11 | Weekly length | Standard (1,000 to 1,500 words) unless the answers say otherwise. |
| D12 | Login prompts | Fire when the background app starts. Unlock-triggered prompts are optional, in M11. |
| D13 | Interests | A list in Settings, seeded from `data/interests.json`, used for pick mode. |
| D14 | Questions | Template-based, with no AI step: seed bank, focus templates, improvement templates, scope templates (all in `data/`). The owner's answers go to Claude verbatim inside the prompt, so no separate style-profile call is needed. The owner can also keep free-text "style notes" in Settings, which go in every prompt. |
