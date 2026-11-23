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
        # the tone is computed from the statuses (missionTone, tested in Node), never by a regular expression on the text
        self.assertIn("verdictChip(missionText, missionTone(rec), 'Mission')", player)
        self.assertNotIn("/not evaluated/.test(", player)


class NoPlumeAfterTheLastSample(unittest.TestCase):
    """0.18.1 kept the plume of the last sample lit while the playback of a longer run went on after the contact."""

    def test_the_stage_scene_draws_no_plume_past_the_last_sample(self):
        text = read("js", "scenes", "rocket.js")
        # structural: the rule itself (plumeLengthAt in model.js) is tested in Node; this only checks that the scene uses it
        self.assertIn("const len = plumeLengthAt(ch, t);", text)
        self.assertRegex(read("js", "model.js"), r"t > times\[times\.length - 1\] \+ 1e-9\) return 0;")
        # the geospatial and cinematic stage scenes inherit setTime and read this.plumeLength
        for name in ("geo.js", "rocket-cinema.js"):
            self.assertIn("super.setTime(t)", read("js", "scenes", name))

    def test_the_player_state_exposes_the_plume_length_for_the_journeys(self):
        self.assertIn("plumeM:", read("js", "views", "player.js"))
        for name in ("geo.js", "rocket-cinema.js"):
            self.assertIn("plume: () => r3.plumeLength || 0", read("js", "scenes", name))


class MissionCompletionIsNotTheDistanceToTheGoal(unittest.TestCase):
    """0.18.1 showed "To goal 0.00 mm" beside "Mission incomplete" with nothing about the clause of mission_completion that failed."""

    def test_the_reading_follows_the_text_the_ground_host_writes(self):
        with open(os.path.join(REPO, "desktop", "domain-ground", "src", "record.rs"), encoding="utf-8") as f:
            record = f.read()
        # completionFacts (requirements.js) parses exactly this observed text; if the host changes it, change both.
        self.assertIn('"{code}; {done} of {total} waypoint(s) reached; {final_distance} mm from the goal at the end"', record)
        self.assertIn("export function completionFacts(", read("js", "requirements.js"))

    def test_the_goal_distance_readouts_say_it_is_not_completion(self):
        text = read("js", "session.js")
        self.assertEqual(text.count("Mission completion requirement"), 2)

    def test_the_player_result_shows_the_facts_under_the_verdict_chips(self):
        self.assertIn("completionFacts(rec)", read("js", "views", "player.js"))


class RunPillsNeverCutTheConditions(unittest.TestCase):
    """0.18.1, at 1024x640, cut the name and the conditions of the pills that were not selected with an ellipsis."""

    def compact_block(self):
        css = read("css", "mission.css")
        start = css.index("@media (max-width: 1100px) and (max-height: 700px)")
        return css[start:css.index("\n}\n", start)]

    def test_no_pill_text_is_cut_with_an_ellipsis_in_the_compact_layout(self):
        block = self.compact_block()
        for line in block.splitlines():
            if ".pl-run" in line and not line.strip().startswith("/*"):
                self.assertNotIn("text-overflow", line, line)
        self.assertNotRegex(block, r"max-width: \d+ch")
        self.assertIn(".pl-run-n", block)
        self.assertRegex(block, r"\.pl-runs \{ overflow-x: auto;")

    def test_the_conditions_stay_in_the_accessible_name_and_the_tooltip(self):
        css = read("css", "mission.css")
        # visually hidden, not display: none, so the accessible name keeps them
        self.assertRegex(self.compact_block(), r"\.pl-run-c \{ position: absolute; width: 1px;")
        player = read("js", "views", "player.js")
        self.assertIn("title: `${runFullName(r)} · ${shortId(r)}`", player)
        self.assertIn("conditionsBrief(r.record.request", player)
        self.assertRegex(css, r"\.pl-run-n \{ display: none; \}")


class EveryRowConsumerUsesTheNeutralClass(unittest.TestCase):
    """Structural only (the files build DOM and cannot be loaded by Node): each place that draws a requirement row takes its
    class from verdictOfRequirement or statusClassOf (model.js, tested in Node), so a safety rule that held is never green."""

    def test_the_four_consumers_use_the_shared_class(self):
        self.assertIn("verdictOfRequirement(r)", read("js", "verification.js"))
        self.assertIn("verdictOfRequirement(q)", read("js", "views", "compare.js"))
        self.assertIn("verdictOfRequirement(r)", read("js", "scenes", "ascent.js"))
        lab = read("js", "views", "lab.js")
        self.assertIn("statusClassOf(", lab)
        self.assertNotRegex(lab, r"`st-\$\{\w+\.status\}`")

    def test_the_lab_table_has_a_neutral_style_for_held(self):
        self.assertRegex(read("css", "lab.css"), r"\.lab-table td\.st-held \{ color: var\(--fg-1\); \}")


class FocusRingsOfThePillsAreNotClipped(unittest.TestCase):
    """Structural: a scrolling row clips its overflow, so it has block padding, and the hidden conditions are anchored to their pill."""

    def test_the_row_has_padding_and_the_pill_is_positioned(self):
        css = read("css", "mission.css")
        self.assertRegex(css, r"\.pl-runs \{ overflow-x: auto; overflow-y: hidden; scrollbar-width: thin; padding-block: 3px; margin-block: -3px; \}")
        self.assertRegex(css, r"\.pl-run \{ position: relative; \}")


class WalkthroughFollowUp(unittest.TestCase):
    """The expert walkthrough of 0.18.1 (F01 to F04, F06, F07, F10, F11): structural checks on the sources."""

    def test_f01_f02_the_scope_of_the_safety_chip_is_next_to_it_and_not_at_the_end_of_the_card(self):
        player = read("js", "views", "player.js")
        run_result = player[player.index("function runResult(run)"):player.index("function changeSummary()")]
        self.assertIn("SAFETY_SCOPE", run_result)
        self.assertRegex(run_result, r"sw\.verdict === 'held' && missionTone\(rec\) === 'fail'")
        fill = player[player.index("function fillResult()"):player.index("function fillAfter()")]
        self.assertNotIn("A requirement can fail without any safety rule being broken", fill)
        self.assertNotIn("pl-fine", fill)

    def test_f03_the_domain_expectation_texts_carry_the_gloss(self):
        for rel in (("js", "views", "compare.js"), ("js", "views", "run.js"), ("js", "views", "prepare.js")):
            self.assertIn("EXPECTATION_GLOSS", read(*rel), rel[-1])

    def test_f10_the_ground_readings_stay_on_a_short_window(self):
        css = read("css", "mission.css")
        short = css[css.index("@media (max-height: 720px)"):css.index("@media (max-width: 760px)")]
        self.assertNotIn("nth-child", short)
        self.assertIn(".pl-hud-row.is-minor { display: none; }", short)
        self.assertIn(".pl-hud.is-rocket .pl-hud-key { display: none; }", short)
        player = read("js", "views", "player.js")
        self.assertIn("rocket && (i === 3 || i === 4) ? 'is-minor' : ''", player)
        self.assertIn("rocket ? 'is-rocket' : 'is-ground'", player)

    def test_f04_f06_evidence_integrity_is_neutral_and_named(self):
        discover = read("js", "views", "discover.js")
        self.assertNotIn("vr.pass ? 'ok'", discover)
        self.assertIn("vr.pass ? 'Evidence integrity: recomputed'", discover)
        self.assertIn("verified ? 'held' : 'bad'", discover)
        css = read("css", "discover.css")
        for rule in re.findall(r"[^{}]*\.dl-(?:chip|tile)\.held[^{}]*\{[^}]*\}", css):
            self.assertNotIn("--pass", rule)
        self.assertRegex(css, r"\.dl-chip\.held")
        prov = read("js", "provenance.js")
        self.assertNotIn("ok ? 'v-pass'", prov)
        self.assertIn("'Evidence integrity: verified'", prov)
        self.assertNotRegex(read("css", "app.css"), r"\.replay-verdict\.v-held[^}]*--pass")

    def test_f07_the_caveat_is_at_the_level_of_the_figure_and_the_figure_is_named(self):
        lab = read("js", "views", "lab.js")
        i = lab.index("lab-gen-caveat")
        self.assertLess(i, lab.index("class: 'lab-gen'"))
        self.assertIn("`${kb}/${n} seeds`", lab)
        self.assertNotIn("It is not a reliability figure", lab)
        self.assertRegex(read("css", "lab.css"), r"\.lab-gen-caveat \{[^}]*font-size: 13\.5px")

    def test_f11_the_jump_button_names_the_instant(self):
        player = read("js", "views", "player.js")
        self.assertNotIn("'Go there'", player)
        self.assertIn("`Go to ${timeText(d.t, pl.unit)}`", player)


if __name__ == "__main__":
    unittest.main()
