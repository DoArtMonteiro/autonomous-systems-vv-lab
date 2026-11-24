# On-screen readout and controls, kept to the corners so the stage and its plume stay clear.
# Values are the record's own: t of the cursor, then the sample at or before it (as the Studio
# readout), altitude of the nozzle plane, speed and applied throttle; the outcome and safety
# verdicts are copied verbatim from the record (top right). A persistent label (bottom left) says
# what is reconstructed for display; one short credit line (bottom right) keeps the OpenStreetMap
# notice visible, and C opens every attribution of the pack. H hides the playback bar. The verdicts stay hidden until
# the playback reaches the end of the run (V shows them earlier).
extends RefCounted

const ILLUSTRATIVE := "Drawn for illustration, not data: the vehicle shapes (42 m), landing pad, lights and masts, ground textures and boulders near the pad, plant textures (their positions and sizes come from the environment pack), the sky image, plume and exhaust, glow and dust, tree crowns, scrub colour, building walls and roofs, haze, water and the ground beyond the pack. Backdrop only, not the run's: terrain, imagery, building footprints and heights and plant positions come from the environment pack."
const ILLUSTRATIVE_ASCENT := "Drawn for illustration, not data: the vehicle shapes (from the record's visual block), the body axis drawn along the recorded velocity (tail first while an engine burns in a steep descent; no attitude is recorded or simulated), the direction east (the record has no heading), the upper stage drawn offset from the first stage's recorded point, plume and exhaust, glow and dust, landing pad and lights, and the Earth beyond the pack as a plain sphere with no geography, atmosphere, sky or haze. Backdrop only, not the run's: the terrain and imagery of the pad's surroundings come from the environment pack."
const DATA_ASCENT := "Recorded data: each vehicle's position, altitude, inertial speed (as the record defines it) and throttle (percent of the maximum), interpolated between its samples for display; a vehicle exists from its first to its last sample. Nothing here is simulated."
const EXPLORATORY := "Exploratory: an idealised model, not a real vehicle, not validated against flight data."
const QUALIFIER := "idealised model, not a real vehicle"
const DATA := "Recorded data: the vehicle's position and orientation (interpolated for display), throttle (percent of the maximum), speed (the length of the recorded velocity vector) and the results. Nothing here is simulated."
const MARGIN := 18

var layer: CanvasLayer
var readout: Label
var verdict: Label
var verdict_text := ""
var revealed := false
var status: Label
var credit_line: Label
var credits_panel: PanelContainer
var credit_panel: PanelContainer
var slider: HSlider
var play_btn: Button
var cam_buttons := {}
var profile_menu: OptionButton
var speed_menu: OptionButton
var quality_label: Label
var result_btn: Button
var legend_btn: Button
var legend_panel: PanelContainer
var note: Label
var bar: PanelContainer
var rows: Array = []
var entity_buttons := {}
var is_v2 := false
var run_line: Label
var sample_line: Label
var speed_word := "speed"
var _block_slider := false


# The text of the result panel. Every run is an exploratory model, whatever the vehicle, and says so first; the
# safety line counts rules (the words of the Studio and of the evidence README), never the bare status, and the
# domain's own sentence is quoted under it. A landing record has a ground contact: the stage is drawn whole
# whatever the contact speed.
static func verdict_text_for(record) -> String:
	var o: Dictionary = record.outcome()
	var s: Dictionary = record.safety()
	var failed := _failed_requirements(record)
	var failed_line := ("\nRequirements failed: %s." % ", ".join(failed)) if failed.size() > 0 else ""
	var sc = record.data.get("scene", {})
	var contact_line := "\nImpact is not modelled: the stage is drawn intact whatever the contact speed." if (typeof(sc) == TYPE_DICTIONARY and sc.get("touchdown") != null) else ""
	return "From the record, shown as written and not re-verified here.\n%s\nOutcome: %s. %s%s%s%s\n%s\nThe record says: \"%s\"" % [EXPLORATORY, str(o.get("label", o.get("code", "n/a"))), str(o.get("explanation", "")), failed_line, contact_line, _impact_lines(record), safety_phrase(record), str(s.get("explanation", ""))]


# A launch record whose entity ends at the surface (the booster, ballistic after separation) says what the record does and
# does not hold about that end: the path up to the impact, not the impact.
static func _impact_lines(record) -> String:
	var out := ""
	if not record.is_v2:
		return out
	for e in record.entities:
		if str(e.get("end_reason", "")).contains("impact"):
			var who := str(e["label"]).get_slice(" (", 0)
			out += "\n%s impact: its recorded path ends at the surface (t %.1f s). The impact itself is not modelled and nothing is drawn for it: no landing burn, break-up or recovery is simulated, and the %s vehicle is not drawn after its last sample (its recorded path line stays)." % [who, e["t_end"], who.to_lower()]
	return out


# The labels of the mission requirements that failed, from the record's own rows (never the ids).
static func _failed_requirements(record) -> PackedStringArray:
	var out := PackedStringArray()
	for q in record.data.get("requirements", []):
		if typeof(q) == TYPE_DICTIONARY and str(q.get("category", "")) == "requirement" and str(q.get("status", "")) == "fail":
			out.append(str(q.get("label", q.get("id", ""))))
	return out


# "Safety rules: none broken (5 checked, S1 to S5), judged on the true state; this does not mean the
# vehicle is safe." / "Safety rules: 1 of 4 broken (name)." / "Safety rules: not evaluated." Only
# evaluated rules are counted, and a broken rule is looked at first. Mirrors safetyWording in
# desktop/studio/ui/js/requirements.js and safety_phrase in desktop/platform/src/evidence.rs.
static func safety_phrase(record) -> String:
	var rules: Array = []
	for q in record.data.get("requirements", []):
		if typeof(q) == TYPE_DICTIONARY and str(q.get("category", "")) == "invariant":
			rules.append(q)
	var judged: Array = []
	var broken: Array = []
	for q in rules:
		if str(q.get("status", "")) != "not_evaluated":
			judged.append(q)
		if str(q.get("status", "")) == "fail":
			broken.append(str(q.get("label", q.get("id", ""))))
	var s: Dictionary = record.safety()
	if str(s.get("status", "")) == "unsafe" or broken.size() > 0:
		if broken.size() > 0:
			return "Safety rules: %d of %d broken (%s)." % [broken.size(), judged.size(), ", ".join(PackedStringArray(broken))]
		return "Safety rules: a rule was broken."
	if (str(s.get("status", "")) == "safe" and str(s.get("class", "")) == "not_evaluated") or (rules.size() > 0 and judged.size() == 0):
		return "Safety rules: not evaluated."
	if rules.size() == 0:
		return "Safety rules: none broken."
	var range_text := ""
	var plain := true
	for q in rules:
		if str(q.get("id", "")).contains("."):
			plain = false
	if plain and judged.size() > 1:
		range_text = ", %s to %s" % [str(judged[0].get("id", "")).get_slice("_", 0), str(judged[judged.size() - 1].get("id", "")).get_slice("_", 0)]
	var counted := "%d checked" % judged.size() if judged.size() == rules.size() else "%d of %d checked; %d not evaluated" % [judged.size(), rules.size(), rules.size() - judged.size()]
	return "Safety rules: none broken (%s%s), judged on the true state; this does not mean the vehicle is safe." % [counted, range_text]


static func _panel(alpha := 0.55) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.04, 0.05, 0.07, alpha)
	for k in ["corner_radius_top_left", "corner_radius_top_right", "corner_radius_bottom_left", "corner_radius_bottom_right"]:
		sb.set(k, 6)
	sb.content_margin_left = 10
	sb.content_margin_right = 10
	sb.content_margin_top = 6
	sb.content_margin_bottom = 6
	return sb


static func _label(size: int, colour := Color(0.93, 0.95, 0.97)) -> Label:
	var l := Label.new()
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", colour)
	l.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.7))
	l.add_theme_constant_override("shadow_offset_x", 1)
	l.add_theme_constant_override("shadow_offset_y", 1)
	return l


static func _small(text: String) -> Label:
	var l := _label(12, Color(0.82, 0.86, 0.9))
	l.text = text
	l.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	return l


# The quality control's label says whether the profile was chosen by the automatic policy; the reason
# is its tooltip. One control, one place: the profile menu next to it names the profile.
func set_quality_note(auto: bool, tip: String) -> void:
	quality_label.text = "Quality (auto)" if auto else "Quality"
	quality_label.tooltip_text = tip
	quality_label.mouse_filter = Control.MOUSE_FILTER_STOP
	profile_menu.tooltip_text = tip


static func _anchor(c: Control, left: float, top: float, right: float, bottom: float) -> void:
	c.anchor_left = left
	c.anchor_top = top
	c.anchor_right = right
	c.anchor_bottom = bottom


# " (10 m)" from the record's own requirement row ("<= 10 m"), or nothing when the row is absent.
static func _limit_text(record, id: String) -> String:
	for q in record.data.get("requirements", []):
		if typeof(q) == TYPE_DICTIONARY and str(q.get("id", "")) == id:
			var parts: PackedStringArray = str(q.get("expected", "")).split(" ", false)
			if parts.size() >= 3 and parts[1].is_valid_float():
				return " (%s %s)" % [parts[1], parts[2]]
	return ""


func build(root: Node, record, pack, t0: float, t1: float, profiles: Array, cameras: Array) -> void:
	is_v2 = record.is_v2
	layer = CanvasLayer.new()
	root.add_child(layer)
	# Top left: what is shown and the readout.
	var top := PanelContainer.new()
	top.add_theme_stylebox_override("panel", _panel())
	top.position = Vector2(MARGIN, MARGIN)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 1)
	top.add_child(vb)
	var title := _label(12, Color(0.82, 0.86, 0.9))
	title.text = title_text(str(pack.m.get("name", pack.m.get("id", ""))))
	vb.add_child(title)
	# Which run this is: the Studio's label for it, its identifier, the vehicle and the seed.
	run_line = _label(13, Color(0.97, 0.98, 1.0))
	run_line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	run_line.custom_minimum_size = Vector2(420, 0)
	vb.add_child(run_line)
	readout = _label(14)
	vb.add_child(readout)
	# The recorded sample the readout reads (a technical detail, kept on a quieter line).
	sample_line = _label(12, Color(0.78, 0.82, 0.87))
	vb.add_child(sample_line)
	layer.add_child(top)
	# Top right: the record's verdicts, verbatim.
	var vr := PanelContainer.new()
	vr.add_theme_stylebox_override("panel", _panel())
	_anchor(vr, 1, 0, 1, 0)
	vr.offset_left = -360 - MARGIN
	vr.offset_right = -MARGIN
	vr.offset_top = MARGIN
	verdict = _label(12)
	verdict.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	verdict.custom_minimum_size = Vector2(340, 0)
	verdict_text = verdict_text_for(record)
	vr.add_child(verdict)
	_show_verdict(false)
	layer.add_child(vr)
	# Bottom left: the persistent illustrative label.
	status = _label(12, Color(0.95, 0.96, 0.98))
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	if is_v2:
		status.text = ILLUSTRATIVE_ASCENT + "\n" + DATA_ASCENT + "\nColoured lines (record): the recorded path of each entity."
	else:
		status.text = ILLUSTRATIVE + "\n" + DATA + "\nRings: green is the landing radius%s, red is the keep-out radius%s, both from the run record's limits. White line: the engine nozzle's path over the ground." % [_limit_text(record, "R5_position"), _limit_text(record, "S2_keep_out")]
	var sp := PanelContainer.new()
	sp.add_theme_stylebox_override("panel", _panel(0.92))
	_anchor(sp, 0, 1, 0, 1)
	sp.offset_left = MARGIN
	sp.offset_right = MARGIN + 560
	# Grows upwards from the bottom margin: the label is as tall as its text needs, whatever its length.
	sp.grow_vertical = Control.GROW_DIRECTION_BEGIN
	sp.offset_top = -MARGIN - 20
	sp.offset_bottom = -MARGIN - 8
	status.custom_minimum_size = Vector2(540, 0)
	sp.add_child(status)
	layer.add_child(sp)
	legend_panel = sp
	# Bottom right: one short credit line; C opens the full attributions.
	credit_line = _label(12, Color(0.95, 0.96, 0.98))
	credit_line.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	var has_osm: bool = typeof(pack.m.get("world")) == TYPE_DICTIONARY and typeof(pack.m["world"].get("features")) == TYPE_DICTIONARY
	credit_line.text = ("© OpenStreetMap contributors (ODbL). " if has_osm else "") + "Terrain and imagery credits: press C."
	var cp := PanelContainer.new()
	cp.add_theme_stylebox_override("panel", _panel(0.85))
	_anchor(cp, 1, 1, 1, 1)
	cp.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	cp.grow_vertical = Control.GROW_DIRECTION_BEGIN
	cp.offset_right = -MARGIN
	cp.offset_bottom = -MARGIN
	cp.offset_left = -MARGIN
	cp.offset_top = -MARGIN
	credit_line.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	credit_line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	credit_line.custom_minimum_size = Vector2(300, 0)
	credit_panel = cp
	cp.add_child(credit_line)
	layer.add_child(cp)
	credits_panel = PanelContainer.new()
	credits_panel.add_theme_stylebox_override("panel", _panel(0.85))
	_anchor(credits_panel, 0.5, 0.5, 0.5, 0.5)
	credits_panel.offset_left = -360
	credits_panel.offset_right = 360
	credits_panel.offset_top = -160
	credits_panel.offset_bottom = 160
	var cl := _label(12)
	cl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	cl.text = "Credits of the environment pack (press C to close):\n\n" + "\n".join(pack.attributions())
	credits_panel.add_child(cl)
	credits_panel.visible = false
	layer.add_child(credits_panel)
	# Playback bar: bottom centre, between the label and the credit line, one slim row.
	bar = PanelContainer.new()
	bar.add_theme_stylebox_override("panel", _panel(0.6))
	_anchor(bar, 0, 1, 1, 1)
	bar.offset_left = MARGIN + 580
	bar.offset_right = -MARGIN - 340
	bar.grow_vertical = Control.GROW_DIRECTION_BEGIN
	bar.offset_top = -MARGIN - 20
	bar.offset_bottom = -MARGIN
	var col := VBoxContainer.new()
	bar.add_child(col)
	var row := HFlowContainer.new()
	col.add_child(row)
	play_btn = Button.new()
	play_btn.text = "Play"
	row.add_child(play_btn)
	row.add_child(_small("Speed"))
	speed_menu = OptionButton.new()
	for sp2 in ["0.25x", "0.5x", "1x", "2x"]:
		speed_menu.add_item(sp2)
	speed_menu.select(2)
	row.add_child(speed_menu)
	row.add_child(_small("Time"))
	slider = HSlider.new()
	slider.min_value = t0
	slider.max_value = t1
	slider.step = 0.0
	slider.custom_minimum_size = Vector2(110, 0)
	slider.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(slider)
	quality_label = _small("Quality")
	row.add_child(quality_label)
	profile_menu = OptionButton.new()
	for p in profiles:
		profile_menu.add_item(p.capitalize())
	row.add_child(profile_menu)
	result_btn = Button.new()
	result_btn.text = "Show result"
	result_btn.tooltip_text = "Show the record's verdicts now (V)"
	row.add_child(result_btn)
	# The legend of what is drawn can be folded away; it starts open, as the label must be on screen.
	legend_btn = Button.new()
	legend_btn.text = "Hide what is drawn"
	legend_btn.toggle_mode = false
	legend_btn.pressed.connect(func():
		legend_panel.visible = not legend_panel.visible
		legend_btn.text = "Hide what is drawn" if legend_panel.visible else "Show what is drawn")
	row.add_child(legend_btn)
	var row2 := HFlowContainer.new()
	col.add_child(row2)
	rows = [row, row2]
	row2.add_child(_small("Camera"))
	# The same names the Studio's player uses for the same cameras.
	var names := {"director": "Auto", "follow": "Follow", "pad": "From the ground", "closeup": "At the pad", "wide": "Whole descent", "overhead": "Overhead", "lowwide": "Low angle"}
	if is_v2:
		names["pad"] = "Pad view"
		names["wide"] = "Trajectory"
	for c in cameras:
		var b := Button.new()
		b.text = names.get(c, c)
		b.toggle_mode = true
		b.add_theme_font_size_override("font_size", 12)
		row2.add_child(b)
		cam_buttons[c] = b
	if is_v2:
		# Entity of the follow camera: Auto follows the most relevant one by the recorded state.
		var ent_row := HFlowContainer.new()
		col.add_child(ent_row)
		rows.append(ent_row)
		ent_row.add_child(_small("Follow"))
		var ea := Button.new()
		ea.text = "Entity: Auto"
		ea.toggle_mode = true
		ea.add_theme_font_size_override("font_size", 12)
		ent_row.add_child(ea)
		entity_buttons["auto"] = ea
		for en in record.entities:
			var eb := Button.new()
			eb.text = str(en["label"]).get_slice(" (", 0)
			eb.toggle_mode = true
			eb.add_theme_font_size_override("font_size", 12)
			ent_row.add_child(eb)
			entity_buttons[en["id"]] = eb
	# The graphics note became the label of the one quality control (see set_quality_note).
	note = _label(12, Color(1.0, 0.9, 0.62))
	note.visible = false
	row2.add_child(note)
	layer.add_child(bar)


# Presentation: hides the engineering panels (readout, verdicts, legend, playback bar) and keeps
# the attribution line and one small permanent line saying that the picture is an illustration and
# what the record says the outcome was, so a clip never shows a run without its result.
static func presentation_line(record) -> String:
	var line := "Illustrative replay of a recorded run"
	if record != null:
		var o: Dictionary = record.outcome()
		line += ". Recorded outcome: %s (from the record, not re-verified here)" % str(o.get("label", o.get("code", "n/a")))
	return line


# The first line of the header: the place is the backdrop of the replay, not where the run happened.
static func title_text(place: String) -> String:
	return "Cinematic View: this view computes nothing. It draws the recorded run  |  %s (backdrop only)" % place


# Which run is on screen. Values are the Studio's display arguments or, when the module is started on
# its own, what the record itself says (the seed of its request, the identifier of its folder).
func set_run_info(label: String, vehicle: String, exploratory: bool, seed: int, run_id: String, record, conditions := "") -> void:
	run_line.text = run_line_text(label, vehicle, seed, run_id, record, conditions)
	speed_word = "inertial speed" if is_v2 else "speed"


# The run line. Every run carries the exploratory qualifier, whatever the vehicle or the Studio's flag:
# "Threshold 3 m (7efed40d)  |  seed 5017  |  22 t landing stage (idealised model, not a real vehicle)  |  exploratory
# |  conditions: GNSS bias 9.72 m".
static func run_line_text(label: String, vehicle: String, seed: int, run_id: String, record, conditions := "") -> String:
	var parts := PackedStringArray()
	var name := label
	if name == "":
		name = "Run %s" % run_id.substr(0, 8)
	elif run_id != "":
		name = "%s (%s)" % [name, run_id.substr(0, 8)]
	parts.append(name)
	var sd := seed
	if sd < 0 and record != null:
		# Read from the record's JSON, where a number is a float: only a seed that is exactly an integer
		# below 2^53 is shown, never a rounded one.
		var rq = record.data.get("request", {})
		if typeof(rq) == TYPE_DICTIONARY and (typeof(rq.get("seed")) == TYPE_FLOAT or typeof(rq.get("seed")) == TYPE_INT):
			var f := float(rq["seed"])
			if f >= 0.0 and f < 9.0e15 and f == floorf(f):
				sd = int(f)
	if sd >= 0:
		parts.append("seed %d" % sd)
	parts.append("%s (%s)" % [vehicle, QUALIFIER] if vehicle != "" else QUALIFIER)
	parts.append("exploratory")
	if conditions != "":
		parts.append("conditions: %s" % conditions)
	return "  |  ".join(parts)


func set_presentation(on: bool, record = null) -> void:
	if not on:
		return
	for c in layer.get_children():
		if c != credit_panel:
			c.visible = false
	var l := _label(12, Color(0.95, 0.96, 0.98))
	l.text = presentation_line(record)
	# One line from the left margin to the credit line (420 px wide at the right); a label that does
	# not fit in a narrow window is cut with an ellipsis instead of running under the credit line.
	l.clip_text = true
	l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_anchor(l, 0, 1, 1, 1)
	l.offset_left = MARGIN
	l.offset_right = -420 - 2 * MARGIN
	l.offset_top = -MARGIN - 16
	l.offset_bottom = -MARGIN
	layer.add_child(l)


func set_controls_visible(on: bool) -> void:
	bar.visible = on


func toggle_credits() -> void:
	credits_panel.visible = not credits_panel.visible


# The record's verdicts are shown only when the playback reaches the end of the run (the rule of
# the technical view), or when the viewer asks for them with V.
func _show_verdict(on: bool) -> void:
	verdict.text = verdict_text if on else "Result: shown when the playback reaches the end of the run. Press V or use Show result to see it now."


func reveal() -> void:
	revealed = true
	_show_verdict(true)


func set_time(t: float, record) -> void:
	if not revealed and t >= record.t1() - 1e-9:
		reveal()
	if record.is_v2:
		_set_time_ascent(t, record)
		return
	var r := readout_for(record, t, speed_word)
	readout.text = r["readout"]
	sample_line.text = r["sample"]
	_block_slider = true
	slider.value = t
	_block_slider = false


# The landing readout at t: {readout, sample}. Before the end it is the recorded sample at or before t, as always. At the end
# of a record that states a ground contact the speed is not the last sample's speed dressed as a contact measurement:
# when the record carries the verifier's speeds at the contact instant (touchdown_vertical_speed and
# touchdown_horizontal_speed) those are shown and named as such, otherwise the line says the record has no contact speed
# and that the number is the last sample's. An altitude within 5 cm of the ground reads 0.0, never -0.0.
static func readout_for(record, t: float, speed_word := "speed") -> Dictionary:
	var i: int = record.lower_index(t)
	var st: float = record.times[i]
	var v := func(id: String, d: int) -> String:
		var x = record.sample_value(id, t)
		return "n/a" if x == null else String.num(0.0 if absf(float(x)) < 0.05 and d == 1 else float(x), d)
	var th = record.sample_value("act_throttle", t)
	var th_text := "n/a" if th == null else "%d %%" % int(round(float(th) * 100.0))
	var alt: String = v.call(record.nozzle_ids[2], 1)
	if record.has_contact() and t >= record.t1() - 1e-9:
		var vs = record.metric("touchdown_vertical_speed")
		var hs = record.metric("touchdown_horizontal_speed")
		var speeds: String
		var sample: String
		if vs != null and hs != null:
			speeds = "at contact, the verifier's values: descent %s m/s, horizontal %s m/s" % [String.num(float(vs), 1), String.num(float(hs), 1)]
			sample = "altitude and throttle: the recorded sample at t %.2f s; speeds: the verifier's, at the contact" % st
		else:
			speeds = "the record has no contact speed; %s of the last sample: %s m/s" % [speed_word, v.call("speed", 1)]
			sample = "reads the recorded sample at t %.2f s (the last one, not a contact measurement)" % st
		return {"readout": "t %.2f s of %.2f s\nground contact, end of the record: altitude %s m   throttle %s\n%s" % [t, record.t1(), alt, th_text, speeds], "sample": sample}
	return {"readout": "t %.2f s of %.2f s\naltitude %s m   %s %s m/s   throttle %s" % [t, record.t1(), alt, speed_word, v.call("speed", 1), th_text], "sample": "reads the recorded sample at t %.2f s" % st}


# Launch ascent readout: the mission clock and, for each entity, its own record at t: altitude,
# speed and throttle (before its first sample it has not started; after its last it has ended).
func _set_time_ascent(t: float, record) -> void:
	var lines := PackedStringArray()
	lines.append("t %.2f s of %.2f s (mission clock)" % [t, record.t1()])
	for e in record.entities:
		var short := str(e["label"]).get_slice(" (", 0)
		if t < e["t_start"] - 1e-9:
			lines.append("%s: starts at t %.1f s" % [short, e["t_start"]])
		elif t > e["t_end"] + 1e-9:
			lines.append("%s: ended at t %.1f s (%s)" % [short, e["t_end"], e["end_reason"]])
		else:
			var v := func(name: String, d: int, scale: float) -> String:
				var x = record.entity_value(e, name, t)
				return "n/a" if x == null else String.num(float(x) * scale, d)
			var thr = record.entity_value(e, "throttle", t)
			var thr_text := "n/a" if thr == null else "%d %%" % int(round(float(thr) * 100.0))
			lines.append("%s: altitude %s km   %s %s m/s   throttle %s" % [short, v.call("altitude_km", 2, 1.0), speed_word, v.call("speed_m_s", 1, 1.0), thr_text])
	readout.text = "\n".join(lines)
	sample_line.text = "reads each entity's recorded samples at the mission clock"
	_block_slider = true
	slider.value = t
	_block_slider = false
	if not revealed and t >= record.t1() - 1e-9:
		reveal()


func set_entity(id: String) -> void:
	for k in entity_buttons:
		entity_buttons[k].button_pressed = k == id


func slider_blocked() -> bool:
	return _block_slider


func set_camera(mode: String) -> void:
	for c in cam_buttons:
		cam_buttons[c].button_pressed = c == mode
