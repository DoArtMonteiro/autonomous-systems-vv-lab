# VV Lab Cinematic View: entry point. Reads a run directory and an environment pack directory,
# validates them, builds the scene and replays the record. It never simulates: the stage pose at
# logical time t comes only from record.pose_at(t). Cameras are rules of the playback state (as the
# technical view's presets in geo.js); only the easing between two camera rules uses the wall clock.
#
# Exit codes: 0 done, 2 bad arguments, 3 invalid run record, 4 invalid or tampered pack.
extends Node3D

const Cli := preload("res://scripts/cli.gd")
const RunRecord := preload("res://scripts/record.gd")
const Frame := preload("res://scripts/frame.gd")
const Pack := preload("res://scripts/pack.gd")
const Terrain := preload("res://scripts/terrain.gd")
const World := preload("res://scripts/world.gd")
const Stage := preload("res://scripts/stage.gd")
const Effects := preload("res://scripts/effects.gd")
const Pad := preload("res://scripts/pad.gd")
const Profiles := preload("res://scripts/profiles.gd")
const Hud := preload("res://scripts/hud.gd")

# Illustrative sun (as the technical view: no date or time of day is part of the model).
const SUN_AZIMUTH_DEG := 128.0
const SUN_ELEVATION_DEG := 27.0
const STAGE_LENGTH := 42.0
const CAMERAS := ["director", "follow", "pad", "closeup", "wide", "overhead", "lowwide"]

var cli
var record
var pack
var vehicle: Node3D
var stage: Dictionary
var camera: Camera3D
var sun: DirectionalLight3D
var env: Environment
var hud
var terrain: Dictionary
var world: Dictionary
var settings: Dictionary
var profile_name := ""
var profile_reason := ""
var vram: Dictionary = {}
var t := 0.0
var playing := false
var speed := 1.0
var mode := "director"
var director_shot := ""
var transition := {}
var observer = null
var top_z := 3000.0
var fx: Dictionary = {}
var drop: MeshInstance3D
var ready_ok := false
var frames := 0
var started_usec := 0
var bench := {}
var shot_wait := -1
var last_watch := 0
var notes: PackedStringArray = PackedStringArray()


func _ready() -> void:
	started_usec = Time.get_ticks_usec()
	cli = Cli.parse(OS.get_cmdline_user_args())
	if cli.error != "":
		_fail(2, cli.error + "\n" + Cli.usage())
		return
	record = RunRecord.load_dir(cli.run_dir)
	if record.error != "":
		_fail(3, "run: " + record.error)
		return
	vehicle = Node3D.new()
	vehicle.name = "Vehicle"
	add_child(vehicle)
	if cli.has_pose_dump:
		_pose_dump()
		return
	pack = Pack.load_dir(cli.env_dir)
	if pack.error != "":
		_fail(4, "environment pack refused: " + pack.error)
		return
	print("cinematic: pack %s verified (%d files, SHA-256 against environment.json)" % [str(pack.m.get("id", "")), pack.verified.size()])
	_build()


func _fail(code: int, message: String) -> void:
	printerr("cinematic: " + message)
	get_tree().quit(code)


# --- pose ---------------------------------------------------------------------------------------

# Places the vehicle node at the recorded pose of logical time t; returns the pose (64-bit).
func apply_pose(at: float) -> Dictionary:
	var p: Dictionary = record.pose_at(at)
	if p["position"] != null:
		vehicle.position = Frame.to_godot(p["position"][0], p["position"][1], p["position"][2])
	vehicle.basis = Basis(Frame.quat_to_godot(p["quaternion"]).normalized())
	return p


# Headless check of what is drawn: for each t, the pose from the record (64-bit, model frame) and
# the transform of the drawn stage node read back from the scene and converted to the model frame.
func _pose_dump() -> void:
	for at in cli.pose_dump:
		var p := apply_pose(at)
		var gt := vehicle.global_transform
		var axis := gt.basis.x.normalized()
		var out := {
			"t": at,
			"index": p["index"],
			"position_enu": p["position"],
			"quaternion_wxyz": p["quaternion"],
			"axis_enu": Frame.rotate_enu(p["quaternion"], [1.0, 0.0, 0.0]),
			"drawn_position_enu": Frame.to_enu(gt.origin),
			"drawn_axis_enu": Frame.to_enu(axis),
			"plume_m": record.plume_length(at),
		}
		print("POSE " + JSON.stringify(out, "", true, true))
	get_tree().quit(0)


# --- scene --------------------------------------------------------------------------------------

func _sun_dir_enu() -> Vector3:
	var az := deg_to_rad(SUN_AZIMUTH_DEG)
	var el := deg_to_rad(SUN_ELEVATION_DEG)
	return Vector3(sin(az) * cos(el), cos(az) * cos(el), sin(el))


static func g(v: Vector3) -> Vector3:
	# ENU vector (x east, y north, z up) to the drawn frame.
	return Vector3(v.x, v.z, -v.y)


func _build() -> void:
	var t_build := Time.get_ticks_usec()
	# Environment: an illustrative sky shader (gradient, sun halo and disc, static clouds); the fog
	# takes its colour from that sky (aerial perspective 1), so the land fades into the sky it is
	# drawn against; screen-space effects; AgX tone mapping at a fixed exposure (no auto exposure).
	var we := WorldEnvironment.new()
	env = Environment.new()
	var sky := Sky.new()
	var psky := ShaderMaterial.new()
	psky.shader = load("res://shaders/sky.gdshader")
	sky.sky_material = psky
	sky.process_mode = Sky.PROCESS_MODE_QUALITY
	sky.radiance_size = Sky.RADIANCE_SIZE_256
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	# A less blue fill: shadows keep form without turning blue (the sky colour is only part of it).
	env.ambient_light_sky_contribution = 0.55
	env.ambient_light_color = Color(0.62, 0.58, 0.52)
	env.ambient_light_energy = 0.9
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_exposure = 0.92
	env.tonemap_white = 6.0
	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_EXPONENTIAL
	env.fog_light_color = Color(0.72, 0.8, 0.89)
	env.fog_sun_scatter = 0.15
	env.fog_density = 0.000045
	env.fog_aerial_perspective = 1.0
	env.fog_sky_affect = 0.0
	env.fog_height = 400.0
	env.fog_height_density = 0.00006
	env.volumetric_fog_density = 0.00012
	env.volumetric_fog_albedo = Color(0.9, 0.92, 0.95)
	env.volumetric_fog_length = 1200.0
	env.volumetric_fog_anisotropy = 0.6
	env.volumetric_fog_sky_affect = 0.0
	env.ssao_radius = 2.0
	env.ssao_intensity = 1.6
	env.ssil_radius = 6.0
	env.ssr_max_steps = 64
	env.glow_intensity = 0.35
	env.glow_bloom = 0.05
	env.glow_hdr_threshold = 3.0
	env.adjustment_enabled = true
	env.adjustment_saturation = 1.08
	env.adjustment_contrast = 1.07
	we.environment = env
	add_child(we)
	sun = DirectionalLight3D.new()
	sun.name = "SunIllustrative"
	sun.light_color = Color(1.0, 0.95, 0.88)
	sun.light_energy = 1.7
	sun.shadow_enabled = true
	sun.shadow_bias = 0.03
	sun.shadow_normal_bias = 1.2
	sun.directional_shadow_max_distance = 1500.0
	sun.directional_shadow_blend_splits = true
	add_child(sun)
	var d := g(_sun_dir_enu())
	sun.look_at_from_position(Vector3.ZERO, -d, Vector3.UP if absf(d.normalized().y) < 0.99 else Vector3.FORWARD)
	camera = Camera3D.new()
	camera.near = 0.5
	camera.far = 250000.0
	camera.fov = 30.0
	camera.attributes = CameraAttributesPractical.new()
	add_child(camera)
	camera.make_current()
	# Profile.
	vram = Profiles.detect_vram(cli.vram_bytes)
	if cli.profile == "auto":
		var pick := Profiles.auto_pick(vram)
		profile_name = pick["profile"]
		profile_reason = "Auto: " + pick["reason"]
	else:
		profile_name = cli.profile
		profile_reason = "Chosen on the command line"
	settings = Profiles.settings(profile_name, cli.custom)
	Profiles.apply(settings, get_viewport(), env, sun)
	# Terrain, world layer and stage.
	terrain = Terrain.build(pack, self)
	var pad_c: Dictionary = record.pad()
	for m in terrain.get("materials", []):
		m.set_shader_parameter("pad_xy", Vector2(pad_c["cx"], pad_c["cy"]))
	world = World.build(pack, self, settings)
	stage = Stage.build(vehicle)
	for n in vehicle.find_children("*", "MeshInstance3D", true, false):
		n.layers = 2   # not on the decals' layer (pad slab, contact shadow): they paint the ground only
		if not n.get_parent().name.begins_with("Plume"):
			n.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	var pp: Dictionary = record.pad()
	Pad.build(self, pack, pp["cx"], pp["cy"])
	_pad_rings()
	fx = Effects.build(self, g(_sun_dir_enu()).normalized())
	# Top of the trajectory box (centre of mass), as the technical view's wide preset uses.
	var mz := 0.0
	for v in record.channels.get(record.position_ids[2], []):
		if v != null:
			mz = maxf(mz, float(v))
	top_z = mz if mz > 0.0 else 3000.0
	# Interface.
	hud = Hud.new()
	hud.build(self, record, pack, record.t0(), record.t1(), Profiles.ORDER + ["custom"], CAMERAS)
	hud.play_btn.pressed.connect(func(): _set_playing(not playing))
	hud.slider.value_changed.connect(func(v): if not hud.slider_blocked(): _set_time(v))
	hud.speed_menu.item_selected.connect(func(i): speed = [0.25, 0.5, 1.0, 2.0][i])
	for c in hud.cam_buttons:
		hud.cam_buttons[c].pressed.connect(func(): set_mode(c))
	var all_profiles: Array = Profiles.ORDER + ["custom"]
	hud.profile_menu.select(all_profiles.find(profile_name))
	hud.profile_menu.item_selected.connect(func(i): _switch_profile(all_profiles[i], "Chosen in the menu"))
	notes.append(profile_reason)
	_update_note()
	mode = "explicit" if cli.has_camera_pose else cli.camera
	t = cli.start_t if not is_nan(cli.start_t) else record.t0()
	playing = cli.play
	hud.set_camera(mode)
	hud.set_controls_visible(cli.controls)
	hud.set_presentation(cli.presentation)
	_track_lines()
	_set_time(t)
	print("cinematic: scene built in %d ms (profile %s: %s)" % [(Time.get_ticks_usec() - t_build) / 1000, profile_name, profile_reason])
	if cli.shot_path != "":
		shot_wait = 90
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	if cli.bench_path != "":
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
		bench = {"t0": cli.bench_t0 if not is_nan(cli.bench_t0) else record.t0(), "t1": cli.bench_t1 if not is_nan(cli.bench_t1) else record.t1(), "start": -1, "deltas": PackedFloat64Array(), "last": 0, "warm": 120}
	RenderingServer.frame_post_draw.connect(_first_frame, CONNECT_ONE_SHOT)
	ready_ok = true


func _first_frame() -> void:
	print("FIRST_FRAME %d" % ((Time.get_ticks_usec() - started_usec) / 1000))


func _update_note() -> void:
	hud.note.text = "Graphics: %s (%s). %s" % [profile_name.capitalize(), profile_reason, " ".join(notes.slice(1))]


func _switch_profile(name: String, reason: String) -> void:
	var old: Dictionary = settings
	profile_name = name
	profile_reason = reason
	settings = Profiles.settings(name, cli.custom)
	Profiles.apply(settings, get_viewport(), env, sun)
	var veg_keys := ["vegetation_density", "lod_near_m", "lod_far_m", "foliage_cards", "vegetation_shadows"]
	var rebuild := false
	for k in veg_keys:
		if old.get(k) != settings.get(k):
			rebuild = true
	if rebuild and world.has("group"):
		world["group"].queue_free()
		world = World.build(pack, self, settings)
	_update_note()


# Rings of the record's pad (R5 landing radius, S2 keep-out), draped on the terrain: data overlays.
func _pad_rings() -> void:
	if cli.presentation:
		return
	var p: Dictionary = record.pad()
	for spec in [[p["land"], Color(0.35, 0.85, 0.55), 0.35], [p["keep"], Color(0.95, 0.45, 0.35), 0.4]]:
		var r: float = spec[0]
		if r <= 0.0:
			continue
		var im := ImmediateMesh.new()
		im.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
		for k in 193:
			var a := TAU * k / 192.0
			var x: float = p["cx"] + r * cos(a)
			var y: float = p["cy"] + r * sin(a)
			im.surface_add_vertex(Vector3(x, pack.ground(x, y) + spec[2], -y))
		im.surface_end()
		var mat := StandardMaterial3D.new()
		mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		mat.albedo_color = spec[1]
		var mi := MeshInstance3D.new()
		mi.mesh = im
		mi.material_override = mat
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(mi)


# Data overlays for reading height: the nozzle-plane track draped on the terrain (record) and a
# drop line from the stage to the ground under it.
func _track_lines() -> void:
	if cli.presentation:
		return
	var im := ImmediateMesh.new()
	im.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
	var ids: Array = record.nozzle_ids
	for i in record.times.size():
		var x = record.channels[ids[0]][i]
		var y = record.channels[ids[1]][i]
		if x == null or y == null:
			continue
		im.surface_add_vertex(Vector3(x, pack.ground(x, y) + 0.6, -y))
	im.surface_end()
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = Color(1, 1, 1, 0.8)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	var mi := MeshInstance3D.new()
	mi.mesh = im
	mi.material_override = mat
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	drop = MeshInstance3D.new()
	drop.material_override = mat
	drop.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(drop)


func _update_drop(vp: Vector3) -> void:
	if drop == null:
		return
	var im := ImmediateMesh.new()
	im.surface_begin(Mesh.PRIMITIVE_LINES)
	im.surface_add_vertex(g(vp))
	im.surface_add_vertex(g(Vector3(vp.x, vp.y, pack.ground(vp.x, vp.y))))
	im.surface_end()
	drop.mesh = im


# --- playback -----------------------------------------------------------------------------------

func _set_playing(on: bool) -> void:
	playing = on
	hud.play_btn.text = "Pause" if on else "Play"


func _set_time(at: float) -> void:
	t = clampf(at, record.t0(), record.t1())
	apply_pose(t)
	var len: float = record.plume_length(t)
	# The axial plume stops at the ground; below that it is drawn as the ground spread.
	var vp := _enu(vehicle.position)
	var clear_m: float = maxf(0.0, vp.z - pack.ground(vp.x, vp.y))
	var thr = record.sample_value("act_throttle", t)
	var thr_f := clampf(float(thr), 0.0, 1.0) if thr != null else 0.6
	Stage.set_plume(stage, len, t, clear_m, thr_f)
	# Exposure as a function of the recorded state: a lit plume pulls it down a little (no automatic
	# exposure: that evolves with the wall clock and a frame at a given t would not repeat).
	env.tonemap_exposure = 0.95 - 0.14 * thr_f * (1.0 if len > 0.0 else 0.0)
	for m in terrain.get("materials", []):
		m.set_shader_parameter("logical_t", t)
	Effects.update(fx, vp, pack.ground(vp.x, vp.y), len, thr_f, t, g)
	_update_drop(vp)
	hud.set_time(t, record)
	_place_camera()


static func _enu(v: Vector3) -> Vector3:
	return Vector3(v.x, -v.z, v.y)


# --- cameras (rules of the playback state, as geo.js) -------------------------------------------

static func bearing(az: float, el: float) -> Vector3:
	return Vector3(sin(deg_to_rad(az)) * cos(deg_to_rad(el)), cos(deg_to_rad(az)) * cos(deg_to_rad(el)), sin(deg_to_rad(el)))


func _aim() -> Vector3:
	var axis := _enu(vehicle.global_transform.basis.x.normalized())
	return _enu(vehicle.position) + axis * STAGE_LENGTH * 0.45


func _pad_v() -> Vector3:
	var p: Dictionary = record.pad()
	return Vector3(p["cx"], p["cy"], 0.0)


func director_pick() -> String:
	var pv := _pad_v()
	var h: float = _enu(vehicle.position).z - pack.ground(pv.x, pv.y)
	if h > 1400.0:
		return "wide"
	if h > 260.0:
		return "follow"
	if h > 55.0:
		return "pad"
	return "closeup"


func _canopy_at(x: float, y: float, r: float) -> float:
	var v: Dictionary = pack.vegetation
	if v.is_empty():
		return 0.0
	var h := 0.0
	for i in v["n"]:
		if absf(v["x"][i] - x) < r and absf(v["y"][i] - y) < r and v["h"][i] > h:
			h = v["h"][i]
	return h


func _observer() -> Vector3:
	if observer != null:
		return observer
	var pv := _pad_v()
	var padp := Vector3(pv.x, pv.y, pack.ground(pv.x, pv.y) + 6.0)
	for b in [160, 200, 120, 240, 80, 280, 40, 320, 0]:
		var at := Vector3(pv.x, pv.y, 0) + bearing(b, 0) * 420.0
		at.z = pack.ground(at.x, at.y) + maxf(12.0, _canopy_at(at.x, at.y, 40.0) + 8.0)
		var clear := true
		for k in range(1, 40):
			var q := at.lerp(padp, k / 40.0)
			if pack.ground(q.x, q.y) > q.z + 0.5:
				clear = false
				break
		if clear:
			observer = at
			return at
	var at2 := Vector3(pv.x, pv.y, 0) + bearing(160, 0) * 420.0
	at2.z = pack.ground(at2.x, at2.y) + 40.0
	observer = at2
	return at2


# Pose {pos, target, fov} (ENU) of camera rule `m` at the current playback state.
func pose(m: String) -> Dictionary:
	if m == "explicit":
		# An exact eye, target and field of view given on the command line (ENU metres, degrees).
		var cp: PackedFloat64Array = cli.camera_pose
		var eye := Vector3(cp[0], cp[1], cp[2])
		var tgt := Vector3(cp[3], cp[4], cp[5])
		return {"pos": eye, "target": tgt, "fov": cp[6], "dof": eye.distance_to(tgt)}
	if m == "director":
		return pose(director_shot if director_shot != "" else director_pick())
	var aim := _aim()
	var pv := _pad_v()
	match m:
		"follow":
			return {"pos": aim + bearing(152, 7) * 190.0, "target": aim, "fov": lens_fov(45.0), "sx": 0.34, "sy": 0.10, "shake": 0.05}
		"pad":
			var at := _observer()
			var dd := at.distance_to(aim)
			return {"pos": at, "target": aim, "fov": clampf(rad_to_deg(2.0 * atan(STAGE_LENGTH * 1.2 / dd)), 3.0, 40.0), "sx": 0.28, "sy": 0.0, "shake": 0.06}
		"closeup":
			# Low hero angle (cinematic only): 165 m out, 22 m above the ground, a 50 mm lens
			# looking up at the stage, which stands on the left third of the frame.
			var at := pv + bearing(38, 0) * 165.0
			at.z = pack.ground(at.x, at.y) + 22.0
			var g0: float = pack.ground(pv.x, pv.y)
			var tg := aim
			tg.z = clampf(tg.z, g0 + 17.0, g0 + 24.0)
			tg.x = pv.x + (tg.x - pv.x) * 0.5
			tg.y = pv.y + (tg.y - pv.y) * 0.5
			return {"pos": at, "target": tg, "fov": lens_fov(50.0), "sx": -0.30, "sy": -0.06, "shake": 0.10, "dof": at.distance_to(tg)}
		"wide":
			var dw := top_z * 1.35
			return {"pos": Vector3(pv.x + 0.5 * dw, pv.y - 0.95 * dw, top_z * 0.62), "target": Vector3(pv.x, pv.y, top_z * 0.42), "fov": 40.0}
	if m == "lowwide":
		# Low wide view from the sun side (cinematic only): an observer 12 m above the ground at
		# least 900 m out, the stage and the landscape behind it in one frame.
		var dl: float = maxf(900.0, aim.z * 1.4)
		var at := pv + bearing(150, 0) * dl
		at.z = pack.ground(at.x, at.y) + 12.0
		var tg := Vector3(aim.x, aim.y, aim.z * 0.6 + pack.ground(pv.x, pv.y) * 0.4)
		return {"pos": at, "target": tg, "fov": 38.0}
	var span := 3200.0
	return {"pos": Vector3(pv.x, pv.y - span * 0.02, span / (2.0 * tan(deg_to_rad(20.0)))), "target": pv, "fov": 40.0}


# Vertical field of view of a lens of focal length `mm` on a 24 mm tall sensor.
static func lens_fov(mm: float) -> float:
	return rad_to_deg(2.0 * atan(12.0 / mm))


# Camera shake as a function of the record time only (a handheld look: slow drift plus a faint
# tremor), in degrees about the camera's right and up axes.
static func shake_deg(at: float, amp: float) -> Vector2:
	var x := sin(TAU * 0.37 * at + 1.1) * 0.55 + sin(TAU * 1.31 * at + 0.3) * 0.3 + sin(TAU * 3.7 * at + 2.0) * 0.15
	var y := sin(TAU * 0.29 * at + 4.0) * 0.55 + sin(TAU * 1.07 * at + 5.1) * 0.3 + sin(TAU * 4.3 * at + 0.7) * 0.15
	return Vector2(x, y) * amp


func set_mode(m: String) -> void:
	if not (m in CAMERAS):
		return
	transition = {"from": _current_cam(), "t0": Time.get_ticks_msec(), "dur": 700.0}
	mode = m
	director_shot = ""
	hud.set_camera(mode)
	_place_camera()


func _current_cam() -> Dictionary:
	var fwd := -camera.global_transform.basis.z
	return {"pos": _enu(camera.position), "target": _enu(camera.position + fwd * 100.0), "fov": camera.fov}


func _place_camera() -> void:
	if mode == "director":
		var shot := director_pick()
		if director_shot != "" and shot != director_shot and transition.is_empty() and cli.shot_path == "":
			transition = {"from": _current_cam(), "t0": Time.get_ticks_msec(), "dur": 1100.0}
		director_shot = shot
	var want := pose(mode)
	var pos: Vector3 = want["pos"]
	var target: Vector3 = want["target"]
	var fov: float = want["fov"]
	if not transition.is_empty() and cli.shot_path == "" and cli.bench_path == "":
		var k := clampf((Time.get_ticks_msec() - transition["t0"]) / transition["dur"], 0.0, 1.0)
		var e := 4.0 * k * k * k if k < 0.5 else 1.0 - pow(-2.0 * k + 2.0, 3.0) / 2.0
		var f: Dictionary = transition["from"]
		pos = f["pos"].lerp(pos, e)
		target = f["target"].lerp(target, e)
		fov = f["fov"] + (fov - f["fov"]) * e
		if k >= 1.0:
			transition = {}
	else:
		transition = {}
	var gz: float = pack.ground(pos.x, pos.y)
	if pos.z < gz + 2.5:
		pos.z = gz + 2.5
	camera.fov = fov
	var gp := g(pos)
	var gt := g(target)
	if gp.distance_to(gt) > 1e-3:
		camera.look_at_from_position(gp, gt, Vector3.UP)
		# Composition: the subject sits at screen (sx, sy) (in half-frame units, +x right, +y up)
		# instead of the centre, by panning the aim point the other way; then the shake.
		var vs := get_viewport().get_visible_rect().size
		var dist := gp.distance_to(gt)
		var half_h := dist * tan(deg_to_rad(fov) * 0.5)
		var sx: float = want.get("sx", 0.0)
		var sy: float = want.get("sy", 0.0)
		if sx != 0.0 or sy != 0.0:
			var b := camera.global_transform.basis
			gt = gt - b.x * sx * half_h * (vs.x / vs.y) - b.y * sy * half_h
			camera.look_at_from_position(gp, gt, Vector3.UP)
		var amp: float = want.get("shake", 0.0)
		if amp > 0.0 and transition.is_empty():
			var sh := shake_deg(t, amp)
			camera.rotate_object_local(Vector3.UP, deg_to_rad(sh.x))
			camera.rotate_object_local(Vector3.RIGHT, deg_to_rad(sh.y))
		_set_dof(want.get("dof", 0.0))
	# Shadows cover what the shot shows: the stage and its shadow, or the whole descent.
	var wide := mode == "wide" or mode == "overhead" or (mode == "director" and director_shot == "wide")
	sun.directional_shadow_max_distance = 6000.0 if wide else 1500.0


# Depth of field on close shots only: the subject at `focus` metres stays sharp, the far landscape and
# the near ground soften. Off (0) elsewhere and in the Performance profile.
func _set_dof(focus: float) -> void:
	var ca: CameraAttributesPractical = camera.attributes
	if ca == null:
		return
	var on := focus > 0.0 and bool(settings.get("dof", false))
	ca.dof_blur_far_enabled = on
	ca.dof_blur_near_enabled = on
	if on:
		ca.dof_blur_far_distance = focus * 1.25
		ca.dof_blur_far_transition = focus * 1.6
		ca.dof_blur_near_distance = focus * 0.5
		ca.dof_blur_near_transition = focus * 0.35
		ca.dof_blur_amount = 0.06


# --- frame loop ---------------------------------------------------------------------------------

func _unhandled_input(ev: InputEvent) -> void:
	if not ready_ok or not (ev is InputEventKey) or not ev.pressed:
		return
	match ev.keycode:
		KEY_SPACE:
			_set_playing(not playing)
		KEY_LEFT:
			_set_time(t - 1.0)
		KEY_RIGHT:
			_set_time(t + 1.0)
		KEY_HOME:
			_set_time(record.t0())
		KEY_END:
			_set_time(record.t1())
		KEY_1, KEY_2, KEY_3, KEY_4, KEY_5, KEY_6, KEY_7:
			set_mode(CAMERAS[ev.keycode - KEY_1])
		KEY_H:
			# Hides the playback bar; the readout, verdicts, illustrative label and credit line stay.
			hud.set_controls_visible(not hud.bar.visible)
		KEY_V:
			hud.reveal()
		KEY_C:
			hud.toggle_credits()
		KEY_ESCAPE:
			get_tree().quit(0)


func _process(delta: float) -> void:
	if not ready_ok:
		return
	frames += 1
	if shot_wait >= 0:
		shot_wait -= 1
		if shot_wait == 0:
			_save_shot()
		return
	if not bench.is_empty():
		_bench_step()
		return
	if playing:
		var nt := t + delta * speed
		if nt >= record.t1():
			nt = record.t1()
			_set_playing(false)
		_set_time(nt)
	elif not transition.is_empty():
		_place_camera()
	_watch_vram()


# Steps the profile down when the video memory in use passes 85 % of the capacity.
func _watch_vram() -> void:
	var now := Time.get_ticks_msec()
	if now - last_watch < 1000 or vram.get("bytes", -1) <= 0:
		return
	last_watch = now
	var used := RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED)
	if used > 0.85 * vram["bytes"] and profile_name != "performance":
		var lower := Profiles.step_down(profile_name if profile_name != "custom" else "balanced")
		notes.append("Video memory at %d MB of %d MB: stepped down to %s." % [used / 1048576, vram["bytes"] / 1048576, lower.capitalize()])
		_switch_profile(lower, "stepped down for video memory")
		hud.profile_menu.select((Profiles.ORDER + ["custom"]).find(lower))


func _save_shot() -> void:
	var img := get_viewport().get_texture().get_image()
	var err := img.save_png(cli.shot_path) if cli.shot_path.ends_with(".png") else img.save_jpg(cli.shot_path, 0.9)
	var meta := _stats()
	meta["file"] = cli.shot_path.get_file()
	meta["camera"] = mode
	meta["shot"] = director_shot
	var fwd := -camera.global_transform.basis.z
	meta["camera_eye_enu"] = [_enu(camera.position).x, _enu(camera.position).y, _enu(camera.position).z]
	meta["camera_dir_enu"] = [_enu(fwd).x, _enu(fwd).y, _enu(fwd).z]
	meta["camera_fov"] = camera.fov
	print("SHOT " + JSON.stringify(meta))
	get_tree().quit(0 if err == OK else 1)


func _stats() -> Dictionary:
	return {
		"t": t,
		"profile": profile_name,
		"profile_reason": profile_reason,
		"settings": settings,
		"adapter": RenderingServer.get_video_adapter_name(),
		"driver": RenderingServer.get_current_rendering_driver_name(),
		"vram_capacity_bytes": vram.get("bytes", -1),
		"vram_capacity_source": vram.get("source", ""),
		"video_mem_used_bytes": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED),
		"texture_mem_used_bytes": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED),
		"buffer_mem_used_bytes": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_BUFFER_MEM_USED),
		"primitives_in_frame": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME),
		"draw_calls_in_frame": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
		"static_memory_bytes": OS.get_static_memory_usage(),
		"window": [get_viewport().get_visible_rect().size.x, get_viewport().get_visible_rect().size.y],
		"world": world.get("stats", {}),
	}


# Benchmark: plays the record from t0 to t1 over bench_seconds of wall time with the Auto camera,
# vsync off, after a warm-up; records the wall time between frames (measured outside the replay).
func _bench_step() -> void:
	var now := Time.get_ticks_usec()
	if bench["warm"] > 0:
		bench["warm"] -= 1
		_set_time(bench["t0"])
		bench["last"] = now
		return
	if bench["start"] < 0:
		bench["start"] = now
	else:
		bench["deltas"].append((now - bench["last"]) / 1000.0)
	bench["last"] = now
	var f: float = float(now - bench["start"]) / (cli.bench_seconds * 1.0e6)
	_set_time(bench["t0"] + (bench["t1"] - bench["t0"]) * minf(f, 1.0))
	if f >= 1.0:
		var ds: PackedFloat64Array = bench["deltas"]
		var sorted := Array(ds)
		sorted.sort()
		var q := func(p: float) -> float:
			return sorted[clampi(int(ceil(p * sorted.size())) - 1, 0, sorted.size() - 1)]
		var out := _stats()
		out["frames"] = sorted.size()
		out["frame_ms_p50"] = q.call(0.5)
		out["frame_ms_p95"] = q.call(0.95)
		out["frame_ms_p99"] = q.call(0.99)
		out["frame_ms_max"] = sorted[sorted.size() - 1]
		out["bench_seconds"] = cli.bench_seconds
		out["replay_from_t"] = bench["t0"]
		out["replay_to_t"] = bench["t1"]
		out["vsync"] = "disabled"
		var f2 := FileAccess.open(cli.bench_path, FileAccess.WRITE)
		f2.store_string(JSON.stringify(out, " "))
		f2.close()
		print("BENCH " + JSON.stringify({"p50": out["frame_ms_p50"], "p99": out["frame_ms_p99"], "frames": out["frames"], "video_mem_used_bytes": out["video_mem_used_bytes"]}))
		get_tree().quit(0)
