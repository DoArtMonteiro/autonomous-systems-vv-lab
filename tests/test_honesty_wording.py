"""A guard on the wording of verdicts.

The safety verdict reaches a person only as the shared phrase that counts rules (safetyWording in
desktop/studio/ui/js/requirements.js; mirrored by safety_phrase in desktop/cinematic/scripts/hud.gd and
by safety_phrase in desktop/platform/src/evidence.rs). This test scans the user-facing sources and fails
if safety.status or safety_status is rendered as text any other way, or if a bare "safe" or "Safe" is
written as a verdict. Internal comparisons such as `=== 'safe'` are allowed.
"""

import os
import re
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI = os.path.join(REPO, "desktop", "studio", "ui", "js")
CINEMATIC = os.path.join(REPO, "desktop", "cinematic", "scripts")
EVIDENCE = os.path.join(REPO, "desktop", "platform", "src", "evidence.rs")

STATUS = re.compile(r"safety\.status|safety_status|safety\.class|safety_class")
# Lines that read the status without rendering it as text.
COMPARISON = re.compile(r"(===|!==|==|!=)\s*['\"](safe|unsafe|not_evaluated)['\"]|['\"](safe|unsafe|not_evaluated)['\"]\s*(===|!==)")
INTERNAL = ("key:", "dataset:", "verdictChip(", "hay", "filter.safety", "verdictOfSafety(", "const cls = record.safety.class", "const unjudged")
BARE = re.compile(r"""(?<![\w.])['"](Safe|safe)['"]""")
BARE_ALLOWED = re.compile(r"""(===|!==|==|!=)\s*['"]safe['"]|['"]safe['"]\s*(===|!==)|\[\s*\[?\s*['"]safe['"]\s*,|\?\s*['"]safe['"]""")


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


class VerdictWording(unittest.TestCase):
    def test_studio_never_renders_the_bare_safety_status(self):
        bad = []
        for path in js_files():
            if path.endswith("requirements.js"):
                continue  # the one place that turns the status into words
            for i, line in enumerate(read(path).splitlines(), 1):
                if line.lstrip().startswith(("*", "/*")):
                    continue
                code = line.split("//")[0]
                if STATUS.search(code) and not COMPARISON.search(code) and not any(k in code for k in INTERNAL):
                    bad.append(f"{os.path.relpath(path, REPO)}:{i}: {line.strip()[:120]}")
        self.assertEqual(bad, [], "safety status rendered outside the shared wording:\n" + "\n".join(bad))

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
                code = COMPARISON.sub("", code)
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
