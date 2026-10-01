// SessionStart hook: tells Claude who writes customer-facing copy.
// Anything printed to stdout is added to the session context.
const unattended = process.env.GITHUB_ACTIONS || process.env.CLAUDE_UNATTENDED;

if (unattended) {
  process.stdout.write(
    "OPENAI WRITER RULE (openai-writer plugin): unattended run detected. No user and no Codex login, " +
      "so the openai-writer skill is skipped. Follow the calling skill's steps as written.\n"
  );
} else {
  process.stdout.write(
    [
      "OPENAI WRITER RULE (openai-writer plugin).",
      "Customer-facing prose is written by OpenAI, not by you. That covers product descriptions, taglines,",
      "features, meta descriptions, blog posts, articles, collection headers and footers, info pages, FAQs,",
      "mailouts, social posts and comments.",
      "For these, invoke the openai-writer skill: you gather the facts and write the brief, OpenAI writes the",
      "draft to a file, you check it and publish the file as it is. Never edit, paraphrase or retype the draft.",
      "Fix problems by sending OpenAI a new brief. Do not run a humanizer or any rewriting skill on the draft.",
      "Any step in another skill that says write, rewrite or humanise copy means: brief OpenAI instead.",
      "Use --plain for plain-text output (social, comments, mailouts).",
      "Code, commit messages, analysis, explanations and internal notes are still written by you.",
      "If the skill fails or Codex is not set up, run its --check step, tell the user what is missing, and ask.",
      "Do not quietly write the copy yourself.",
    ].join("\n") + "\n"
  );
}
