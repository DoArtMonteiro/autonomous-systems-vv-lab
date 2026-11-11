# On-screen readout and controls, kept to the corners so the stage and its plume stay clear.
# Values are the record's own: t of the cursor, then the sample at or before it (as the Studio
# readout), altitude of the nozzle plane, speed and applied throttle; the outcome and safety
# verdicts are copied verbatim from the record (top right). A persistent label (bottom left) says
# what is reconstructed for display; one short credit line (bottom right) keeps the OpenStreetMap
# notice visible, and C opens every attribution of the pack. H hides the playback bar. The verdicts stay hidden until
# the playback reaches the end of the run (V shows them earlier).
extends RefCounted

const ILLUSTRATIVE := "Illustrative, not data: stage geometry (42 m), landing pad, lights and masts, plume and exhaust, glow and dust, crown shapes and foliage cards, building walls and roofs, sky, haze, water finish, ground beyond the pack."
const DATA := "Data: stage pose from the record (interpolated for display), throttle, verdicts; terrain, imagery, footprints, heights, plant positions from the validated pack. Nothing here is simulated."
const MARGIN := 18

var layer: CanvasLayer
var readout: Label
var verdict: Label
var verdict_text := ""
var revealed := false
var status: Label
var credit_line: Label
var credits_panel: PanelContainer
var slider: HSlider
var play_btn: Button
var cam_buttons := {}
var profile_menu: OptionButton
var speed_menu: OptionButton
var note: Label
var bar: PanelContainer
var rows: Array = []
var _block_slider := false


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


static func _anchor(c: Control, left: float, top: float, right: float, bottom: float) -> void:
	c.anchor_left = left
	c.anchor_top = top
	c.anchor_right = right
	c.anchor_bottom = bottom


func build(root: Node, record, pack, t0: float, t1: float, profiles: Array, cameras: Array) -> void:
	layer = CanvasLayer.new()
	root.add_child(layer)
	# Top left: what is shown and the readout.
	var top := PanelContainer.new()
	top.add_theme_stylebox_override("panel", _panel())
	top.position = Vector2(MARGIN, MARGIN)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 1)
	top.add_child(vb)
	var title := _label(11, Color(0.72, 0.77, 0.82))
	title.text = "Cinematic View: replay of a recorded run  |  %s" % str(pack.m.get("name", pack.m.get("id", "")))
	vb.add_child(title)
	readout = _label(14)
	vb.add_child(readout)
	layer.add_child(top)
	# Top right: the record's verdicts, verbatim.
	var vr := PanelContainer.new()
	vr.add_theme_stylebox_override("panel", _panel())
	_anchor(vr, 1, 0, 1, 0)
	vr.offset_left = -360 - MARGIN
	vr.offset_right = -MARGIN
	vr.offset_top = MARGIN
	verdict = _label(11)
	verdict.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	verdict.custom_minimum_size = Vector2(340, 0)
	var o: Dictionary = record.outcome()
	var s: Dictionary = record.safety()
	verdict_text = "From the record, shown as written and not re-verified here.\nOutcome: %s. %s\nSafety: %s. %s" % [str(o.get("label", o.get("code", "n/a"))), str(o.get("explanation", "")), str(s.get("status", "n/a")), str(s.get("explanation", ""))]
	vr.add_child(verdict)
	_show_verdict(false)
	layer.add_child(vr)
	# Bottom left: the persistent illustrative label.
	status = _label(10, Color(0.88, 0.9, 0.92))
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.text = ILLUSTRATIVE + "\n" + DATA + "\nRings (record): green R5 landing radius, red S2 keep-out. White line: nozzle track on the ground."
	var sp := PanelContainer.new()
	sp.add_theme_stylebox_override("panel", _panel(0.45))
	_anchor(sp, 0, 1, 0, 1)
	sp.offset_left = MARGIN
	sp.offset_right = MARGIN + 560
	sp.offset_top = -MARGIN - 86
	sp.offset_bottom = -MARGIN - 8
	status.custom_minimum_size = Vector2(540, 0)
	sp.add_child(status)
	layer.add_child(sp)
	# Bottom right: one short credit line; C opens the full attributions.
	credit_line = _label(10, Color(0.88, 0.9, 0.92))
	credit_line.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	var has_osm: bool = typeof(pack.m.get("world")) == TYPE_DICTIONARY and typeof(pack.m["world"].get("features")) == TYPE_DICTIONARY
	credit_line.text = ("© OpenStreetMap contributors (ODbL). " if has_osm else "") + "Terrain and imagery credits: press C."
	_anchor(credit_line, 1, 1, 1, 1)
	credit_line.offset_left = -420 - MARGIN
	credit_line.offset_right = -MARGIN
	credit_line.offset_top = -MARGIN - 16
	credit_line.offset_bottom = -MARGIN
	layer.add_child(credit_line)
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
	bar.offset_right = -MARGIN - 440
	bar.offset_top = -MARGIN - 88
	bar.offset_bottom = -MARGIN - 4
	var col := VBoxContainer.new()
	bar.add_child(col)
	var row := HBoxContainer.new()
	col.add_child(row)
	play_btn = Button.new()
	play_btn.text = "Play"
	row.add_child(play_btn)
	speed_menu = OptionButton.new()
	for sp2 in ["0.25x", "0.5x", "1x", "2x"]:
		speed_menu.add_item(sp2)
	speed_menu.select(2)
	row.add_child(speed_menu)
	slider = HSlider.new()
	slider.min_value = t0
	slider.max_value = t1
	slider.step = 0.0
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(slider)
	profile_menu = OptionButton.new()
	for p in profiles:
		profile_menu.add_item(p.capitalize())
	row.add_child(profile_menu)
	var row2 := HBoxContainer.new()
	col.add_child(row2)
	rows = [row, row2]
	var names := {"director": "Auto", "follow": "Follow", "pad": "Ground", "closeup": "Pad", "wide": "Wide", "overhead": "Top", "lowwide": "Low"}
	for c in cameras:
		var b := Button.new()
		b.text = names.get(c, c)
		b.toggle_mode = true
		b.add_theme_font_size_override("font_size", 12)
		row2.add_child(b)
		cam_buttons[c] = b
	note = _label(10, Color(1.0, 0.86, 0.55))
	note.clip_text = true
	note.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row2.add_child(note)
	layer.add_child(bar)


func set_controls_visible(on: bool) -> void:
	bar.visible = on


func toggle_credits() -> void:
	credits_panel.visible = not credits_panel.visible


# The record's verdicts are shown only when the playback reaches the end of the run (the rule of
# the technical view), or when the viewer asks for them with V.
func _show_verdict(on: bool) -> void:
	verdict.text = verdict_text if on else "Result: shown when the playback reaches the end of the run. Press V to show it now."


func reveal() -> void:
	revealed = true
	_show_verdict(true)


func set_time(t: float, record) -> void:
	if not revealed and t >= record.t1() - 1e-9:
		reveal()
	var i: int = record.lower_index(t)
	var st: float = record.times[i]
	var v := func(id: String, d: int) -> String:
		var x = record.sample_value(id, t)
		return "n/a" if x == null else String.num(float(x), d)
	readout.text = "t %.2f s  (sample %.2f s)\nalt %s m   speed %s m/s   throttle %s" % [t, st, v.call(record.nozzle_ids[2], 1), v.call("speed", 1), v.call("act_throttle", 3)]
	_block_slider = true
	slider.value = t
	_block_slider = false


func slider_blocked() -> bool:
	return _block_slider


func set_camera(mode: String) -> void:
	for c in cam_buttons:
		cam_buttons[c].button_pressed = c == mode
