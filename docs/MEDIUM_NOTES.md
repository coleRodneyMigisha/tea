# tea: Medium notes

## 1. How drafts get onto Medium

tea does not post. Medium no longer issues new API integration tokens, and its official API is unsupported, so tea's job ends at the clipboard. The owner pastes the draft into Medium's editor, edits it, and publishes.

**Copy for Medium** places rich text (HTML) and plain text on the clipboard. Rich text is the default because Medium's editor converts pasted formatting; raw Markdown pasted into it will not convert.

First-run check: paste a test draft into a Medium story editor and confirm headings, links, lists and block quotes survive. If anything breaks, record it in `docs/DEVIATIONS.md` and adjust `domain/medium.py`.

## 2. Formatting assumptions (verify on first paste)

Medium's editor offers a limited set of formats: a title, two heading sizes, bold, italic, links, bulleted and numbered lists, block quotes, code blocks, images and embeds. tea therefore:

- emits one H1 (the title), then H2 and H3 only;
- never emits tables, H4 or deeper, nested lists or raw HTML;
- warns in the **Check before posting** panel if an edited draft contains any of those.

## 3. Medium's AI content policy (as seen when this pack was written)

From Medium's help pages (`help.medium.com/hc/en-us/articles/22576852947223-Artificial-Intelligence-AI-content-policy` and the "Content not eligible for the paywall" page):

- Medium describes itself as being for human storytelling, not AI-generated writing.
- AI-generated writing is not allowed behind the paywall in the Partner Program, whether or not it is disclosed.
- Stories that include AI-generated text are expected to disclose it. Medium's own example is a sentence within the first two paragraphs, such as "This story was written with the assistance of an AI writing program." Undisclosed AI-assisted text can be limited to distribution on the author's personal network.
- Medium's definition of AI-generated writing, as reported by secondary sources, is writing where the majority of the content was produced by an AI program with little or no editing, improvement or fact-checking. The policy does not cover AI tools for outlining, spelling, grammar or fact-checking.
- AI-generated images need a caption saying so. tea generates no images.

**This policy changes.** Re-read the linked pages before the first post and every few months. The interpretation above is a summary, not legal or policy advice, and Medium alone decides how it applies to a given story.

## 4. What tea does about it

1. **Drafts are drafts.** The UI calls them drafts, the checklist asks the owner to edit in their own words, and the original generated text is kept alongside the owner's edits so the extent of editing is visible.
2. **Disclosure line.** On by default. **Copy for Medium** inserts the line after the first or second body paragraph. The wording is editable in Settings, and the owner can turn it off per copy. The one-time notice reads: "Medium asks writers to disclose AI-written text. tea adds a disclosure line when you copy."
3. **First-hand material comes from the owner.** The writing standard forbids invented anecdotes, so a draft only includes experience the owner supplied through answers or documents. This also makes edits more meaningful.
4. **Verification report.** Claims are checked against sources before the owner posts.
5. **No images, no embeds.** Nothing generated needs an image caption.

## 5. Not in scope

Paywall and Partner Program settings, tags, publications and the post's canonical link are set by the owner in Medium. These are original posts, so no canonical link is needed.
