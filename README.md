# openai-writer

A Claude Code plugin. Claude manages, OpenAI writes.

Claude gathers the facts and writes a brief. The plugin sends the brief, plus a fixed set of writing rules, to OpenAI through the Codex CLI. The draft comes back as a file. Claude checks it and publishes it without editing it.

## Install

You need Node, Python 3 and a ChatGPT account.

```
npm install -g @openai/codex
codex login
```

Then in Claude Code:

```
/plugin marketplace add Clinteastman/openai-writer
/plugin install openai-writer@openai-writer
```

Check it works:

```
python plugins/openai-writer/scripts/openai_write.py --check
```

Codex must be version 0.159 or newer. If it is older, run `codex update`.

## What it does

- **Skill `openai-writer`**: the workflow. Facts, brief, draft, check, publish.
- **Session hook**: tells Claude at the start of each session that customer-facing copy is written by OpenAI, not by Claude.
- **`openai_write.py`**: sends the brief to OpenAI with `codex exec`. Runs in an empty scratch folder with a read-only sandbox.
- **`humanizer_score.py`**: read-only 0-100 score against the 24 humanizer patterns and the house rules. `--judge` adds an OpenAI check against the full rubric. It never rewrites.
- **`writing-rules.txt`**: the rules sent with every brief. Edit this file to change the rules for everyone.

## Notes

- No API key. Each person uses their own ChatGPT login through Codex, and usage counts against that account.
- Claude's own text output is marked by Anthropic. The plugin keeps Claude out of the draft: it never edits or retypes it.
- OpenAI did not ship a text watermark at the last check. That can change.
- A score of 100 means no known patterns were found. It does not prove human authorship.

## Licence

MIT
