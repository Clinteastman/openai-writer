---
name: openai-writer
description: |
  Claude manages, OpenAI writes. Use for ANY customer-facing copy: product
  descriptions, taglines, features, meta descriptions, blog posts, articles,
  collection headers and footers, info pages, FAQs, mailouts, social posts.
  Claude gathers the facts and writes a brief, OpenAI drafts the text via the
  Codex CLI, Claude checks it with the scorers and publishes the file untouched.
  Also use when the user says "have OpenAI write it".
allowed-tools:
  - Read
  - Bash
  - Write
  - Grep
  - Glob
argument-hint: "<what to write, e.g. 'description for product 11259' or 'blog post on greenhouse heating'>"
---

# OpenAI Writer

Claude is the manager. OpenAI is the writer. Claude never writes or edits the prose.

## Where the scripts are

This skill's base directory is shown when it loads. The scripts are two levels up, in `scripts/`:

- `<base>/../../scripts/openai_write.py`
- `<base>/../../scripts/humanizer_score.py`

Run them with `python` on Windows and `python3` on macOS/Linux.

## Step 0: preflight (first use each session)

```bash
python <scripts>/openai_write.py --check
```

If it fails, tell the user exactly what is missing and stop. Do not write the copy yourself instead.

- `codex CLI not found`: `npm install -g @openai/codex`
- `too old`: `codex update`
- `not logged in`: the user runs `codex login` and signs in with their ChatGPT account

## Why "never edit the draft"

Anthropic marks Claude's text output. Any sentence Claude types or rewrites is Claude text again.

- Claude writes the **brief** (facts, format). That is instructions, not the deliverable.
- OpenAI writes the **content**, straight into a file.
- Claude does **not** retype, paraphrase, trim or "fix" the draft. Problems go back to OpenAI as a new brief.
- Publish with file-based flags where the tool offers them, so the text never passes through Claude's output.

## Workflow

### 1. Gather the facts (Claude)

OpenAI sees nothing except the brief. Collect real data first (product API, spec sheet, search queries, link URLs). Never guess a number. If a fact is missing, leave it out of the brief.

### 2. Write the brief

Use the Write tool to save a brief file (in the project's scratch folder, e.g. `_tmp/brief-<slug>.txt`). Include:

1. The task and the exact output format (HTML tags, fields, word counts, headings).
2. The facts, as a plain list, with "use only these".
3. Anything to preserve, and anything OpenAI must not touch.

Do **not** retype the writing rules. `openai_write.py` sends [writing-rules.txt](writing-rules.txt) with every brief: British English, banned words, 20-word sentences, installer tone, `&pound;<price>` shortcode, and the humanizer's mechanical patterns (no -ing fluff, no "not only", no vague sources, no em dashes, no curly quotes, no title-case headings). Edit that one file to change the rules for everyone. The humanizer's "add soul" advice is left out on purpose because it does not suit product or collection copy.

### 3. Send it

```bash
python <scripts>/openai_write.py --prompt-file _tmp/brief-<slug>.txt --out _tmp/draft-<slug>.html
```

- Default model `gpt-6.1-sol`. Override with `--model` and `--effort low|medium|high`.
- Runs in an empty scratch folder with a read-only sandbox. OpenAI cannot see the project.
- Prints only `OK: N words written to <path>`.
- One call per field when fields need different formats.

### 4. Check it (read, do not edit)

```bash
python <scripts>/humanizer_score.py _tmp/draft-<slug>.html          # 0-100, patterns + house rules
python <scripts>/humanizer_score.py _tmp/draft-<slug>.html --judge   # adds OpenAI rubric judge
```

85+ pass, 65-84 review, under 65 fail. Use `--judge` for blog posts and long copy.

Also check against the brief: no invented specs, format followed, length limits met.

### 5. Fix by re-briefing

If anything fails, write a new brief containing the draft and a short list of exact problems ("sentence 3 is 27 words", "remove 'seamless'"). Run `openai_write.py` again. Maximum 3 rounds, then stop and tell the user. Do **not** run any rewriting skill (such as a humanizer) on the draft: that is a Claude rewrite.

### 6. Publish the file as it is, then verify

Use the file flags of whatever publishes it (`--description-file`, `--content-file` and so on). If a field only accepts inline text (a short tagline or meta description), copy it exactly and tell the user that is the one place text passed through Claude.

Re-fetch the live item and confirm the change landed before reporting done.

## When working in the gscontent repo

If `tools/greenhouse6.py` exists in the project, also apply the repo rules:

- Use the matching publish skill for the target (`update-product`, `update-blog`, `update-footer`, `update-header`, `update-info`, `update-meta`). Follow their Hard Rules and formats, but take the prose from OpenAI's draft instead of writing it.
- Put the page spec structure into the brief: `page-specs/product-page-spec.md`, `page-specs/greenhouse-stores-article-checklist.md` or `page-specs/sister-store-blog-checklist.md`.
- Run the publish gate too: `python tools/ai_check.py <draft>`. `ai_score < 0.40` passes. This gate is mandatory before publishing anything.
- Never rename products, never add `<buy></buy>`, preserve shortcodes and video embeds, never rewrite `desc_side`.
- `--tagline` and `--meta-description` have no file flag, so copy those verbatim.

## Limits to tell the user

- OpenAI had no deployed text watermark at the last check (Oct 2026, secondary sources). That can change.
- Every Claude edit, summary or rewrite of the draft is Claude-marked text.
- A humanizer score of 100 means no known patterns, not "human".
- Facts must come from real data in the brief. OpenAI only phrases them.
- Each person uses their own ChatGPT login through Codex. Usage counts against that account.
