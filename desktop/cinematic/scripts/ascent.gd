# Launch ascent view (vv-run.v2): several entities (the stack, then the booster and the upper stage
# after separation) drawn from the record. Nothing here simulates: every entity's position is the
# record's own, interpolated between its samples for display exactly as the Studio's ascent view does
# (the curved plane of altitude and downrange, desktop/studio/ui/js/scenes/ascent.js), an entity exists
# between its first and its last sample, and the camera is a rule of the recorded state.
#
# Frame. The record's plane is the pad's tangent plane: east along the downrange direction (the
# record has no heading: east is a choice of this view), up above the pad. The point the record gives
# is drawn as the BASE of the vehicle (altitude 0 is the pad). Positions are 64-bit floats; because the
# downrange reaches 1000 km and the pack is 18 km, everything drawn is offset by a floating origin
# (east and north of the camera target), so the engine's 32-bit vectors stay small.
#
# Illustrative, not data: vehicle shapes (from the record's visual block, which the simulation never
# reads), the body axis (drawn along the recorded velocity: no attitude is recorded), the plume, the
# Earth beyond the pack as a plain sphere with no geography, the atmosphere and the sky.
extends RefCounted

const Stage := preload("res://scripts/stage.gd")
const Effects := preload("res://scripts/effects.gd")

var main: Node3D
var record
var pack
var world_root: Node3D
var ents: Array = []       # runtime per entity: {rec, node, body, plume, k, length, diameter, abs, axis, thr, active, marker}
var shift_e := 0.0
var shift_n := 0.0
var fx: Dictionary = {}
var earth: MeshInstance3D
var trails: Array = []
var ground0 := 0.0
var cam_alt_m := 0.0
var auto_entity := ""
var g0_pad := 0.0


static func g(v: Vector3) -> Vector3:
	return Vector3(v.x, v.z, -v.y)


# --- vehicles ----------------------------------------------------------------------------------------

static func _lathe(profile: Array, segs: int) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for i in profile.size() - 1:
		for s in segs:
			var a0 := TAU * s / segs
			var a1 := TAU * (s + 1) / segs
			var p := [
				Vector3(profile[i].x * cos(a0), profile[i].y, profile[i].x * sin(a0)),
				Vector3(profile[i].x * cos(a1), profile[i].y, profile[i].x * sin(a1)),
				Vector3(profile[i + 1].x * cos(a1), profile[i + 1].y, profile[i + 1].x * sin(a1)),
				Vector3(profile[i + 1].x * cos(a0), profile[i + 1].y, profile[i + 1].x * sin(a0)),
			]
			for tri in [[0, 1, 2], [0, 2, 3]]:
				for k in tri:
					st.add_vertex(p[k])
	st.generate_normals()
	return st.commit()


static func _paint(c: Color, rough := 0.42, metal := 0.0) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = rough
	m.metallic = metal
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	return m


# Builds the vehicle of one entity under `body` (local +Y is the body axis, base at y = 0) from the
# record's visual block (stage lengths, diameters and colours). Returns {length, diameter}.
static func _shape(body: Node3D, kind: String, vis: Dictionary) -> Dictionary:
	var stages: Array = vis.get("stages", []) if typeof(vis.get("stages", [])) == TYPE_ARRAY else []
	var s1: Dictionary = stages[0] if stages.size() > 0 and typeof(stages[0]) == TYPE_DICTIONARY else {"length_m": 13.0, "diameter_m": 1.8, "colour": "#d9dde3"}
	var s2: Dictionary = stages[1] if stages.size() > 1 and typeof(stages[1]) == TYPE_DICTIONARY else {"length_m": 5.0, "diameter_m": 1.8, "colour": "#b9c2cc"}
	var fair := Color(str(vis.get("fairing_colour", "#eef1f4")))
	var parts: Array = []   # [length, radius, colour]
	var has_fairing := false
	match kind:
		"stack":
			parts = [s1, s2]
			has_fairing = true
		"upper_stage":
			parts = [s2]
			has_fairing = true
		_:
			parts = [s1]
	# The upper stage keeps the place it had in the stack: its body starts where the first stage ends
	# (the recorded point is the same for both children at separation; this is a drawing offset only).
	var y := float(s1.get("length_m", 13.0)) if kind == "upper_stage" else 0.0
	var base_y := y
	var first_r := 0.9
	for i in parts.size():
		var L: float = float(parts[i].get("length_m", 10.0))
		var r: float = float(parts[i].get("diameter_m", 1.8)) * 0.5
		if i == 0:
			first_r = r
			# Engine bells, dark, below the first part's base plane (y < 0 is behind the base).
			var bell := _lathe([Vector2(0.22 * r, 0.0), Vector2(0.5 * r, -0.9 * r)], 24)
			var bm := MeshInstance3D.new()
			bm.mesh = bell
			bm.material_override = _paint(Color(0.08, 0.08, 0.09), 0.5, 0.6)
			bm.position = Vector3(0, base_y + 0.9 * r, 0)
			body.add_child(bm)
		var mesh := _lathe([Vector2(r, 0.0), Vector2(r, L)], 48)
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.material_override = _paint(Color(str(parts[i].get("colour", "#d9dde3"))))
		mi.position = Vector3(0, y, 0)
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		body.add_child(mi)
		y += L
		if i < parts.size() - 1:
			# Interstage: a dark band.
			var band := _lathe([Vector2(r * 1.01, -0.6), Vector2(r * 1.01, 0.6)], 48)
			var bi := MeshInstance3D.new()
			bi.mesh = band
			bi.material_override = _paint(Color(0.07, 0.07, 0.08), 0.6)
			bi.position = Vector3(0, y, 0)
			body.add_child(bi)
	var r_top: float = float(parts[parts.size() - 1].get("diameter_m", 1.8)) * 0.5
	if has_fairing:
		var lf := 2.6 * r_top * 2.0
		var prof := []
		for k in 13:
			var f := float(k) / 12.0
			prof.append(Vector2(r_top * pow(1.0 - pow(f, 1.7), 0.55), f * lf))
		var fm := MeshInstance3D.new()
		fm.mesh = _lathe(prof, 48)
		fm.material_override = _paint(fair, 0.35)
		fm.position = Vector3(0, y, 0)
		fm.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		body.add_child(fm)
		y += lf
	return {"length": y, "diameter": first_r * 2.0, "base": base_y}


# --- build -------------------------------------------------------------------------------------------

# `world_root` holds what stays where it is (terrain, world layer, pad, the Earth sphere); it is moved
# by the floating origin. `terrain_avg` colours the Earth beyond the pack.
func build(main_node: Node3D, rec, pk, root: Node3D, sun_world: Vector3, avg_colour: Color, presentation: bool) -> void:
	main = main_node
	record = rec
	pack = pk
	world_root = root
	ground0 = pack.ground(0.0, 0.0)
	var vis: Dictionary = record.scene_data.get("visual", {}) if typeof(record.scene_data.get("visual", {})) == TYPE_DICTIONARY else {}
	for e in record.entities:
		var vehicle := Node3D.new()
		vehicle.name = "Entity_" + str(e["id"])
		main.add_child(vehicle)
		var body := Node3D.new()
		body.name = "Body"
		body.rotation = Vector3(0, 0, -PI / 2.0)   # local +Y (the build axis) onto the vehicle's +X
		vehicle.add_child(body)
		var dims := _shape(body, str(e["kind"]), vis)
		var d: float = dims["diameter"]
		var k: float = maxf(0.15, d / 3.7)   # the plume is built for the 3.7 m stage: scaled to this one
		var plume := Stage.build_plume(body)
		plume["plume"].scale = Vector3.ONE * k
		plume["plume"].position = Vector3(0, dims["base"], 0)
		plume["light"].position = Vector3(0, dims["base"] - 6.0 * k, 0)
		plume["light"].omni_range = 120.0 * k
		# Effects are not shadow casters; the vehicle is on the visual layer the decals do not paint.
		for n in vehicle.find_children("*", "GeometryInstance3D", true, false):
			n.layers = 2
		# A marker for the wide view: the vehicle is a point at that distance (illustrative).
		var mm := StandardMaterial3D.new()
		mm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		mm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		mm.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		mm.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
		mm.albedo_color = Color(e["color"]) * 2.0
		mm.disable_fog = true
		mm.no_depth_test = true
		mm.billboard_keep_scale = true   # the node scale sets the apparent size
		mm.albedo_texture = Stage._glow_texture()
		var mq := QuadMesh.new()
		mq.size = Vector2(1, 1)
		var marker := MeshInstance3D.new()
		marker.mesh = mq
		marker.material_override = mm
		marker.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		marker.visible = false
		main.add_child(marker)
		ents.append({"rec": e, "node": vehicle, "body": body, "plume": plume, "k": k, "length": dims["length"], "base": dims["base"], "diameter": d,
			"abs": [0.0, 0.0, 0.0], "axis": [0.0, 1.0], "dax": [0.0, 1.0], "thr": 0.0, "active": false, "marker": marker})
	fx = Effects.build(main, sun_world)
	# The Earth beyond the pack: a plain sphere (no geography); the limb glow is the sky shader's.
	var R: float = record.earth_radius_km * 1000.0
	var sm := SphereMesh.new()
	sm.radius = R
	sm.height = 2.0 * R
	sm.radial_segments = 512
	sm.rings = 256
	earth = MeshInstance3D.new()
	earth.name = "EarthIllustrative"
	earth.mesh = sm
	var em := StandardMaterial3D.new()
	em.albedo_color = avg_colour.lerp(Color(0.24, 0.34, 0.48), 0.75)   # a plain, illustrative sea tint (no geography)
	em.roughness = 0.5
	em.metallic_specular = 0.6
	earth.material_override = em
	earth.position = Vector3(0, -R - 6.0, 0)
	earth.extra_cull_margin = R
	earth.layers = 2
	world_root.add_child(earth)
	if not presentation:
		_trails()


# The recorded paths (data overlay): one polyline per entity in the curved plane.
func _trails() -> void:
	for e in record.entities:
		var im := ImmediateMesh.new()
		im.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
		var px: Array = e["px"]
		var py: Array = e["py"]
		for i in px.size():
			if px[i] == null or py[i] == null:
				continue
			im.surface_add_vertex(g(Vector3(float(px[i]) * 1000.0, 0.0, float(py[i]) * 1000.0 + ground0)))
		im.surface_end()
		var mat := StandardMaterial3D.new()
		mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		mat.albedo_color = e["color"]
		var mi := MeshInstance3D.new()
		mi.mesh = im
		mi.material_override = mat
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mi.extra_cull_margin = 1.0e7
		world_root.add_child(mi)
		trails.append(mi)


# --- the record at t ---------------------------------------------------------------------------------

# Positions (east, north, up in metres, 64-bit), axes and throttle of every entity at t.
func update_entities(t: float) -> void:
	for en in ents:
		var e: Dictionary = en["rec"]
		var act: bool = record.entity_active(e, t)
		var pl = record.entity_plane(e, t) if act else null
		en["active"] = act and pl != null
		if not en["active"]:
			continue
		en["abs"] = [float(pl[0]) * 1000.0, 0.0, float(pl[1]) * 1000.0 + ground0]
		en["axis"] = record.entity_axis(e, t)
		var thr = record.entity_value(e, "throttle", t)
		en["thr"] = clampf(float(thr), 0.0, 1.0) if thr != null else 0.0
		# Drawn axis. The body is drawn along the recorded velocity, nose forward, with the plume at the
		# tail. While an entity descends (recorded radial velocity below zero) with its engine burning,
		# that would put the nozzle on top, burning upwards; the body is then drawn tail first (axis
		# reversed, nose up, plume down), the pose of a braking burn. Illustrative: no attitude is
		# recorded or simulated.
		var vr = record.entity_value(e, "radial_velocity_m_s", t)
		var ax: Array = en["axis"]
		var rev: bool = en["thr"] > 0.005 and vr != null and float(vr) < 0.0
		en["dax"] = [-ax[0], -ax[1]] if rev else ax


func find(id: String) -> Dictionary:
	for en in ents:
		if en["rec"]["id"] == id:
			return en
	return {}


func entity_pos(en: Dictionary) -> Array:
	return en["abs"]


# Centre of the vehicle (half way along its body) in absolute coordinates.
func centre_of(en: Dictionary) -> Array:
	var a: Array = en["abs"]
	var ax: Array = en["dax"]
	var h: float = (en["base"] + en["length"]) * 0.5
	return [a[0] + ax[0] * h, 0.0, a[2] + ax[1] * h]


# Applies the floating origin: moves the static world, places every entity and its effects.
func apply_shift(se: float, sn: float, t: float) -> void:
	shift_e = se
	shift_n = sn
	world_root.position = g(Vector3(-se, -sn, 0.0))
	var sg := Vector3(se, sn, 0.0)
	var to_g := func(v: Vector3) -> Vector3:
		return g(v - sg)
	for en in ents:
		var node: Node3D = en["node"]
		node.visible = en["active"]
		en["marker"].visible = false
		if not en["active"]:
			continue
		var a: Array = en["abs"]
		var ax: Array = en["dax"]
		node.position = g(Vector3(a[0] - se, a[1] - sn, a[2]))
		node.basis = Basis(Vector3.BACK, atan2(ax[1], ax[0]))
		# Plume: the recorded throttle drives it; the length follows the technical view's rule, scaled to
		# this vehicle (illustrative presentation of a recorded value).
		var thr: float = en["thr"]
		var k: float = en["k"]
		var alt_m: float = maxf(0.0, a[2] - ground0)
		var plen: float = (6.0 + 22.0 * thr) if thr > 0.005 else 0.0
		Stage.set_plume(en["plume"], plen, t, alt_m / k + 1.0e-3 if alt_m < 200.0 else INF, thr)
		if en["plume"]["plume"].visible:
			en["plume"]["plume"].scale = Vector3.ONE * k
	# Ground effects of the first entity (the stack on the pad), driven by its recorded nozzle height.
	var lead: Dictionary = ents[0]
	var lp: Array = lead["abs"]
	var lthr: float = lead["thr"] if lead["active"] else 0.0
	var l_alt: float = maxf(0.0, lp[2] - ground0)
	var plen_lead: float = (6.0 + 22.0 * lthr) if lthr > 0.005 else 0.0
	Effects.update(fx, Vector3(lp[0] - se, lp[1] - sn, lp[2]), pack.ground(lp[0], lp[1]) if absf(lp[0]) < pack.extent() else 0.0, plen_lead if lead["active"] else 0.0, lthr, t, func(v: Vector3) -> Vector3: return g(v))


# --- cameras -----------------------------------------------------------------------------------------

func _active() -> Array:
	var out := []
	for en in ents:
		if en["active"]:
			out.append(en)
	return out


# The most relevant entity by recorded state: the stack until it ends, then the entity whose engine
# is burning, else the first active one.
func relevant() -> Dictionary:
	for en in ents:
		if en["active"] and en["rec"]["parent"] == null:
			return en
	var best: Dictionary = {}
	for en in ents:
		if en["active"] and en["thr"] > 0.01:
			return en
		if en["active"] and best.is_empty():
			best = en
	return best


# Automatic shot as a function of the record at t: "pad" at lift-off, "follow" the lead entity in
# flight, "staging" for the seconds after children appear, then "follow" of the burning entity, else
# "wide".
func auto_pick(t: float) -> String:
	var lead: Dictionary = relevant()
	if lead.is_empty():
		return "wide"
	auto_entity = lead["rec"]["id"]
	var root_active := false
	for en in ents:
		if en["rec"]["parent"] == null and en["active"]:
			root_active = true
	if root_active:
		return "pad" if (lead["abs"][2] - ground0) < 150.0 else "follow"
	var since := INF
	for en in ents:
		if en["active"]:
			since = minf(since, t - en["rec"]["t_start"])
	if since < 8.0:
		return "staging"
	return "follow" if lead["thr"] > 0.01 else "wide"


# Pose {pos, target, fov} in ENU relative to the floating origin, which this sets to the target.
func pose(m: String, selected: String, viewport_aspect: float, observer: Vector3) -> Dictionary:
	var focus: Dictionary = find(selected) if selected != "auto" else relevant()
	if focus.is_empty() or not focus["active"]:
		focus = relevant()
	if focus.is_empty():
		return {"pos": Vector3(0, -300, 20), "target": Vector3(0, 0, 10), "fov": 40.0}
	var c: Array = centre_of(focus)
	var tgt := [c[0], 0.0, c[2]]
	var eye := [0.0, 0.0, 0.0]
	var fov := 30.0
	match m:
		"pad":
			# The observer of the pad view is the one the landing view uses: 420 m out, clear of the canopy.
			var ex: float = observer.x
			var en_: float = observer.y
			var ez: float = observer.z
			var dd := sqrt((tgt[0] - ex) * (tgt[0] - ex) + en_ * en_ + (tgt[2] - ez) * (tgt[2] - ez))
			eye = [ex, en_, ez]
			fov = clampf(rad_to_deg(2.0 * atan(maxf(focus["length"], 20.0) * 1.3 / dd)), 4.0, 45.0)
		"staging":
			var act := _active()
			var sx := 0.0
			var sz := 0.0
			for en in act:
				var cc: Array = centre_of(en)
				sx += cc[0]
				sz += cc[2]
			sx /= maxf(1.0, act.size())
			sz /= maxf(1.0, act.size())
			var span := 0.0
			for en in act:
				var cc2: Array = centre_of(en)
				span = maxf(span, sqrt(pow(cc2[0] - sx, 2.0) + pow(cc2[2] - sz, 2.0)))
			var d := maxf(120.0, 5.0 * span + 80.0)
			tgt = [sx, 0.0, sz]
			eye = [sx, -d, sz + 0.12 * d]
		"wide":
			# The whole path so far: from the pad to the farthest active entity, seen from the side.
			var maxx := 0.0
			var maxz := 0.0
			var minx := 0.0
			for en in _active():
				maxx = maxf(maxx, en["abs"][0])
				maxz = maxf(maxz, en["abs"][2])
				minx = minf(minx, en["abs"][0])
			fov = 40.0
			var half := tan(deg_to_rad(fov) * 0.5)
			var xspan := (maxx - minx) + 2000.0
			var zspan := maxz + 2000.0
			var d2 := maxf(xspan / (2.0 * half * maxf(viewport_aspect, 0.5)), zspan / (2.0 * half)) * 1.2 + 1500.0
			tgt = [(maxx + minx) * 0.5, 0.0, maxz * 0.5]
			# Out of the flight plane the Earth falls away: lift the eye by the drop of the horizon at that
			# distance, plus a height of 0.45 of the distance, so the whole path is above the horizon.
			var rm: float = record.earth_radius_km * 1000.0
			eye = [tgt[0], -d2, tgt[2] + 0.45 * d2 + d2 * d2 / (2.0 * rm)]
		_:
			# follow
			var d3 := clampf(focus["length"] * 4.5, 60.0, 400.0)
			eye = [tgt[0], -d3, tgt[2] + 0.12 * d3]
	shift_e = tgt[0]
	shift_n = 0.0
	cam_alt_m = eye[2]
	return {"pos": Vector3(eye[0] - shift_e, eye[1] - shift_n, eye[2]), "target": Vector3(tgt[0] - shift_e, tgt[1] - shift_n, tgt[2]), "fov": fov, "shift_e": shift_e, "shift_n": shift_n}


# An exact eye, target and field of view (ENU metres, degrees) given on the command line.
func explicit(cp: PackedFloat64Array) -> Dictionary:
	shift_e = cp[3]
	shift_n = cp[4]
	return {"pos": Vector3(cp[0] - shift_e, cp[1] - shift_n, cp[2]), "target": Vector3(0.0, 0.0, cp[5]), "fov": cp[6], "shift_e": shift_e, "shift_n": shift_n}


# Wide-view markers: the vehicle is a point at that distance, so a small camera-facing glow of constant
# angular size marks it (illustrative).
func place_markers(wide: bool, cam_dist: Dictionary) -> void:
	for en in ents:
		var mk: MeshInstance3D = en["marker"]
		mk.visible = wide and en["active"]
		if mk.visible:
			var a: Array = en["abs"]
			mk.position = g(Vector3(a[0] - shift_e, a[1] - shift_n, a[2]))
			var d := mk.position.distance_to(cam_dist["eye_g"])
			mk.scale = Vector3.ONE * d * 0.025