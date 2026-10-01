#!/usr/bin/env python3
"""Score a draft against the humanizer skill's AI-writing patterns. Read-only.

This never rewrites anything. It checks the 24 patterns from the humanizer
checklist (based on Wikipedia's "Signs of AI writing") and prints which ones
fired, with quotes, plus a 0-100 score (100 = no tells found).

Two checks:
    default   Deterministic regex checks for the mechanical patterns, plus the
              house writing rules (banned words, 20-word sentences, literal pound).
    --judge   Also asks OpenAI (via openai_write.py in this folder) to score the
              draft against the full rubric. Catches the semantic tells a regex
              cannot (inflated significance, vague sourcing, voice).
              Claude is not in this loop, so nothing is rewritten by Claude.

Verdict: score >= 85 PASS (exit 0), 65-84 REVIEW (exit 2), < 65 FAIL (exit 1).

Usage:
    python humanizer_score.py draft.html
    python humanizer_score.py draft.html --json
    python humanizer_score.py draft.html --judge
    python humanizer_score.py --text "Our comprehensive range..."
"""
# tool-conventions: exempt - small scoring report with its own --json shape, not a site API CLI
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

PASS_MIN = 85
REVIEW_MIN = 65

# ---------------------------------------------------------------------------
# Pattern definitions. (number, name, weight per hit, kind, data)
# kind "phrases": plain case-insensitive substrings. kind "regex": regex list.
# Numbers match the sections in the humanizer SKILL.md.
# ---------------------------------------------------------------------------

SIGNIFICANCE = [
    "stands as", "serves as", "is a testament", "a testament to", "pivotal moment",
    "evolving landscape", "focal point", "key turning point", "indelible mark",
    "deeply rooted", "marking the", "shaping the", "represents a shift",
    "reflects broader", "setting the stage", "a vital role", "a crucial role",
    "a pivotal role", "a significant role", "underscores the importance",
    "highlights the importance", "enduring legacy",
]
PROMOTIONAL = [
    "boasts a", "nestled", "in the heart of", "must-visit", "breathtaking",
    "perfect for", "perfect piece", "exquisite", "timeless elegance",
    "transform your", "stunning", "beautifully", "the perfect blend", "renowned",
    "groundbreaking", "vibrant", "rich heritage", "commitment to",
]
AI_VOCAB = [
    "additionally", "align with", "crucial", "delve", "emphasizing", "enduring",
    "enhance", "fostering", "garner", "highlight", "interplay", "intricate",
    "intricacies", "pivotal", "showcase", "tapestry", "testament", "underscore",
    "valuable", "comprehensive", "robust", "seamless", "leverage", "elevate",
    "unleash", "unlock", "landscape", "state-of-the-art",
]
FILLER = [
    "in order to", "due to the fact that", "at this point in time",
    "in the event that", "has the ability to", "it is important to note",
    "it is worth noting", "at its core", "in today's", "when it comes to",
    "needless to say", "it goes without saying",
]
CHATBOT = [
    "i hope this helps", "let me know if", "of course!", "certainly!",
    "here is a ", "here's a ", "would you like me", "feel free to",
]
SYCOPHANCY = ["great question", "you're absolutely right", "excellent point", "that's a great"]
HEDGES = [
    "could potentially", "may possibly", "might have some", "it could be argued",
    "it might be argued", "arguably", "to some extent", "in some ways",
]
CUTOFF = ["while specific details", "as of my last", "based on available information", "up to my last training"]
GENERIC_CONCLUSION = [
    "future looks bright", "exciting times", "journey toward", "journey towards",
    "step in the right direction", "only time will tell", "the possibilities are endless",
]
NEG_PARALLEL = ["not just", "not merely", "not only", "it's not about", "it isn't just"]

RE_ING = re.compile(
    r",\s+(ensuring|highlighting|underscoring|emphasizing|emphasising|reflecting|symbolizing|"
    r"symbolising|contributing|cultivating|fostering|encompassing|showcasing)\b", re.I)
RE_COPULA = re.compile(r"\b(serves as|stands as|functions as|acts as|boasts|represents a|marks a)\b", re.I)
RE_VAGUE = re.compile(
    r"\b(experts (say|believe|argue|agree)|industry (reports|observers|experts)|studies (show|suggest)|"
    r"observers have|some critics|many (customers|people|gardeners) (say|believe|love)|"
    r"widely (regarded|considered|known))\b", re.I)
RE_CHALLENGES = re.compile(r"\b(despite (these|its|the) challenges|faces (several |many )?challenges)\b", re.I)
RE_THREE = re.compile(r"\b[A-Za-z-]+, [A-Za-z-]+,? and [A-Za-z-]+\b")
RE_RANGE = re.compile(r"\bfrom [^.,;]{3,40} to [^.,;]{3,40}, from\b", re.I)
RE_EMDASH = re.compile("—|&mdash;")
RE_CURLY = re.compile("[“”‘’]|&[lr]dquo;|&[lr]squo;")
RE_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF✀-➿]")
RE_INLINE_HEADER = re.compile(r"<li[^>]*>\s*<(?:strong|b)>[^<]{1,40}:\s*</(?:strong|b)>|^\s*[-*]\s+\*\*[^*]{1,40}:\*\*", re.I | re.M)

# Repo writing rules (CLAUDE.md), reported separately from the humanizer patterns.
BANNED = ["comprehensive", "robust", "seamless", "unleash", "elevate", "state-of-the-art", "unlock", "delve", "landscape"]
AMERICAN = ["aluminum", "color", "colors", "authorized", "center", "gray", "meter", "meters", "powder coated"]

# (id, label, weight per hit, humanizer section)
WEIGHTS = {
    "significance": ("Significance and legacy inflation", 1.5, "1"),
    "promotional": ("Promotional language", 1.5, "4"),
    "ing_fluff": ("Superficial -ing phrases", 1.0, "3"),
    "vague_attribution": ("Vague attributions", 1.5, "5"),
    "challenges": ("Formulaic challenges section", 1.5, "6"),
    "ai_vocab": ("Overused AI vocabulary", 1.5, "7"),
    "copula_avoidance": ("Copula avoidance (serves as, boasts)", 1.0, "8"),
    "negative_parallel": ("Negative parallelism", 1.5, "9"),
    "rule_of_three": ("Rule of three", 0.4, "10"),
    "false_range": ("False ranges", 1.0, "12"),
    "em_dash": ("Em dashes", 1.5, "13"),
    "inline_header_list": ("Inline-header bold lists", 1.0, "15"),
    "title_case_heading": ("Title Case headings", 1.0, "16"),
    "emoji": ("Emojis", 2.0, "17"),
    "curly_quotes": ("Curly quotation marks", 0.5, "18"),
    "chatbot": ("Chatbot artifacts", 3.0, "19"),
    "cutoff": ("Knowledge-cutoff disclaimers", 2.0, "20"),
    "sycophancy": ("Sycophantic tone", 2.0, "21"),
    "filler": ("Filler phrases", 1.0, "22"),
    "hedging": ("Excessive hedging", 1.0, "23"),
    "generic_conclusion": ("Generic positive conclusion", 2.0, "24"),
}


def strip_html(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&pound;|&nbsp;|&amp;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def block_text(raw: str) -> str:
    """Plain text with a section sign marking the end of each HTML block (li, p, h2...)."""
    return strip_html(re.sub(r"</(?:li|p|h[1-6]|div|tr|td|th)>", " § ", raw))


def sentences(text: str) -> list[str]:
    out = []
    for block in text.split("§"):
        for p in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9<\"'])", block):
            if len(p.split()) >= 2:
                out.append(p.strip())
    return out


def snippet(text: str, start: int, end: int, pad: int = 40) -> str:
    return text[max(0, start - pad):min(len(text), end + pad)].replace("\n", " ").strip()


def find_phrases(haystack: str, needles: list[str]) -> list[tuple[str, str]]:
    low = haystack.lower()
    hits = []
    for n in needles:
        for m in re.finditer(re.escape(n.lower()), low):
            hits.append((n, snippet(haystack, m.start(), m.end())))
    return hits


def find_regex(haystack: str, rx: re.Pattern) -> list[tuple[str, str]]:
    return [(m.group(0), snippet(haystack, m.start(), m.end())) for m in rx.finditer(haystack)]


def title_case_headings(html: str) -> list[tuple[str, str]]:
    out = []
    for inner in re.findall(r"<h[2-4][^>]*>([^<]+)</h[2-4]>", html, flags=re.I):
        words = re.findall(r"[A-Za-z']+", inner.strip())
        if len(words) >= 3 and sum(1 for w in words if w[0].isupper()) >= max(2, int(0.7 * len(words))):
            out.append((inner.strip(), inner.strip()))
    for inner in re.findall(r"^#{2,4}\s+(.+)$", html, flags=re.M):
        words = re.findall(r"[A-Za-z']+", inner)
        if len(words) >= 3 and sum(1 for w in words if w[0].isupper()) >= max(2, int(0.7 * len(words))):
            out.append((inner.strip(), inner.strip()))
    return out


def run_patterns(raw: str) -> tuple[dict, str]:
    text = strip_html(raw)
    found: dict[str, list[tuple[str, str]]] = {
        "significance": find_phrases(text, SIGNIFICANCE),
        "promotional": find_phrases(text, PROMOTIONAL),
        "ing_fluff": find_regex(text, RE_ING),
        "vague_attribution": find_regex(text, RE_VAGUE),
        "challenges": find_regex(text, RE_CHALLENGES),
        "ai_vocab": find_phrases(text, AI_VOCAB),
        "copula_avoidance": find_regex(text, RE_COPULA),
        "negative_parallel": find_phrases(text, NEG_PARALLEL),
        "rule_of_three": find_regex(text, RE_THREE),
        "false_range": find_regex(text, RE_RANGE),
        "em_dash": find_regex(raw, RE_EMDASH),
        "inline_header_list": find_regex(raw, RE_INLINE_HEADER),
        "title_case_heading": title_case_headings(raw),
        "emoji": find_regex(raw, RE_EMOJI),
        "curly_quotes": find_regex(raw, RE_CURLY),
        "chatbot": find_phrases(text, CHATBOT),
        "cutoff": find_phrases(text, CUTOFF),
        "sycophancy": find_phrases(text, SYCOPHANCY),
        "filler": find_phrases(text, FILLER),
        "hedging": find_phrases(text, HEDGES),
        "generic_conclusion": find_phrases(text, GENERIC_CONCLUSION),
    }
    # AI vocab "highlight" etc. should not double-count inside words like "highlights" noise: fine.
    return found, text


def repo_rules(raw: str, text: str) -> dict:
    banned = find_phrases(text, BANNED)
    american = [(w, c) for w, c in find_phrases(text, AMERICAN) if re.search(rf"\b{re.escape(w)}\b", c, re.I)]
    long_sents = [s for s in sentences(block_text(raw)) if len(s.split()) > 20]
    return {
        "banned_words": banned,
        "american_spellings": american,
        "sentences_over_20_words": [(f"{len(s.split())} words", s[:90]) for s in long_sents],
        "literal_pound_sign": [("£", c) for _, c in find_regex(raw, re.compile("£"))],
    }


def rhythm(text: str) -> dict:
    lens = [len(s.split()) for s in sentences(text)]
    if len(lens) < 6:
        return {"sentences": len(lens), "note": "too short to judge rhythm"}
    sd = statistics.pstdev(lens)
    return {
        "sentences": len(lens),
        "mean_words": round(statistics.mean(lens), 1),
        "stdev_words": round(sd, 1),
        "note": "very uniform sentence length (monotone)" if sd < 3.5 else "ok",
    }


def score(found: dict, word_count: int) -> float:
    total = 0.0
    for key, hits in found.items():
        total += WEIGHTS[key][1] * len(hits)
    density = total / max(word_count, 60) * 100  # weighted tells per 100 words
    return round(100 * math.exp(-density / 6), 1)


def verdict(s: float) -> tuple[str, int]:
    if s >= PASS_MIN:
        return "PASS", 0
    if s >= REVIEW_MIN:
        return "REVIEW", 2
    return "FAIL", 1


JUDGE_BRIEF = """You are a strict editor scoring a draft against a checklist of AI-writing patterns.
Do NOT rewrite the draft. Score it.

PATTERNS (from the humanizer checklist):
1 Undue emphasis on significance, legacy, broader trends
2 Undue emphasis on notability or media coverage
3 Superficial -ing phrases adding fake depth
4 Promotional or advertisement-like language
5 Vague attributions and weasel words
6 Formulaic "challenges and future" outlines
7 Overused AI vocabulary (crucial, pivotal, showcase, underscore, tapestry, landscape and similar)
8 Copula avoidance (serves as, stands as, boasts instead of is/has)
9 Negative parallelisms (not only X but Y)
10 Rule of three overuse
11 Elegant variation (synonym cycling)
12 False ranges (from X to Y where not a real scale)
13 Em dash overuse
14 Mechanical boldface
15 Inline-header vertical lists
16 Title Case headings
17 Emojis
18 Curly quotes
19 Chatbot artifacts
20 Knowledge-cutoff disclaimers
21 Sycophantic tone
22 Filler phrases
23 Excessive hedging
24 Generic positive conclusions
Also judge: uniform sentence rhythm, no concrete detail, invented or unverifiable facts (studies, quotes, numbers with no source).

Reply with ONLY a JSON object, no code fences, in this shape:
{"score": <0-100, 100 means no AI tells>, "verdict": "PASS|REVIEW|FAIL",
 "findings": [{"pattern": <number or "rhythm" or "invented-fact">, "severity": "low|medium|high", "quote": "<exact short quote from the draft>", "why": "<one short sentence>"}]}
Only list real findings. Quote exactly. 85+ is PASS, 65-84 REVIEW, under 65 FAIL.

DRAFT:
"""


def run_judge(raw: str, model: str | None) -> dict:
    with tempfile.TemporaryDirectory() as td:
        brief = Path(td) / "judge_brief.txt"
        out = Path(td) / "judge_out.txt"
        brief.write_text(JUDGE_BRIEF + raw, encoding="utf-8")
        cmd = [sys.executable, str(Path(__file__).resolve().parent / "openai_write.py"),
               "--prompt-file", str(brief), "--out", str(out), "--no-rules"]
        if model:
            cmd += ["--model", model]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if proc.returncode != 0 or not out.exists():
            return {"error": (proc.stderr or proc.stdout)[-600:]}
        reply = out.read_text(encoding="utf-8").strip()
    m = re.search(r"\{[\s\S]*\}", reply)
    try:
        return json.loads(m.group(0)) if m else {"error": "no JSON in reply", "reply": reply[:400]}
    except json.JSONDecodeError:
        return {"error": "bad JSON in reply", "reply": reply[:400]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", help="Draft file, or - for stdin")
    ap.add_argument("--text", help="Score this text instead of a file")
    ap.add_argument("--json", action="store_true", help="Machine-readable output")
    ap.add_argument("--judge", action="store_true", help="Also run the OpenAI rubric judge")
    ap.add_argument("--judge-model", help="Model for the judge (default: openai_write.py default)")
    ap.add_argument("--quotes", type=int, default=3, help="Quotes shown per pattern (default 3)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if args.text is not None:
        raw = args.text
    elif args.path == "-":
        raw = sys.stdin.read()
    elif args.path:
        raw = Path(args.path).read_text(encoding="utf-8")
    else:
        ap.error("give a file, - for stdin, or --text")

    found, text = run_patterns(raw)
    words = len(text.split())
    s = score(found, words)
    label, code = verdict(s)
    rules = repo_rules(raw, text)
    rh = rhythm(block_text(raw))
    bold = len(re.findall(r"<(?:strong|b)\b|\*\*", raw))

    result = {
        "score": s, "verdict": label, "words": words,
        "patterns": {k: {"section": WEIGHTS[k][2], "label": WEIGHTS[k][0], "hits": len(v),
                         "examples": [c for _, c in v[:args.quotes]]} for k, v in found.items() if v},
        "repo_rules": {k: {"hits": len(v), "examples": [c for _, c in v[:args.quotes]]} for k, v in rules.items() if v},
        "rhythm": rh, "bold_count": bold,
    }
    if args.judge:
        result["judge"] = run_judge(raw, args.judge_model)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Humanizer score: {s}/100  {label}  ({words} words)")
        for k, v in result["patterns"].items():
            print(f"  [{v['section']:>2}] {v['label']}: {v['hits']}")
            for ex in v["examples"]:
                print(f"        ...{ex}...")
        if result["repo_rules"]:
            print("Repo writing rules:")
            for k, v in result["repo_rules"].items():
                print(f"  {k}: {v['hits']}")
                for ex in v["examples"]:
                    print(f"        ...{ex}...")
        print(f"Rhythm: {rh.get('note')} (sentences {rh.get('sentences')}, stdev {rh.get('stdev_words', '-')})")
        if bold > 12:
            print(f"Bold: {bold} bold marks (check it is not mechanical emphasis)")
        if "judge" in result:
            j = result["judge"]
            if "error" in j:
                print(f"Judge error: {j['error']}")
            else:
                print(f"OpenAI judge: {j.get('score')}/100  {j.get('verdict')}")
                for f in j.get("findings", [])[:12]:
                    print(f"  [{f.get('pattern')}] {f.get('severity')}: \"{f.get('quote')}\" - {f.get('why')}")
    return code


if __name__ == "__main__":
    sys.exit(main())
