"""Style checker for public text of the ERA V5 lab (G11 Release).

It finds four kinds of error (see style_guide.md):
  banned-word    a word from the banned list
  em-dash        the character U+2014 (and en-dash, U+2013: write "to" for a range)
  email          an email address
  long-sentence  a sentence with more than --max-words words (default 25)

Usage:
    python check_style.py <file.md or folder> [...] [--max-words 25] [--numbers]
    python check_style.py --list          # print the banned words
    python check_style.py --self-test     # the test file must give exactly 4 errors

Exit code: 0 when there are no errors, 1 otherwise (also when a path does not exist).
--numbers also lists every number as a warning: each number needs TSAI approval before it is published.
List markers such as "1." are not numbers.
Banned words are not checked inside code blocks, inline code, URLs and link targets.
Em-dashes, en-dashes and emails are checked everywhere.
The self-test also checks that style_guide.md lists the same banned words as BANNED.
"""
import argparse
import os
import re
import sys

BANNED = [
    "revolutionary", "revolutionise", "revolutionize", "groundbreaking", "ground-breaking", "breakthrough",
    "game-changer", "game-changing", "cutting-edge", "state-of-the-art", "SOTA", "world-class", "best-in-class",
    "world's first", "first-ever", "unprecedented", "unparalleled", "unmatched", "paradigm shift", "disruptive",
    "synergy", "leverage", "utilise", "utilize", "seamless", "seamlessly", "magic", "magical", "incredible",
    "amazing", "awesome", "mind-blowing", "flawless", "guaranteed", "human-level", "superhuman", "AGI",
    "sentient", "delve",
]
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
NUMBER = re.compile(r"(?<![\w.])\d[\d,.]*%?")

def banned_pattern(words):
    parts = []
    for w in words:
        p = r"[-\s]+".join(re.escape(x) for x in re.split(r"[-\s]+", w))
        parts.append(p.replace("'", "['" + chr(0x2019) + "]"))
    return re.compile(r"(?<![\w-])(?:" + "|".join(parts) + r")(?![\w-])", re.IGNORECASE)

BANNED_RE = banned_pattern(BANNED)

def guide_words(path):
    """The banned words as style_guide.md lists them: the paragraph of `words` after 'The banned words'."""
    text = open(path, encoding="utf-8").read()
    return re.findall(r"`([^`]+)`", text.split("The banned words", 1)[1].split("\n\n", 2)[1])

def prose_lines(text):
    """Yield (line_number, line) with code blocks, inline code, HTML comments and link targets blanked out.

    Blanking keeps the column numbers of the rest of the line.
    """
    blank = lambda m: " " * len(m.group())
    text = re.sub(r"<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group()), text, flags=re.S)
    fence = False
    for n, line in enumerate(text.split("\n"), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            yield n, ""
            continue
        if fence:
            yield n, ""
            continue
        line = re.sub(r"`[^`]*`", blank, line)
        line = re.sub(r"\]\([^)]*\)", lambda m: "]" + " " * (len(m.group()) - 1), line)
        line = re.sub(r"https?://\S+", blank, line)
        yield n, line

def units(lines):
    """Group lines into text units (paragraph, list item, heading, table row). Yield (start_line, text)."""
    cur, start = [], 0
    for n, line in lines:
        s = line.strip()
        new_unit = (not s or s.startswith(("#", "|", ">")) or re.match(r"^([-*+]|\d+[.)])\s", s))
        if new_unit and cur:
            yield start, " ".join(cur); cur = []
        if not s:
            continue
        if s.startswith(("#", "|")):
            yield n, s.strip("#| ")
            continue
        if not cur: start = n
        cur.append(re.sub(r"^([-*+>]|\d+[.)])\s+", "", s))
    if cur:
        yield start, " ".join(cur)

def sentences(text):
    for s in re.split(r"(?<=[.!?])[\"'" + chr(0x201d) + chr(0x2019) + r")\]]*\s+", text):
        if s.strip(): yield s.strip()

def check_text(text, max_words=25, numbers=False):
    """Return a list of (line, col, kind, message). kind is 'error' or 'warning'."""
    out = []
    # Em-dashes, en-dashes and emails are errors anywhere in the file, even in code or links.
    for n, raw in enumerate(text.split("\n"), 1):
        for m in re.finditer(EM_DASH, raw):
            out.append((n, m.start() + 1, "error", "em-dash: use a full stop, a comma or 'and'"))
        for m in re.finditer(EN_DASH, raw):
            out.append((n, m.start() + 1, "error", "en-dash: write 'to' for a range (24 to 31 Oct), or use a full stop or a comma"))
        for m in EMAIL.finditer(raw):
            out.append((n, m.start() + 1, "error", "email: no email addresses in public text"))
    lines = list(prose_lines(text))
    for n, line in lines:
        for m in BANNED_RE.finditer(line):
            out.append((n, m.start() + 1, "error", f"banned-word: '{m.group()}'"))
        if numbers:
            marker = re.match(r"\s*\d+[.)](?=\s)", line)   # a list marker, not a number
            for m in NUMBER.finditer(line):
                if marker and m.start() < marker.end(): continue
                out.append((n, m.start() + 1, "warning", f"number '{m.group()}': has TSAI approved it?"))
    for start, text_unit in units(lines):
        for s in sentences(text_unit):
            words = [w for w in s.split() if re.search(r"\w", w)]
            if len(words) > max_words:
                out.append((start, 1, "error", f"long-sentence: {len(words)} words (max {max_words}): '{' '.join(words[:8])} ...'"))
    return sorted(out)

def files_of(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, _, names in os.walk(p):
                for name in sorted(names):
                    if name.endswith((".md", ".txt")): yield os.path.join(root, name)
        else:
            yield p

def self_test():
    here = os.path.dirname(os.path.abspath(__file__))
    test = os.path.join(here, "tests", "four_errors.md")
    clean = "We read the data. We wrote the rules.\n\n- Team A: we built a checker.\n"
    errs = [x for x in check_text(open(test, encoding="utf-8").read()) if x[2] == "error"]
    kinds = sorted(x[3].split(":")[0] for x in errs)
    ok = len(errs) == 4 and kinds == ["banned-word", "em-dash", "email", "long-sentence"]
    ok = ok and not check_text(clean)
    print(f"self-test: {test} gives {len(errs)} errors {kinds}; clean sample gives {len(check_text(clean))}")
    range_kinds = [x[3].split(":")[0] for x in check_text("We met from 24" + EN_DASH + "31 Oct.\n")]
    ok = ok and range_kinds == ["en-dash"]
    print(f"self-test: a date range with an en-dash gives {range_kinds}")
    words = guide_words(os.path.join(here, "style_guide.md"))
    only_guide = [w for w in words if w not in BANNED]
    only_script = [w for w in BANNED if w not in words]
    ok = ok and not only_guide and not only_script
    print(f"self-test: style_guide.md lists {len(words)} banned words, the script {len(BANNED)}"
          + (f"; only in the guide: {only_guide}" if only_guide else "")
          + (f"; only in the script: {only_script}" if only_script else ""))
    print("self-test PASS" if ok else "self-test FAIL")
    return 0 if ok else 1

def main():
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Style checker for public text (G11 Release).")
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--max-words", type=int, default=25)
    ap.add_argument("--numbers", action="store_true", help="list numbers as warnings")
    ap.add_argument("--list", action="store_true", help="print the banned words")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.list:
        print("\n".join(BANNED)); return 0
    if a.self_test:
        return self_test()
    if not a.paths:
        ap.error("give at least one file or folder")
    missing = [p for p in a.paths if not os.path.exists(p)]
    for p in missing:
        print(f"path not found: {p}", file=sys.stderr)
    if missing:
        return 1
    errors = warnings = 0
    for path in files_of(a.paths):
        for line, col, kind, msg in check_text(open(path, encoding="utf-8").read(), a.max_words, a.numbers):
            print(f"{path}:{line}:{col}: {kind}: {msg}")
            errors += kind == "error"; warnings += kind == "warning"
    print(f"{errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main())
