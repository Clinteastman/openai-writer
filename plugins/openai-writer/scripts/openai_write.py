#!/usr/bin/env python3
"""Send a writing brief to OpenAI (via the Codex CLI) and save the reply to a file.

Claude Code writes the brief. OpenAI writes the content. The text goes straight
to --out and is never printed, so the calling agent does not re-type it.

Uses the ChatGPT login already held by the Codex CLI. No API key needed.
Check your setup with: python openai_write.py --check

Usage:
    python openai_write.py --check
    python openai_write.py --prompt-file brief.txt --out draft.html
    python openai_write.py --prompt-file brief.txt --out draft.html --model gpt-5.5 --effort medium
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PREAMBLE = (
    "You are a professional copywriter. Write the content described in the brief below.\n"
    "Do not run commands, read files or browse. Use only the facts given in the brief.\n"
    "Never invent specifications, dimensions, prices or claims.\n"
    "Reply with the finished content only: no preamble, no commentary, no code fences.\n\n"
)

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "skills" / "openai-writer" / "writing-rules.txt"
MIN_CODEX = (0, 159, 0)  # gpt-6.1-sol is rejected on a ChatGPT login before this


def check_setup() -> int:
    """Preflight: Codex CLI installed, new enough, and logged in."""
    codex = shutil.which("codex")
    if not codex:
        print("FAIL: codex CLI not found. Install: npm install -g @openai/codex")
        return 2
    ver = subprocess.run([codex, "--version"], capture_output=True, text=True).stdout
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", ver)
    print(f"codex: {ver.strip()}")
    if m and tuple(int(x) for x in m.groups()) < MIN_CODEX:
        print("FAIL: codex is too old for gpt-6.1-sol. Run: codex update")
        return 3
    login = subprocess.run([codex, "login", "status"], capture_output=True, text=True)
    print(f"login: {(login.stdout or login.stderr).strip()}")
    if login.returncode != 0 or "logged in" not in (login.stdout + login.stderr).lower():
        print("FAIL: not logged in. Run: codex login")
        return 4
    print("OK: ready")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="Check Codex is installed, current and logged in, then exit")
    ap.add_argument("--prompt-file", help="File holding the writing brief")
    ap.add_argument("--out", help="File to write OpenAI's reply to")
    ap.add_argument("--model", default="gpt-6.1-sol",
                    help="Model slug (default gpt-6.1-sol). Needs Codex CLI 0.159+ on a ChatGPT login")
    ap.add_argument("--effort", choices=["low", "medium", "high"], help="Reasoning effort override")
    ap.add_argument("--rules-file", default=str(DEFAULT_RULES),
                    help="Fixed writing rules sent with every brief (default: the plugin's writing-rules.txt)")
    ap.add_argument("--no-rules", action="store_true", help="Send the brief without the fixed rules")
    ap.add_argument("--timeout", type=int, default=600, help="Seconds before giving up (default 600)")
    args = ap.parse_args()

    if args.check:
        return check_setup()
    if not args.prompt_file or not args.out:
        ap.error("--prompt-file and --out are required")

    codex = shutil.which("codex")
    if not codex:
        print("ERROR: codex CLI not found on PATH. Run: python openai_write.py --check", file=sys.stderr)
        return 2

    brief = Path(args.prompt_file).read_text(encoding="utf-8")
    rules = "" if args.no_rules else Path(args.rules_file).read_text(encoding="utf-8") + "\n\n"
    prompt = PREAMBLE + rules + "BRIEF:\n" + brief
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    cmd = [
        codex, "exec",
        "--sandbox", "read-only",
        "--skip-git-repo-check",
        "--ephemeral",
        "--output-last-message", str(out),
        "--model", args.model,
    ]
    if args.effort:
        cmd += ["-c", f'model_reasoning_effort="{args.effort}"']
    cmd.append("-")  # read the prompt from stdin

    # Run from an empty scratch directory so the agent cannot read the caller's project.
    with tempfile.TemporaryDirectory(prefix="openai_write_") as scratch:
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                encoding="utf-8",
                capture_output=True,
                cwd=scratch,
                timeout=args.timeout,
            )
        except subprocess.TimeoutExpired:
            print(f"ERROR: codex timed out after {args.timeout}s", file=sys.stderr)
            return 3

    if proc.returncode != 0 or not out.exists() or not out.read_text(encoding="utf-8").strip():
        print(f"ERROR: codex exec failed (exit {proc.returncode}). Run: python openai_write.py --check", file=sys.stderr)
        print((proc.stderr or proc.stdout)[-1500:], file=sys.stderr)
        return 4

    words = len(out.read_text(encoding="utf-8").split())
    print(f"OK: {words} words written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
