# tea: writing standard

This is the quality bar every draft is written to and checked against. It is turned into the prompts in `prompts/`. Read it so you understand what the prompts are trying to do, and so you can tune them.

"Research-backed" here means two things: the **method** follows published guidance on how people read and what makes content useful, and the **content** is tied to real sources and checked for unsupported claims.

## 1. Sources behind this standard

These are what the standard actually rests on. Where something is a working convention and not a research finding, it says so.

| Source | What it contributes | Limits |
|---|---|---|
| Google Search Central, "Creating helpful, reliable, people-first content" (`developers.google.com/search/docs/fundamentals/creating-helpful-content`) | Content should be original, answer the reader's question completely, show first-hand experience and expertise, and be trustworthy. Written for search quality, and built around the E-E-A-T idea: experience, expertise, authoritativeness, trust. | It is search guidance, not a formula for good writing. Used here as a quality checklist. |
| Jakob Nielsen, "How Users Read on the Web" (Nielsen Norman Group, 1997, `nngroup.com/alertbox/9710a.html`) and Morkes and Nielsen, "Concise, SCANNABLE, and Objective: How to Write for the Web" (1997) | Most readers scan. Their findings favor one idea per paragraph, the inverted pyramid (conclusion first), roughly half the word count of conventional prose, and plain objective language over promotional "marketese". Credibility drops when writing exaggerates. | Old studies on informational web pages. Later work reports similar scanning behavior, but long-form essays on Medium are a different case. Apply these as defaults for openings, paragraphs and tone, not as hard word limits. |
| Readability guidance summarizing NN/g work (Newcastle University editorial guidelines) | A reading level of about grade 9 or below for a general audience, up to grade 12 for experts. | Second-hand summary. Used only as a configurable default. |
| Medium's AI content policy (`help.medium.com/hc/en-us/articles/22576852947223`) | Disclosure and distribution rules for AI-written text. See `MEDIUM_NOTES.md`. | Policies change. Re-check before relying on it. |

Nothing else in this document is presented as research. The structure templates in section 4 are common working patterns.

## 2. Principles and the rules they become

**People first.** The post exists to help one specific reader.
- Rule: the draft states, near the top, what the reader will understand or be able to do after reading.
- Rule: no padding, no throat-clearing opener, no restating the topic before saying something.

**Conclusion first.**
- Rule: the first paragraph gives the main point or answer. Detail follows. A reader who stops after the first paragraph still has the gist.

**Scannable, not shallow.**
- Rule: one idea per paragraph, 1 to 4 sentences. Paragraphs begin with the point.
- Rule: descriptive H2 headings that say something ("Why handoffs fail"), not labels ("Background"). H3 only when a section genuinely splits.
- Rule: lists only for genuinely parallel items. Never a list of fragments standing in for an argument.

**Plain and credible.**
- Rule: concrete nouns and verbs. Prefer the short word. Define a term the first time it appears if the audience may not know it.
- Rule: no promotional language, superlatives or hype ("game-changing", "revolutionary", "unlock").
- Rule: state uncertainty plainly ("the evidence is thin", "this varies by context") and do not overclaim.

**Experience and expertise, honestly.**
- Rule: first-person experience, stories and opinions come **only** from the owner's answers or uploaded documents. If none were given, the draft contains no invented anecdotes, and Claude is told to flag "no first-hand material supplied" so the owner can add some.

**Backed by sources.**
- Rule: every statistic, date, named finding, quotation or non-obvious factual claim is traceable to a source tea has seen (uploaded text or a retrieved web page), or it is flagged.
- Rule: paraphrase. Quote only when the exact wording matters, keep quotes under 15 words, and attribute them.
- Rule: no invented sources, URLs, authors, DOIs or numbers. Ever.
- Rule: if the material is too thin for a strong post, say so in a short note above the draft and write a shorter, honest one.

## 3. Voice

The style profile (built from the owner's answers) overrides these defaults where they conflict.

- Default: first person when the owner supplied experience, otherwise a direct second person ("you") or neutral. Contractions are fine. Sentence length varies; mix short and long.
- Default readability: about grade 9 for general topics. If the audience answer says expert or academic, allow up to grade 12 and necessary jargon.
- **Avoid the common machine-writing tells.** The prompts tell Claude to rewrite any of these, and the optional second-pass check does it again:
  - Opening with a scene-setting cliché ("In today's fast-paced world", "In an era of…").
  - "It's not X, it's Y" constructions used as a rhetorical crutch; stacked rhetorical questions.
  - Forced triads ("fast, simple, and powerful") and symmetrical balanced pairs everywhere.
  - Inflated words and stock phrases: delve, tapestry, landscape, navigate (figuratively), unlock, leverage, game-changer, "at the end of the day", "it's important to note".
  - A one-line dramatic paragraph after every point; a neat moral closer on every section.
  - Em dashes used as the default punctuation. Prefer commas and full stops.
  - Bold labels at the start of every bullet; headings in Title Case.
  - Ending with a summary that repeats the post or a generic call to action.
- Endings: stop when the point is made. End on the last useful thing, or on the call to action the owner asked for.

## 4. Structure templates (working patterns, not research)

Claude picks one based on the topic and the owner's answers; the prompt does not force one.

1. **Explainer.** Question, short answer, why it works that way, evidence, what it means, what to do next.
2. **Argument.** Claim, reasons, the strongest objection, the response, the limits of the claim.
3. **Lessons from experience.** The situation, what was tried, what happened, what the owner would tell someone else. Requires first-hand material from the answers.
4. **How-to guide.** The outcome, prerequisites, steps, common mistakes, how to know it worked.
5. **Source synthesis.** The question, what the sources agree on, where they disagree, the owner's reading of it.

## 5. Length

| Setting | Words |
|---|---|
| Short | 600 to 900 |
| Standard | 1,000 to 1,500 |
| Long | 1,800 to 2,500 |

Hit the range without padding; if the material supports fewer words, write fewer.

## 6. Formatting for Medium

- One H1 title. H2 and H3 only below it. No tables, no H4 and deeper, no nested lists, no raw HTML.
- Web sources are linked inline in the text. End with a short **Sources** list (title, publisher, link). Uploaded documents are cited inline as (filename, p. N) and listed under Sources.
- No images are generated. Do not insert image placeholders.

## 7. Audit checklist (built into `prompts/packet_draft.md`, `packet_improve.md` and `packet_audit.md`)

1. Does the first paragraph give the main point?
2. Does every factual claim have a supporting source in the notes, or is it flagged?
3. Is there any anecdote or first-person claim not supported by the owner's answers or documents? Remove it.
4. Any invented-looking sources, numbers or quotes? Remove or flag.
5. Any machine-writing tells from section 3? Rewrite them.
6. Is every paragraph one idea? Are the headings informative?
7. Is the tone free of hype and consistent with the style profile?
8. Does it fit the length range and Medium formatting rules?
