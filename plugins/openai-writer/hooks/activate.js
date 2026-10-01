// SessionStart hook: tells Claude who writes customer-facing copy.
// Anything printed to stdout is added to the session context.
process.stdout.write(
  [
    "OPENAI WRITER RULE (openai-writer plugin).",
    "Customer-facing prose is written by OpenAI, not by you. That covers product descriptions, taglines,",
    "features, meta descriptions, blog posts, articles, collection headers and footers, info pages, FAQs,",
    "mailouts and social posts.",
    "For these, invoke the openai-writer skill: you gather the facts and write the brief, OpenAI writes the",
    "draft to a file, you check it and publish the file as it is. Never edit, paraphrase or retype the draft.",
    "Fix problems by sending OpenAI a new brief.",
    "Code, commit messages, analysis, explanations and internal notes are still written by you.",
    "If the skill fails or Codex is not set up, run its --check step, tell the user what is missing, and ask.",
    "Do not quietly write the copy yourself. Exception: unattended runs with no user present keep their",
    "existing behaviour.",
  ].join("\n") + "\n"
);
