extends Node3D
# Spike: show a recorded vv-lab ground-vehicle trace in 3D. It renders only recorded
# per-tick positions (x_mm, y_mm -> X, Z metres); height and orientation are not simulated.
# Usage: godot --path spikes/godot-trace-viewer -- <path to spikes/out/trace.json>

var states: Array = []
var tick_index := -1
var vehicle: MeshInstance3D
var info: Label
var started_ms := 0

func _ready() -> void:
	started_ms = Time.get_ticks_msec()
	var args := OS.get_cmdline_user_args()
	var path: String = args[0] if args.size() > 0 else "../out/trace.json"
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		push_error("cannot read trace: %s" % path)
		get_tree().quit(2)
		return
	var trace: Dictionary = JSON.parse_string(file.get_as_text())
	states = trace["states"]
	_build_world(trace["geometry"])
	var layer := CanvasLayer.new()
	add_child(layer)
	info = Label.new()
	info.position = Vector2(16, 12)
	info.add_theme_font_size_override("font_size", 20)
	layer.add_child(info)
	var note := Label.new()
	note.position = Vector2(16, 680)
	note.add_theme_font_size_override("font_size", 16)
	note.text = "2D kinematic model shown in 3D: positions are recorded integer mm on a plane; height, orientation and dynamics are NOT simulated. Run %s, replay %s." % [trace["run_id"], trace["replay"]]
	layer.add_child(note)
	print("SPIKE ready_ms=%d ticks=%d" % [Time.get_ticks_msec() - started_ms, states.size()])

func _box(size: Vector3, pos: Vector3, color: Color) -> MeshInstance3D:
	var m := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size
	m.mesh = mesh
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	m.material_override = mat
	m.position = pos
	add_child(m)
	return m

func _p(x_mm: float, y_mm: float, h: float = 0.0) -> Vector3:
	return Vector3(x_mm / 1000.0, h, -y_mm / 1000.0)

func _build_world(g: Dictionary) -> void:
	var b: Dictionary = g["bounds"]
	var w: float = (b["max_x_mm"] - b["min_x_mm"]) / 1000.0
	var d: float = (b["max_y_mm"] - b["min_y_mm"]) / 1000.0
	_box(Vector3(w, 0.02, d), _p((b["min_x_mm"] + b["max_x_mm"]) / 2.0, (b["min_y_mm"] + b["max_y_mm"]) / 2.0, -0.01), Color(0.22, 0.24, 0.26))
	var zone: Array = g["restricted_zone"]
	if zone.size() >= 3:
		var xs: Array = zone.map(func(p): return p["x_mm"])
		var ys: Array = zone.map(func(p): return p["y_mm"])
		var zx: float = (xs.max() - xs.min()) / 1000.0
		var zy: float = (ys.max() - ys.min()) / 1000.0
		_box(Vector3(zx, 0.3, zy), _p((xs.max() + xs.min()) / 2.0, (ys.max() + ys.min()) / 2.0, 0.15), Color(0.8, 0.2, 0.2))
	for wp in g["waypoints"]:
		_box(Vector3(0.2, 0.6, 0.2), _p(wp["x_mm"], wp["y_mm"], 0.3), Color(0.2, 0.8, 0.4))
	vehicle = _box(Vector3(0.4, 0.25, 0.3), _p(g["start"]["x_mm"], g["start"]["y_mm"], 0.125), Color(0.25, 0.55, 0.95))
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-55, 30, 0)
	add_child(light)
	var cam := Camera3D.new()
	add_child(cam)
	cam.look_at_from_position(Vector3(3.5, 6.0, 2.5), Vector3(3.5, 0, -2.5), Vector3.UP)

func _process(_delta: float) -> void:
	# One recorded tick per rendered frame (run with --fixed-fps); no interpolation between ticks.
	tick_index += 1
	if tick_index >= states.size():
		print("SPIKE done_ms=%d" % (Time.get_ticks_msec() - started_ms))
		get_tree().quit(0)
		return
	var s: Dictionary = states[tick_index]
	if s["x_mm"] != s["from_x_mm"] or s["y_mm"] != s["from_y_mm"]:
		var a := _p(s["from_x_mm"], s["from_y_mm"], 0.03)
		var e := _p(s["x_mm"], s["y_mm"], 0.03)
		var seg := _box(Vector3(max(abs(e.x - a.x), 0.05), 0.04, max(abs(e.z - a.z), 0.05)), (a + e) / 2.0,
			Color(0.95, 0.5, 0.2) if s["safety_state"] == "fallback" else Color(0.3, 0.6, 1.0))
		seg.name = "seg_%d" % s["tick"]
	vehicle.position = _p(s["x_mm"], s["y_mm"], 0.125)
	# Fidelity check: report the rendered position mapped back to millimetres.
	print("SPIKE tick=%d rendered_mm=%d,%d" % [s["tick"], roundi(vehicle.position.x * 1000.0), roundi(-vehicle.position.z * 1000.0)])
	info.text = "tick %d  safety %s  position (%d, %d) mm" % [s["tick"], s["safety_state"], s["x_mm"], s["y_mm"]]
