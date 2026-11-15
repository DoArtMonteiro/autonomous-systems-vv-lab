"""A guard on the wording of verdicts.

The safety verdict reaches a person only as the shared phrase that counts rules (safetyWording in
desktop/studio/ui/js/requirements.js; mirrored by safety_phrase in desktop/cinematic/scripts/hud.gd and
by safety_phrase in desktop/platform/src/evidence.rs). This test reads the user-facing sources and fails
if the safety status or class is read in any way but a comparison with a literal, unless that exact
expression is on an explicit allowlist with its reason, or if a bare "safe" or "Safe" is written as a verdict.

How the scan of the Studio works (whole files, so a statement split over several lines is seen too):
  1. comments are removed (a tokenizer that knows strings, template literals and regular expressions, so a
     "//" inside a string is not a comment);
  2. comparisons with a literal (`x.safety.status === 'safe'`, `'unsafe' !== y`) are removed, because they decide
     something and print nothing;
  3. whatever still reads the status or class is a violation: `safety_status`, `safety_class`, `safety.status`,
     `.safety['status']`, `{ status } = x.safety`, `{ safety } = x`, `{ safety: { status } }`, `.safety` kept in a
     variable, and a "Safety: " literal (a verdict prefix);
  4. a bare 'safe' or 'Safe' string, and any whole word "safe" in the code, is a violation.
An allowlist entry names the file, the exact read and the exact expression it may appear in, with the reason; an
entry that matches nothing fails the test. requirements.js is scanned too, except inside the functions of the
shared wording itself. The Cinematic View's hud.gd is scanned for the same reads (`get("status")`, `%s` formatting of a
status) and for a "Safety: " literal.
`test_the_scan_catches_the_mutants` proves it on a set of snippets, each of which must be caught, and on clean
snippets that must not be.
"""

import os
import re
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI = os.path.join(REPO, "desktop", "studio", "ui", "js")
CINEMATIC = os.path.join(REPO, "desktop", "cinematic", "scripts")
EVIDENCE = os.path.join(REPO, "desktop", "platform", "src", "evidence.rs")


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


# ------------------------------------------------------------------------------------------ comments

def _skip_string(text, i):
    q = text[i]
    j = i + 1
    while j < len(text) and text[j] != q and text[j] != "\n":
        j += 2 if text[j] == "\\" else 1
    return min(j, len(text) - 1)


def _skip_template(text, i):
    j = i + 1
    while j < len(text):
        c = text[j]
        if c == "\\":
            j += 2
        elif c == "`":
            return j
        elif text.startswith("${", j):
            depth, j = 1, j + 2
            while j < len(text) and depth:
                d = text[j]
                if d in "'\"":
                    j = _skip_string(text, j)
                elif d == "`":
                    j = _skip_template(text, j)
                elif d == "{":
                    depth += 1
                elif d == "}":
                    depth -= 1
                j += 1
        else:
            j += 1
    return len(text) - 1


def strip_js(text):
    """The code without its comments (line numbers kept); strings, templates and regular expressions are kept whole."""
    out, i, n, prev = [], 0, len(text), ""
    while i < n:
        c = text[i]
        if c in "'\"":
            j = _skip_string(text, i)
            out.append(text[i:j + 1])
            i, prev = j + 1, c
        elif c == "`":
            j = _skip_template(text, i)
            out.append(text[i:j + 1])
            i, prev = j + 1, c
        elif c == "/" and text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif c == "/" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * text.count("\n", i, j))
            i = j
        elif c == "/" and (prev == "" or prev in "(,=:[!&|?{};+-*%<>~^"):
            j, in_class = i + 1, False
            while j < n and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "[":
                    in_class = True
                elif text[j] == "]":
                    in_class = False
                elif text[j] == "/" and not in_class:
                    break
                j += 1
            out.append(text[i:j + 1])
            i, prev = j + 1, "/"
        else:
            out.append(c)
            if not c.isspace():
                prev = c
            i += 1
    return "".join(out)


def strip_gd(text):
    """GDScript without its '#' comments (a '#' inside a string stays)."""
    out = []
    for line in text.split("\n"):
        in_s, k = False, 0
        while k < len(line):
            ch = line[k]
            if ch == "\\" and in_s:
                k += 2
                continue
            if ch == '"':
                in_s = not in_s
            elif ch == "#" and not in_s:
                line = line[:k]
                break
            k += 1
        out.append(line)
    return "\n".join(out)


# ------------------------------------------------------------------------------------------ what counts as a read

LITERAL = r"""['"](?:safe|unsafe|not_evaluated)['"]"""
OPERAND = r"[\w$.\[\]?]+"
COMPARISONS = [
    re.compile(rf"{OPERAND}\s*(?:===|!==|==|!=)\s*{LITERAL}"),
    re.compile(rf"{LITERAL}\s*(?:===|!==|==|!=)\s*{OPERAND}"),
]
KEY = r"""['"](?:status|class)['"]"""
JS_READS = [
    re.compile(r"\bsafety_status\b"),
    re.compile(r"\bsafety_class\b"),
    re.compile(r"\bsafety\s*\??\s*\.\s*(?:status|class)\b"),                       # safety.status, rec.safety?.class
    re.compile(rf"""['"]safety['"]\s*\]\s*\??\.?\s*\[\s*{KEY}\s*\]"""),             # rec['safety']['status']
    re.compile(rf"\bsafety\s*\??\.?\s*\[\s*{KEY}\s*\]"),                             # rec.safety?.['status']
    re.compile(r"\{[^{}]*\b(?:status|class)\b[^{}]*\}\s*=(?![=>])[^;]*?\bsafety\b", re.S),   # const { status } = rec.safety
    re.compile(r"\{[^{}]*\bsafety\b[^{}]*\}\s*=(?![=>])"),                           # const { safety } = rec
    re.compile(r"\bsafety\s*:\s*\{[^{}]*\b(?:status|class)\b[^{}]*\}"),             # ({ safety: { status } }) =>
    re.compile(r"\.safety\b(?!\s*\??\s*\.\s*(?:explanation|status|class)\b)(?!\s*\??\.?\s*\[)"),   # .safety kept in a variable
    re.compile(r"""['"`]\s*Safety\s*:"""),                                           # a "Safety: " verdict prefix
]

# Where a read is allowed without being shown as a verdict: file, the exact read, the exact expression it sits in, why.
ALLOW = {
    "verification.js": [
        (r"^safety\.class$", r"const cls = record\.safety\.class;", "the safety class letter, drawn as a class badge and not as a verdict"),
    ],
    "views/library.js": [
        (r"^safety_status$", r"s\.safety_status !== filter\.safety", "the filter compares the summary with the option the person picked; nothing is printed"),
        (r"^\.safety$", r"filter\.safety && s\.safety_status !== filter\.safety", "the filter's own option (filter.safety), not a record"),
        (r"^safety_status$", r"const hay = \[m\.run_id, m\.label,.*s\.safety_status, s\.safety_class \|\| ''", "the text the search box matches against, never displayed"),
        (r"^safety_class$", r"const hay = \[m\.run_id, m\.label,.*s\.safety_status, s\.safety_class \|\| ''", "the same search text"),
        (r"^safety_status$", r"verdictOfSafety\(s\.safety_status\)", "picks the glyph (a symbol); the words come from safetyBrokenText"),
        (r"^safety_class$", r"s\.safety_class && !unjudged \? h\('span', \{ class: \['class-badge', `class-\$\{s\.safety_class\}`\] \}, s\.safety_class\) : null", "the safety class letter as a class badge, not a verdict"),
    ],
    "views/compare.js": [
        (r"^safety\.(status|class)$", r"key: `\$\{r\.record\.safety\.status\}\$\{r\.record\.safety\.class\}\$\{sw\.broken\}`", "a grouping key that decides which cells look alike; never displayed"),
    ],
    "views/player.js": [
        (r"^safety\.status$", r"dataset: \{ outcome: rec\.outcome\.code, safety: rec\.safety\.status \}", "a data attribute read by the journeys; not text"),
    ],
}
# requirements.js is scanned; reads are allowed only inside these functions (the shared wording).
WORDING_FAMILY = ("safetyWording", "summarySafetyText")

# Bare 'safe' strings that are not verdicts: file, the exact expression, why.
BARE_ALLOW = {
    "views/library.js": [("[['safe', 'none broken'], ['unsafe', 'a rule broken']]", "the options of the Safety rules filter; the value is the summary's status, the words are the labels")],
}


def _family_lines(code):
    """Line numbers (0-based) inside the functions of the shared wording."""
    lines = code.split("\n")
    inside, span = set(), None
    for n, line in enumerate(lines):
        m = re.match(r"export function (\w+)\(", line)
        if m:
            span = n if m.group(1) in WORDING_FAMILY else None
        if span is not None:
            inside.add(n)
            if line.startswith("}"):
                span = None
    return inside


def scan_js(text, rel, used=None):
    """[(line, why)] of every place of the JavaScript `text` that reads the safety status or class, prints a bare safe,
    or prefixes a verdict with "Safety: ", other than a comparison with a literal and the allowlisted expressions."""
    code = strip_js(text)
    for rx in COMPARISONS:
        code = rx.sub(lambda m: " " * len(m.group(0)), code)
    lines = code.split("\n")
    family = _family_lines(code) if rel == "requirements.js" else set()
    bad = []
    for rx in JS_READS:
        for m in rx.finditer(code):
            n = code.count("\n", 0, m.start())
            if n in family:
                continue
            read = re.sub(r"\s+", "", m.group(0))
            ok = False
            for entry in ALLOW.get(rel, []):
                if re.search(entry[0], read) and re.search(entry[1], lines[n]):
                    ok = True
                    if used is not None:
                        used.add((rel, entry[0], entry[1]))
            if not ok:
                bad.append((n + 1, f"reads the safety status or class: {read[:60]}  |  {lines[n].strip()[:100]}"))
    # a bare 'safe' string and any whole word safe
    allowed = code
    for expr, _why in BARE_ALLOW.get(rel, []):
        if expr in allowed:
            allowed = allowed.replace(expr, " " * len(expr))
            if used is not None:
                used.add((rel, "bare", expr))
    word = re.compile(r"(?<![\w-])safe(?![\w-])", re.IGNORECASE)
    for n, line in enumerate(allowed.split("\n")):
        if word.search(line):
            bad.append((n + 1, f"the word safe: {line.strip()[:100]}"))
    return sorted(set(bad))


GD_READS = [
    re.compile(r"""["'][^"'\n]*\bSafety\s*:[^"'\n]*["']"""),                                                    # "Safety: ..." text
    re.compile(r"""str\(\s*[\w.]+\.get\(\s*"(?:status|class)"[^)\n]*\)\s*\)"""),                                # str(x.get("status", ""))
    re.compile(r"""[\w.]+\.get\(\s*"(?:status|class)"[^)\n]*\)"""),                                              # x.get("status")
    re.compile(r""""[^"\n]*%s[^"\n]*"\s*%\s*(?:\[[^\]\n]*\bstatus\b[^\]\n]*\]|status\b)"""),                  # "...%s" % status
]
GD_COMPARISON = re.compile(r"""(?:str\(\s*)?[\w.]+\.get\(\s*"(?:status|class)"[^)\n]*\)\s*\)?\s*(?:==|!=)\s*"[^"\n]*\"""")


def scan_gd(text, rel):
    """[(line, why)] of the GDScript places that format or print a status or class, or write a "Safety: " verdict."""
    code = strip_gd(text)
    code = GD_COMPARISON.sub(lambda m: " " * len(m.group(0)), code)
    bad = []
    for rx in GD_READS:
        if rx is not GD_READS[0] and rel != "hud.gd":
            continue  # only the panel formats verdicts; record.gd and the others read statuses to parse them
        for m in rx.finditer(code):
            n = code.count("\n", 0, m.start())
            bad.append((n + 1, f"GDScript prints or formats a status: {m.group(0).strip()[:90]}"))
    return sorted(set(bad))


def violations(text, rel):
    return scan_gd(text, rel) if rel.endswith(".gd") else scan_js(text, rel)


# ------------------------------------------------------------------------------------------ the mutants

HUD = "hud.gd"
MUTANTS = [
    ("a 'Safety: ' prefix on a status", "views/run.js", "h('p', null, 'Safety: ' + run.status);"),
    ("a template that prints the word safe", "views/run.js", "h('p', null, `Result ${r.safe ? 'safe' : ''}`);"),
    ("a multi-line concatenation", "views/run.js", "const t = 'Safety: ' +\n  rec.safety\n    .status;"),
    ("a destructured status that is rendered", "views/run.js", "const { status } = rec.safety;\nh('b', null, status);"),
    ("hud.gd formats a status with %s", HUD, "func _m5(status):\n\tvar t = \"Safety: %s\" % status\n"),
    ("a ternary that renders a bare word", "views/run.js", "h('b', null, rec.safety.status === 'safe' ? 'safe' : 'unsafe');"),
    ("{ safety } taken out, then safety.status", "views/run.js", "const { safety } = rec;\nh('b', null, safety.status);"),
    ("an arrow parameter destructure", "views/run.js", "const f = ({ safety: { status } }) => h('b', null, status);"),
    ("hud.gd words a verdict from the status", HUD, "func _m9(s):\n\tvar t = \"The vehicle is %s\" % str(s.get(\"status\", \"\"))\n"),
    ("a class-badge line that smuggles the raw status", "views/library.js", "h('span', { class: ['class-badge'] }, s.safety_status);"),
    ("bracket access", "views/run.js", "h('b', null, rec['safety']['status']);"),
    ("optional chaining with a bracket", "views/run.js", "h('b', null, rec.safety?.['status']);"),
    ("the status read in requirements.js outside the wording", "requirements.js", "export const leak = (s) => s.safety_status;"),
    ("a ternary with two bare words", "views/run.js", "h('b', null, ok ? 'safe' : 'unsafe');"),
    ("a text node that says safe", "views/run.js", "h('b', null, 'All safe');"),
    ("the class of a summary printed", "views/run.js", "h('b', null, m.summary.safety_class);"),
    ("a key attribute and the summary status", "views/new.js", "h('td', {key:1}, m.summary.safety_status)"),
    ("a ternary that falls back to the raw status", "views/new.js", "const t = x.safety.status === 'safe' ? 'all clear' : record.safety.status;"),
    ("a template literal split over lines", "views/new.js", "h('p', null, `Safety: ${\n  record.safety.status\n}`)"),
    ("optional chaining", "views/new.js", "h('b', null, rec?.safety?.status)"),
    ("the object kept in a variable", "views/new.js", "const s = rec.safety; h('b', null, s.status);"),
    ("a '//' inside a string hiding the rest of the line", "views/new.js", "h('a', { href: 'https://x' }, 'a'); h('b', null, rec.safety.status);"),
]
CLEAN = [
    ("the domain's explanation", "views/new.js", "h('p', null, prose(rec.safety.explanation))"),
    ("a comparison that decides and prints nothing", "views/new.js", "const ok = rec.safety.status === 'safe' && rec.safety.class === 'not_evaluated';"),
    ("a reversed comparison", "views/new.js", "if ('unsafe' === s.safety_status) mark();"),
    ("comments", "views/new.js", "// rec.safety.status is read in requirements.js only\nconst a = 1; /* s.safety_status 'safe' */"),
    ("a URL in a string and a comment", "views/new.js", "const u = 'https://example.org/a'; // rec.safety.status"),
    ("the shared wording in requirements.js", "requirements.js", "export function safetyWording(record) {\n  const x = record.safety.status;\n  return x;\n}\n"),
    ("hud.gd comparing a status", HUD, "func f(s):\n\tif str(s.get(\"status\", \"\")) == \"unsafe\" or str(s.get(\"class\", \"\")) != \"x\":\n\t\treturn 1\n"),
    ("hud.gd comment", HUD, "# \"Safety: %s\" % status in a comment\nvar a = 1\n"),
]


class VerdictWording(unittest.TestCase):
    def test_the_scan_catches_the_mutants(self):
        missed = [name for name, rel, src in MUTANTS if not violations(src, rel)]
        self.assertEqual(missed, [], "the guard misses: " + ", ".join(missed))
        wrongly = [(name, violations(src, rel)) for name, rel, src in CLEAN if violations(src, rel)]
        self.assertEqual(wrongly, [], "the guard flags clean code")

    def test_studio_reads_the_safety_status_only_through_the_shared_wording(self):
        bad, used = [], set()
        for path in js_files():
            rel = os.path.relpath(path, UI).replace(os.sep, "/")
            for n, why in scan_js(read(path), rel, used):
                bad.append(f"{rel}:{n}: {why}")
        self.assertEqual(bad, [], "the safety status or class is read, or a verdict is written, outside the shared wording:\n" + "\n".join(bad))
        wanted = {(f, e[0], e[1]) for f, es in ALLOW.items() for e in es} | {(f, "bare", e) for f, es in BARE_ALLOW.items() for e, _w in es}
        self.assertEqual(sorted(wanted - used), [], "allowlist entries that match nothing (remove them)")

    def test_the_cinematic_panel_formats_no_status_and_writes_no_safety_prefix(self):
        for name in sorted(os.listdir(CINEMATIC)):
            if name.endswith(".gd"):
                bad = scan_gd(read(os.path.join(CINEMATIC, name)), name)
                self.assertEqual(bad, [], f"{name}: " + "; ".join(why for _n, why in bad))
        text = read(os.path.join(CINEMATIC, "hud.gd"))
        self.assertIn("safety_phrase(record)", text)
        self.assertIn("this does not mean the vehicle is safe", text)

    def test_evidence_readme_uses_the_rule_count_phrase(self):
        text = read(EVIDENCE)
        self.assertNotIn("Safety: {}", text)
        self.assertNotRegex(text, r"record\.safety\.status,\s*\n", "the status must not be an argument of the README text")
        self.assertIn("safety_phrase(record)", text)
        self.assertIn("Safety rules: {}", text)


if __name__ == "__main__":
    unittest.main()
