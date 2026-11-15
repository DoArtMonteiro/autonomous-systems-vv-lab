"""A guard on the wording of verdicts.

The safety verdict reaches a person only as the shared phrase that counts rules (safetyWording in
desktop/studio/ui/js/requirements.js; mirrored by safety_phrase in desktop/cinematic/scripts/hud.gd and
by safety_phrase in desktop/platform/src/evidence.rs). This test scans the user-facing sources and fails
if the safety status or class is read in any way but a comparison with a literal, unless the place is
on an explicit, per-file allowlist with its reason, or if a bare "safe" or "Safe" is written as a verdict.

How the Studio scan works (a whole-file scan, so a statement split over several lines is seen too):
  1. comments are removed;
  2. comparisons with a literal (`x.safety.status === 'safe'`, `'unsafe' !== y`) are removed, because
     they decide something and print nothing;
  3. whatever still reads the status or class (`safety_status`, `safety_class`, `.safety.status`,
     `.safety.class`, a destructuring of `.safety`, or `.safety` kept in a variable) is a violation,
     unless the line is on the allowlist of its file.
`test_the_scan_catches_the_known_mutants` proves it on a set of snippets that must each be caught.
"""

import os
import re
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI = os.path.join(REPO, "desktop", "studio", "ui", "js")
CINEMATIC = os.path.join(REPO, "desktop", "cinematic", "scripts")
EVIDENCE = os.path.join(REPO, "desktop", "platform", "src", "evidence.rs")

LITERAL = r"""['"](?:safe|unsafe|not_evaluated)['"]"""
OPERAND = r"[\w$.\[\]?]+"
COMPARISONS = [
    re.compile(rf"{OPERAND}\s*(?:===|!==|==|!=)\s*{LITERAL}"),
    re.compile(rf"{LITERAL}\s*(?:===|!==|==|!=)\s*{OPERAND}"),
]
STATUS_READS = [
    re.compile(r"\bsafety_status\b"),
    re.compile(r"\bsafety_class\b"),
    re.compile(r"\.safety\s*\??\.\s*(?:status|class)\b"),
    # const { status } = rec.safety;  (the whole statement, possibly over several lines)
    re.compile(r"\{[^{}]*\b(?:status|class)\b[^{}]*\}\s*=(?![=>])[^;]*?\bsafety\b", re.S),
    # const s = rec.safety; ... s.status  (the object kept in a variable)
    re.compile(r"\.safety\b(?!\s*\??\.\s*(?:explanation|status|class)\b)"),
]

# Where the raw status or class may be read without being shown as a verdict: file, a pattern for the line, the reason.
ALLOW = {
    "verification.js": [(r"const cls = record\.safety\.class", "the safety class letter, shown as a class badge and not as a verdict")],
    "views/library.js": [
        (r"filter\.safety", "the filter compares the summary with the option the person picked; nothing is printed"),
        (r"const hay =", "the text the search box matches against, never displayed"),
        (r"verdictOfSafety\(s\.safety_status\)", "picks the glyph (a symbol); the words come from safetyBrokenText"),
        (r"class-badge", "the safety class letter as a class badge, not a verdict"),
    ],
    "views/compare.js": [(r"key: `\$\{r\.record\.safety\.status\}", "a grouping key that decides which cells look alike; never displayed")],
    "views/player.js": [(r"dataset: \{ outcome: rec\.outcome\.code, safety: rec\.safety\.status \}", "a data attribute read by the journeys; not text")],
}


# Files that are the shared wording itself: the one place that turns the status into words.
WHOLE_FILE = {"requirements.js": "safetyWording and summarySafetyText: the shared wording"}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def js_files():
    for root, _dirs, names in os.walk(UI):
        if "vendor" in root:
            continue
        for n in names:
            if n.endswith(".js"):
                yield os.path.join(root, n)


def strip_comments(text):
    """Comments out of the text, keeping the line numbers (a block comment keeps its newlines)."""
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"(?m)(^|\s)//.*$", r"\1", text)


def scan(text, rel, used=None):
    """The places of `text` that read the safety status or class other than by comparing it with a literal and that
    are not allowlisted for this file: [(line number, line)]. `used` collects the allowlist entries that matched."""
    code = strip_comments(text)
    for rx in COMPARISONS:
        code = rx.sub(lambda m: " " * len(m.group(0)), code)
    lines = code.splitlines()
    found = {}
    for rx in STATUS_READS:
        for m in rx.finditer(code):
            n = code.count("\n", 0, m.start())
            found[n] = lines[n]
    bad = []
    for n, line in sorted(found.items()):
        entries = ALLOW.get(rel, [])
        hit = [e for e in entries if re.search(e[0], line)]
        if hit:
            if used is not None:
                used.update((rel, e[0]) for e in hit)
            continue
        bad.append((n + 1, line.strip()[:140]))
    return bad


BARE = re.compile(r"""(?<![\w.])['"](Safe|safe)['"]""")
BARE_ALLOWED = re.compile(r"""(===|!==|==|!=)\s*['"]safe['"]|['"]safe['"]\s*(===|!==)|\[\s*\[?\s*['"]safe['"]\s*,|\?\s*['"]safe['"]""")

MUTANTS = {
    "a key attribute and the summary status": "h('td', {key:1}, m.summary.safety_status)",
    "a ternary that falls back to the raw status": "const t = x.safety.status === 'safe' ? 'all clear' : record.safety.status;",
    "the status as the argument of a chip": "verdictChip(record.safety.status)",
    "a template literal split over lines": "h('p', null, `Safety: ${\n  record.safety.status\n}`)",
    "a destructuring": "const {status} = rec.safety;",
    "a concatenation": "rec.safety.status + ' hay'",
    "optional chaining": "h('b', null, rec?.safety?.status)",
    "the object kept in a variable": "const s = rec.safety; h('b', null, s.status);",
    "the class of the summary": "h('i', null, s.safety_class)",
}
CLEAN = {
    "the domain's explanation": "h('p', null, prose(rec.safety.explanation))",
    "a comparison that decides and prints nothing": "const ok = rec.safety.status === 'safe' && rec.safety.class === 'not_evaluated';",
    "a reversed comparison": "if ('unsafe' === s.safety_status) mark();",
    "a comment": "// rec.safety.status is read in requirements.js only\nconst a = 1; /* s.safety_status */",
}


class VerdictWording(unittest.TestCase):
    def test_the_scan_catches_the_known_mutants(self):
        missed = [name for name, src in MUTANTS.items() if not scan(src, "views/new.js")]
        self.assertEqual(missed, [], "the scan misses: " + ", ".join(missed))
        wrongly = [name for name, src in CLEAN.items() if scan(src, "views/new.js")]
        self.assertEqual(wrongly, [], "the scan flags clean code: " + ", ".join(wrongly))

    def test_studio_reads_the_safety_status_only_through_the_shared_wording(self):
        bad = []
        used = set()
        for path in js_files():
            rel = os.path.relpath(path, UI).replace(os.sep, "/")
            if rel in WHOLE_FILE:
                continue
            for n, line in scan(read(path), rel, used):
                bad.append(f"{rel}:{n}: {line}")
        self.assertEqual(bad, [], "the safety status or class is read outside the shared wording:\n" + "\n".join(bad))
        stale = sorted((f, p) for f, es in ALLOW.items() for p, _r in es if (f, p) not in used)
        self.assertEqual(stale, [], "allowlist entries that no longer match anything (remove them): " + repr(stale))

    def test_no_bare_safe_verdict_string_in_the_studio(self):
        bad = []
        for path in js_files():
            for i, line in enumerate(read(path).splitlines(), 1):
                if line.lstrip().startswith(("*", "/*")):
                    continue  # a comment
                code = line.split("//")[0]
                for m in BARE.finditer(code):
                    if m.group(1) == "Safe" or not BARE_ALLOWED.search(code):
                        bad.append(f"{os.path.relpath(path, REPO)}:{i}: {line.strip()[:120]}")
                        break
        self.assertEqual(bad, [], "a bare safe or Safe string:\n" + "\n".join(bad))

    def test_no_whole_word_safe_in_visible_studio_text(self):
        """Case-insensitive: any whole word "safe" in the Studio's code must be an internal comparison or a filter option
        (the shared wording says "no safety rule broken"; mission titles and prose say the same)."""
        word = re.compile(r"(?<![\w-])safe(?![\w-])", re.IGNORECASE)
        bad = []
        for path in js_files():
            for i, line in enumerate(read(path).splitlines(), 1):
                if line.lstrip().startswith(("*", "/*", "//")):
                    continue
                code = line.split("//")[0]
                for rx in COMPARISONS:
                    code = rx.sub("", code)
                code = BARE_ALLOWED.sub("", code)
                if word.search(code):
                    bad.append(f"{os.path.relpath(path, REPO)}:{i}: {line.strip()[:120]}")
        self.assertEqual(bad, [], "a whole word safe in visible text:\n" + "\n".join(bad))

    def test_cinematic_panel_uses_the_rule_count_phrase(self):
        text = read(os.path.join(CINEMATIC, "hud.gd"))
        self.assertNotRegex(text, r"Safety: %s", "the panel must not print the raw safety status")
        self.assertIn("safety_phrase(record)", text)
        self.assertIn("this does not mean the vehicle is safe", text)
        for name in os.listdir(CINEMATIC):
            if name.endswith(".gd") and name != "hud.gd":
                src = read(os.path.join(CINEMATIC, name))
                self.assertNotRegex(src, r"Safety: ", f"{name} writes a safety verdict")

    def test_evidence_readme_uses_the_rule_count_phrase(self):
        text = read(EVIDENCE)
        self.assertNotIn("Safety: {}", text)
        self.assertNotRegex(text, r"record\.safety\.status,\s*\n", "the status must not be an argument of the README text")
        self.assertIn("safety_phrase(record)", text)
        self.assertIn("Safety rules: {}", text)


if __name__ == "__main__":
    unittest.main()
