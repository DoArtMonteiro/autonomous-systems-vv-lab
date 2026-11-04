# On-screen readout and controls. Values are the record's own: t of the cursor, then the sample at or
# before it (as the Studio readout), altitude of the nozzle plane, speed and applied throttle; the
# outcome and safety verdicts are copied verbatim from the record. A persistent label lists what is
# reconstructed for display and not data.
extends RefCounted

const ILLUSTRATIVE := "Illustrative, not data: stage geometry (42 m), plume, ground glow and dust, foliage cards and crown shapes, building walls and roofs, structure shapes, sky, haze, water finish, ground beyond the pack."
const DATA := "Data: stage position and attitude from the record (interpolated for display), throttle, outcome; terrain, imagery, footprints, heights and plant positions from the validated pack. Nothing here is simulated."

var layer: CanvasLayer
var readout: Label
var verdict: Label
var status: Label
var slider: HSlider
var play_btn: Button
var cam_buttons := {}
var profile_menu: OptionButton
var speed_menu: OptionButton
var note: Label
var bar: PanelContainer
var rows: Array = []
var _block_slider := false


static func _panel(alpha := 0.62) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.05, 0.06, 0.08, alpha)
	sb.corner_radius_top_left = 6
	sb.corner_radius_top_right = 6
	sb.corner_radius_bottom_left = 6
	sb.corner_radius_bottom_right = 6
	sb.content_margin_left = 12
	sb.content_margin_right = 12
	sb.content_margin_top = 8
	sb.content_margin_bottom = 8
	return sb


static func _label(size: int, colour := Color(0.92, 0.94, 0.96)) -> Label:
	var l := Label.new()
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", colour)
	l.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.6))
	l.add_theme_constant_override("shadow_offset_x", 1)
	l.add_theme_constant_override("shadow_offset_y", 1)
	return l


func build(root: Node, record, pack, t0: float, t1: float, profiles: Array, cameras: Array) -> void:
	layer = CanvasLayer.new()
	root.add_child(layer)
	# Top left: readout and verdict.
	var top := PanelContainer.new()
	top.add_theme_stylebox_override("panel", _panel())
	top.position = Vector2(16, 16)
	top.custom_minimum_size = Vector2(400, 0)
	var vb := VBoxContainer.new()
	top.add_child(vb)
	var title := _label(13, Color(0.7, 0.75, 0.8))
	title.text = "Cinematic View (replay of a recorded run, read-only)  |  %s" % str(pack.m.get("name", pack.m.get("id", "")))
	vb.add_child(title)
	readout = _label(15)
	vb.add_child(readout)
	verdict = _label(12)
	verdict.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	verdict.custom_minimum_size = Vector2(400, 0)
	var o: Dictionary = record.outcome()
	var s: Dictionary = record.safety()
	verdict.text = "Outcome (from the record): %s. %s\nSafety (from the record): %s. %s" % [str(o.get("label", o.get("code", "n/a"))), str(o.get("explanation", "")), str(s.get("status", "n/a")), str(s.get("explanation", ""))]
	vb.add_child(verdict)
	layer.add_child(top)
	# Bottom: playback, cameras, profile.
	bar = PanelContainer.new()
	bar.add_theme_stylebox_override("panel", _panel(0.7))
	bar.anchor_left = 0.0
	bar.anchor_right = 1.0
	bar.anchor_top = 1.0
	bar.anchor_bottom = 1.0
	bar.offset_left = 16
	bar.offset_right = -16
	bar.offset_top = -132
	bar.offset_bottom = -16
	var col := VBoxContainer.new()
	bar.add_child(col)
	var row := HBoxContainer.new()
	col.add_child(row)
	play_btn = Button.new()
	play_btn.text = "Play"
	play_btn.custom_minimum_size = Vector2(72, 0)
	row.add_child(play_btn)
	speed_menu = OptionButton.new()
	for sp in ["0.25x", "0.5x", "1x", "2x"]:
		speed_menu.add_item(sp)
	speed_menu.select(2)
	row.add_child(speed_menu)
	slider = HSlider.new()
	slider.min_value = t0
	slider.max_value = t1
	slider.step = 0.0
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(slider)
	var row2 := HBoxContainer.new()
	col.add_child(row2)
	rows = [row, row2]
	var cl := _label(13, Color(0.7, 0.75, 0.8))
	cl.text = "Camera"
	row2.add_child(cl)
	var names := {"director": "Auto", "follow": "Follow", "pad": "From the ground", "closeup": "At the pad", "wide": "Wide", "overhead": "Overhead"}
	for c in cameras:
		var b := Button.new()
		b.text = names.get(c, c)
		b.toggle_mode = true
		row2.add_child(b)
		cam_buttons[c] = b
	var sp2 := Control.new()
	sp2.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row2.add_child(sp2)
	var pl := _label(13, Color(0.7, 0.75, 0.8))
	pl.text = "Graphics"
	row2.add_child(pl)
	profile_menu = OptionButton.new()
	for p in profiles:
		profile_menu.add_item(p.capitalize())
	row2.add_child(profile_menu)
	note = _label(12, Color(1.0, 0.86, 0.55))
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	col.add_child(note)
	status = _label(11, Color(0.85, 0.88, 0.9))
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.text = ILLUSTRATIVE + "\n" + DATA + "\nCredits: " + "; ".join(pack.credits()) + ". Keys: space play, arrows step 1 s, 1 to 6 cameras, H hides the controls."
	col.add_child(status)
	bar.offset_top = -150
	layer.add_child(bar)


func set_time(t: float, record) -> void:
	var i: int = record.lower_index(t)
	var st: float = record.times[i]
	var v := func(id: String, d: int) -> String:
		var x = record.sample_value(id, t)
		return "n/a" if x == null else String.num(float(x), d)
	readout.text = "t %.2f s   sample %.2f s\naltitude %s m   speed %s m/s   throttle %s" % [t, st, v.call(record.nozzle_ids[2], 1), v.call("speed", 1), v.call("act_throttle", 3)]
	_block_slider = true
	slider.value = t
	_block_slider = false


func slider_blocked() -> bool:
	return _block_slider


func set_camera(mode: String) -> void:
	for c in cam_buttons:
		cam_buttons[c].button_pressed = c == mode
