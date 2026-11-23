"""Tripwires for the M19.1 honesty corrections of the Studio. They read the user-facing sources; they are not a proof.

Each test names the 0.18.1 behaviour it rejects. The behaviour of the wording itself is tested in
tests/ui_requirements.test.mjs (Node); the Cinematic View's panel texts are tested in tests/test_cinematic_cli.py
(they need VV_GODOT). The scanning guard of the verdict words is tests/test_honesty_wording.py.
"""

import os
import re
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UI = os.path.join(REPO, "desktop", "studio", "ui")


def read(*parts):
    with open(os.path.join(UI, *parts), encoding="utf-8") as f:
        return f.read()


def function_body(text, name):
    m = re.search(rf"export function {name}\(", text)
    assert m, name
    end = text.index("\n}\n", m.start())
    return text[m.start():end]


class SafetyChipIsNeutral(unittest.TestCase):
    """0.18.1 drew "No safety rule broken (5 checked)" in the green of a requirement that was met, beside failed requirements."""

    def test_the_safety_wording_never_returns_the_pass_class(self):
        body = function_body(read("js", "requirements.js"), "safetyWording")
        self.assertNotRegex(body, r"verdict:\s*'pass'")
        self.assertIn("verdict: 'held'", body)

    def test_a_safe_status_maps_to_held_not_pass(self):
        body = function_body(read("js", "model.js"), "verdictOfSafety")
        self.assertNotIn("'pass'", body)
        self.assertIn("'held'", body)

    def test_the_player_chip_for_safety_is_not_tone_ok(self):
        player = read("js", "views", "player.js")
        self.assertRegex(player, r"const safetyTone = sw\.verdict;")
        # tone(): held is its own tone, 'safe' no longer maps to the green one
        tone = player[player.index("function tone(status)"):player.index("function verdictChip")]
        self.assertIn("'held'", tone)
        self.assertNotRegex(tone, r"'safe'")

    def test_every_surface_that_draws_the_held_class_has_a_neutral_style(self):
        app, mission, control = read("css", "app.css"), read("css", "mission.css"), read("css", "control.css")
        self.assertRegex(app, r"\.v-held \.glyph")
        self.assertRegex(app, r"\.verdict\.v-held::before")
        self.assertRegex(mission, r"\.vchip\.v-held")
        self.assertRegex(control, r"\.v-held \.mc-v-s")
        for text in (app, mission, control):
            for rule in re.findall(r"[^{}]*\.v-held[^{}]*\{[^}]*\}", text):
                self.assertNotIn("--pass", rule, "a held rule is drawn in the green of a requirement that was met: " + rule.strip())
        self.assertIn("held: 'shield'", read("js", "verification.js"))
        self.assertIn("shield:", read("js", "dom.js"))
        self.assertIn("held: { word: 'held', tone: 'held' }", read("js", "views", "control.js"))


class NothingIsMetByDefault(unittest.TestCase):
    """0.18.1 wrote "Every requirement ... met." whenever no row failed, also when rows were not evaluated."""

    def test_the_met_sentences_come_from_the_shared_helper(self):
        for rel in (("js", "views", "player.js"), ("js", "views", "lab.js")):
            text = read(*rel)
            self.assertNotRegex(text, r"'Every requirement[^']*met\.[^']*'", rel[-1])
            self.assertIn("noFailureSentence(", text, rel[-1])

    def test_the_mission_chip_is_neutral_when_no_mission_requirement_is_listed(self):
        player = read("js", "views", "player.js")
        self.assertRegex(player, r"metFail\.length \? 'fail' : !missionReqs\.length \|\| /not evaluated/\.test\(missionText\) \? 'neutral' : 'pass'")


if __name__ == "__main__":
    unittest.main()
