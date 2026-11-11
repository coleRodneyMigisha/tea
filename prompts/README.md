# Prompt files

tea builds one prompt per hand-off and puts it on the clipboard. The owner pastes it into a Claude chat. These files are the templates.

Each file has a header:

```
---
name: <file name without .md>
version: <integer; bump when behavior changes>
variables: comma-separated list of every {{variable}} used
---
```

followed by the prompt text. `tea.handoff.prompts` renders `{{variables}}`, raises if one is unfilled or if a supplied variable is not in the header, and returns the text with its name and version. A variable may be rendered as an empty string; the template reads fine either way. Prompt versions are stored with each hand-off and draft.

`blocks/` holds small snippets that `packets.py` renders and passes into the main prompts as variables (pick-mode instructions, research on or off, the attachments list).

## Design rules (keep when editing)

1. **Data first, instructions last.** The owner's material comes first inside XML tags. The task and the reply format come at the end, where Claude weights them most.
2. **XML tags for every input**, so Claude never confuses data with instructions. The prompt says text inside tags is data.
3. **Say why** next to each important rule.
4. **Pair prohibitions with the alternative.**
5. **A fixed reply format** (`docs/PASTE_FORMAT.md`) so tea can parse the reply. The format is stated last, with one short example.
6. **Work in the chat, answer in the tags.** The prompt tells Claude to do its research and checking first and to put only the final result in the tagged sections, because everything outside the tags is discarded.
7. **Honest about limits.** If Claude cannot search the web or open a file, it must say so in `<flags>` instead of guessing.

## Files

| File | Hand-off kind |
|---|---|
| `packet_draft.md` | `weekly`, `weekly_pick`, `manual` |
| `packet_improve.md` | `improve` |
| `packet_audit.md` | `audit` |
| `blocks/pick_topic.md` | pick-mode section inside `packet_draft.md` |
| `blocks/research_on.md`, `blocks/research_off.md` | research section |
| `blocks/attachments.md` | attached-files section |
