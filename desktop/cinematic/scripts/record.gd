# Run record (vv-run.v1) of a powered landing, read for display only. The renderer never simulates:
# every pose comes from the record's recorded states, interpolated between samples exactly as the
# Studio's technical view does (desktop/studio/ui/js/dom.js sampleAt and lowerIndex,
# desktop/studio/ui/js/scenes/rocket.js setTime). All arithmetic here is in 64-bit GDScript floats;
# only the drawn transform is cast to the engine's 32-bit vectors.
extends RefCounted

const MAX_RECORD_BYTES := 64 * 1024 * 1024

var data: Dictionary = {}
var times: PackedFloat64Array = PackedFloat64Array()
var channels: Dictionary = {}  # id -> Array (float or null), on the scene timebase
var error: String = ""

# Channel ids resolved through record.scene.channels, as channelsOf() does.
var nozzle_ids: Array = ["base_x", "base_y", "altitude"]
var position_ids: Array = ["pos_x", "pos_y", "pos_z"]
var attitude_ids: Array = ["q_w", "q_x", "q_y", "q_z"]
var engine_id: String = "engine_state"

# vv-run.v2 (launch ascent): several entities, each with its own timebase. `times` is then the
# mission timebase (the clock of the replay), `channels` stays empty, and every entity carries its
# own samples: {id, label, kind, parent, times, t_start, t_end, end_reason, ch: {name: Array},
# px, py: Array (km, the curved plane, as the Studio's ascent view draws it), color}.
var is_v2 := false
var entities: Array = []
var earth_radius_km := 6371.0
var scene_data: Dictionary = {}
const MAX_ENTITIES := 8


static func load_dir(dir: String) -> RefCounted:
	var r = load("res://scripts/record.gd").new()
	var path := dir.path_join("record.json")
	if not FileAccess.file_exists(path):
		r.error = "no record.json in the run directory"
		return r
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		r.error = "record.json cannot be opened"
		return r
	if f.get_length() > MAX_RECORD_BYTES:
		r.error = "record.json is larger than the limit"
		return r
	var parsed = JSON.parse_string(f.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		r.error = "record.json is not a JSON object"
		return r
	r._init_from(parsed)
	return r


func _init_from(d: Dictionary) -> void:
	data = d
	var schema := str(d.get("schema", ""))
	if schema == "vv-run.v2":
		is_v2 = true
		_init_v2(d)
		return
	if schema != "vv-run.v1":
		error = "record schema is neither vv-run.v1 nor vv-run.v2"
		return
	if d.has("entities") or d.has("mission"):
		error = "a vv-run.v1 record cannot have entities or a mission"
		return
	var scene = d.get("scene", {})
	if typeof(scene) != TYPE_DICTIONARY or str(scene.get("kind", "")) != "rocket-3d":
		error = "the record is not a rocket landing (scene kind rocket-3d)"
		return
	var sc = scene.get("channels", {})
	if typeof(sc) == TYPE_DICTIONARY:
		if sc.get("nozzle_position") is Array and sc["nozzle_position"].size() == 3:
			nozzle_ids = sc["nozzle_position"]
		if sc.get("position") is Array and sc["position"].size() == 3:
			position_ids = sc["position"]
		if sc.get("attitude") is Array and sc["attitude"].size() == 4:
			attitude_ids = sc["attitude"]
		if sc.get("engine_state") is String:
			engine_id = sc["engine_state"]
	var tbs = d.get("timebases", {})
	if typeof(tbs) != TYPE_DICTIONARY or tbs.is_empty():
		error = "the record has no timebases"
		return
	# Primary timebase: the one the scene names, else the one with the most samples (model.js).
	var tb := ""
	if typeof(sc) == TYPE_DICTIONARY and sc.get("timebase") is String and tbs.has(sc["timebase"]):
		tb = sc["timebase"]
	else:
		var best := -1
		for k in tbs.keys():
			if tbs[k].size() > best:
				best = tbs[k].size()
				tb = k
	for v in tbs[tb]:
		times.append(float(v))
	if times.size() < 1:
		error = "the scene timebase is empty"
		return
	for i in range(1, times.size()):
		if not (times[i] > times[i - 1]):
			error = "the scene timebase is not strictly increasing"
			return
	for c in d.get("channels", []):
		if typeof(c) != TYPE_DICTIONARY or str(c.get("timebase", "")) != tb:
			continue
		var vals = c.get("values", [])
		if not (vals is Array) or vals.size() != times.size():
			continue
		channels[str(c.get("id", ""))] = vals
	for id in nozzle_ids:
		if not channels.has(id):
			error = "the record has no nozzle position channel %s" % id
			return


# Reads a vv-run.v2 record: the mission timebase, the entities of the scene (each with its timebase
# and its altitude and downrange channels) and the metadata the record declares for them. Anything
# unknown, or a channel that does not have one value per sample of its timebase, refuses the record.
func _init_v2(d: Dictionary) -> void:
	var scene = d.get("scene", {})
	if typeof(scene) != TYPE_DICTIONARY or str(scene.get("kind", "")) != "ascent":
		error = "the record is not a launch ascent (scene kind ascent)"
		return
	scene_data = scene
	var erk = scene.get("earth_radius_km")
	if (typeof(erk) == TYPE_INT or typeof(erk) == TYPE_FLOAT) and float(erk) > 1000.0:
		earth_radius_km = float(erk)
	var tbs = d.get("timebases", {})
	if typeof(tbs) != TYPE_DICTIONARY or tbs.is_empty():
		error = "the record has no timebases"
		return
	var timebases := {}
	for k in tbs.keys():
		if not (tbs[k] is Array) or tbs[k].is_empty():
			error = "timebase %s is not a list of samples" % str(k)
			return
		var arr := PackedFloat64Array()
		for v in tbs[k]:
			if typeof(v) != TYPE_INT and typeof(v) != TYPE_FLOAT:
				error = "timebase %s has a value that is not a number" % str(k)
				return
			arr.append(float(v))
		for i in range(1, arr.size()):
			if not (arr[i] > arr[i - 1]):
				error = "timebase %s is not strictly increasing" % str(k)
				return
		timebases[str(k)] = arr
	var sc = scene.get("channels", {})
	var mission_tb := str(sc.get("timebase", "")) if typeof(sc) == TYPE_DICTIONARY else ""
	if not timebases.has(mission_tb):
		error = "the scene's replay timebase is not a timebase of the record"
		return
	times = timebases[mission_tb]
	# Channels: every one must have one value per sample of its own timebase.
	var by_id := {}
	for c in d.get("channels", []):
		if typeof(c) != TYPE_DICTIONARY:
			error = "a channel is not an object"
			return
		var cid := str(c.get("id", ""))
		var ctb := str(c.get("timebase", ""))
		var vals = c.get("values", [])
		if cid == "" or not timebases.has(ctb) or not (vals is Array):
			error = "channel %s has no valid timebase or values" % cid
			return
		if vals.size() != timebases[ctb].size():
			error = "channel %s has %d values for the %d samples of timebase %s" % [cid, vals.size(), timebases[ctb].size(), ctb]
			return
		by_id[cid] = {"timebase": ctb, "values": vals}
	var meta_list = d.get("entities", null)
	var scene_list = scene.get("entities", null)
	if not (meta_list is Array) or not (scene_list is Array) or scene_list.is_empty() or scene_list.size() > MAX_ENTITIES:
		error = "a vv-run.v2 record needs entities (record and scene), at most %d" % MAX_ENTITIES
		return
	var meta := {}
	for m0 in meta_list:
		if typeof(m0) == TYPE_DICTIONARY:
			meta[str(m0.get("id", ""))] = m0
	var palette := [Color("#d9dde3"), Color("#e8863a"), Color("#6fb1e6")]
	for se in scene_list:
		if typeof(se) != TYPE_DICTIONARY:
			error = "a scene entity is not an object"
			return
		var id := str(se.get("id", ""))
		if id == "" or not meta.has(id):
			error = "scene entity %s is not an entity of the record (unknown entity)" % id
			return
		for e0 in entities:
			if e0["id"] == id:
				error = "entity %s appears twice" % id
				return
		var tb := str(se.get("timebase", ""))
		if not timebases.has(tb):
			error = "entity %s uses an unknown timebase %s" % [id, tb]
			return
		var parent = se.get("parent", null)
		if parent != null:
			var known := false
			for e0 in entities:
				known = known or e0["id"] == str(parent)
			if not known:
				error = "entity %s has a parent that is not declared before it" % id
				return
		var alt_id := str(se.get("altitude", ""))
		var dr_id := str(se.get("downrange", ""))
		for cid2 in [alt_id, dr_id]:
			if not by_id.has(cid2) or by_id[cid2]["timebase"] != tb:
				error = "entity %s needs channel %s on its own timebase" % [id, cid2]
				return
		var m: Dictionary = meta[id]
		var ch := {}
		for cid3 in m.get("channels", []):
			if not by_id.has(str(cid3)) or by_id[str(cid3)]["timebase"] != tb:
				error = "entity %s lists channel %s that is not on its timebase" % [id, str(cid3)]
				return
			var short := str(cid3)
			if short.begins_with(id + "_"):
				short = short.substr(id.length() + 1)
			ch[short] = by_id[str(cid3)]["values"]
		ch["altitude_km"] = by_id[alt_id]["values"]
		ch["downrange_km"] = by_id[dr_id]["values"]
		var et: PackedFloat64Array = timebases[tb]
		# The curved plane of the Studio's ascent view: x along the pad's horizon, y above the pad,
		# per sample (null where either channel is null).
		var px := []
		var py := []
		var alt_v: Array = ch["altitude_km"]
		var dr_v: Array = ch["downrange_km"]
		for i in et.size():
			if alt_v[i] == null or dr_v[i] == null:
				px.append(null)
				py.append(null)
				continue
			var th: float = float(dr_v[i]) / earth_radius_km
			var rho: float = earth_radius_km + float(alt_v[i])
			px.append(rho * sin(th))
			py.append(rho * cos(th) - earth_radius_km)
		entities.append({
			"id": id, "label": str(se.get("label", id)), "kind": str(se.get("kind", "")), "parent": parent,
			"times": et, "t_start": et[0], "t_end": et[et.size() - 1],
			"end_reason": str(m.get("end_reason", "")), "ch": ch, "px": px, "py": py,
			"color": palette[entities.size() % palette.size()],
		})
	if typeof(scene.get("visual", {})) != TYPE_DICTIONARY:
		scene_data["visual"] = {}


# Value of array `values` (one per sample of `tms`) at t: linear between the two samples around t,
# the earlier sample when either is null or t is outside (dom.js sampleAt).
static func sample_arr(tms: PackedFloat64Array, values: Array, t: float) -> Variant:
	var n := tms.size()
	if n == 0:
		return null
	var i := 0
	if t >= tms[n - 1]:
		i = n - 1
	elif t > tms[0]:
		var lo := 0
		var hi := n - 1
		while hi - lo > 1:
			var mid := (lo + hi) >> 1
			if tms[mid] <= t:
				lo = mid
			else:
				hi = mid
		i = lo
	var a = values[i]
	if i >= n - 1 or t <= tms[i]:
		return a
	var b = values[i + 1]
	if a == null or b == null:
		return a
	var den := tms[i + 1] - tms[i]
	if den == 0.0:
		den = 1.0
	var f := (t - tms[i]) / den
	return float(a) + (float(b) - float(a)) * f


# True when entity `e` exists at logical time t (the Studio draws it only between its first and its
# last sample).
func entity_active(e: Dictionary, t: float) -> bool:
	var tm: PackedFloat64Array = e["times"]
	return tm.size() > 0 and t >= tm[0] and t <= tm[tm.size() - 1]


# Position of entity `e` at t in the curved plane (km: east along the pad's horizon, up above the
# pad), interpolated between the recorded samples of its own timebase; null in a gap. Display only.
func entity_plane(e: Dictionary, t: float) -> Variant:
	var x = sample_arr(e["times"], e["px"], t)
	var y = sample_arr(e["times"], e["py"], t)
	if x == null or y == null:
		return null
	return [float(x), float(y)]


# Unit vector (east, up) along the recorded velocity of entity `e` at t, in the curved plane, from
# the recorded speed and radial velocity (no attitude is recorded or simulated); the local vertical
# when the speed is below 1 m/s.
func entity_axis(e: Dictionary, t: float) -> Array:
	var sp = entity_value(e, "speed_m_s", t)
	var vr = entity_value(e, "radial_velocity_m_s", t)
	var dr = sample_arr(e["times"], e["ch"]["downrange_km"], t)
	var th: float = float(dr) / earth_radius_km if dr != null else 0.0
	if sp == null or vr == null or float(sp) < 1.0:
		return [sin(th), cos(th)]
	var s_: float = float(sp)
	var r_: float = clampf(float(vr), -s_, s_)
	var h_: float = sqrt(maxf(s_ * s_ - r_ * r_, 0.0))
	return [(r_ * sin(th) + h_ * cos(th)) / s_, (r_ * cos(th) - h_ * sin(th)) / s_]


# Sample of a named channel (e.g. "speed_m_s", "throttle") of entity `e` at t, or null.
func entity_value(e: Dictionary, name: String, t: float) -> Variant:
	if not e["ch"].has(name):
		return null
	return sample_arr(e["times"], e["ch"][name], t)


func t0() -> float:
	return times[0]


func t1() -> float:
	return times[times.size() - 1]


func has(id: String) -> bool:
	return channels.has(id)


# Largest index i with times[i] <= t, clamped to the ends (dom.js lowerIndex).
func lower_index(t: float) -> int:
	var lo := 0
	var hi := times.size() - 1
	if hi < 0:
		return -1
	if t <= times[0]:
		return 0
	if t >= times[hi]:
		return hi
	while hi - lo > 1:
		var mid := (lo + hi) >> 1
		if times[mid] <= t:
			lo = mid
		else:
			hi = mid
	return lo


# Linear interpolation of a channel at t, display only; null in a gap (dom.js sampleAt).
func sample_at(id: String, t: float) -> Variant:
	if not channels.has(id):
		return null
	var values: Array = channels[id]
	var i := lower_index(t)
	if i < 0:
		return null
	var a = values[i]
	if i >= times.size() - 1 or t <= times[i]:
		return a
	var b = values[i + 1]
	if a == null or b == null:
		return a
	var den := times[i + 1] - times[i]
	if den == 0.0:
		den = 1.0
	var f := (t - times[i]) / den
	return float(a) + (float(b) - float(a)) * f


# Value of the sample at or before t (the Studio readout and the plume use these, not interpolation).
func sample_value(id: String, t: float) -> Variant:
	if not channels.has(id):
		return null
	var i := lower_index(t)
	return null if i < 0 else channels[id][i]


static func _q(w, x, y, z) -> Array:
	var a := [float(w if w != null else 1.0), float(x if x != null else 0.0), float(y if y != null else 0.0), float(z if z != null else 0.0)]
	return a


static func _normalize(q: Array) -> Array:
	var l: float = sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
	if l == 0.0:
		return [1.0, 0.0, 0.0, 0.0]
	return [q[0] / l, q[1] / l, q[2] / l, q[3] / l]


# Quaternion.slerp of three.js r170 (the technical view), on [w, x, y, z] in 64-bit floats.
static func slerp_three(qa: Array, qb: Array, t: float) -> Array:
	if t == 0.0:
		return qa.duplicate()
	if t == 1.0:
		return qb.duplicate()
	var x: float = qa[1]
	var y: float = qa[2]
	var z: float = qa[3]
	var w: float = qa[0]
	var cos_half: float = w * qb[0] + x * qb[1] + y * qb[2] + z * qb[3]
	var bw: float = qb[0]
	var bx: float = qb[1]
	var by: float = qb[2]
	var bz: float = qb[3]
	if cos_half < 0.0:
		bw = -bw
		bx = -bx
		by = -by
		bz = -bz
		cos_half = -cos_half
	if cos_half >= 1.0:
		return [w, x, y, z]
	var sqr_sin := 1.0 - cos_half * cos_half
	if sqr_sin <= 2.220446049250313e-16:
		var s := 1.0 - t
		return _normalize([s * w + t * bw, s * x + t * bx, s * y + t * by, s * z + t * bz])
	var sin_half := sqrt(sqr_sin)
	var half := atan2(sin_half, cos_half)
	var ra := sin((1.0 - t) * half) / sin_half
	var rb := sin(t * half) / sin_half
	return [w * ra + bw * rb, x * ra + bx * rb, y * ra + by * rb, z * ra + bz * rb]


# The channel `id` if it has one value per sample, else an empty array.
func _full_channel(id: String) -> Array:
	var c = channels.get(id, [])
	return c if (c is Array and c.size() == times.size()) else []


# Pose of the stage at logical time t, as rocket.js setTime draws it: the nozzle exit plane
# position (interpolated) and the attitude slerped between the two recorded samples.
# Returns {position: [e, n, u] or null, quaternion: [w, x, y, z], index: i}.
func pose_at(t: float) -> Dictionary:
	var i := lower_index(t)
	var nx = sample_at(nozzle_ids[0], t)
	var ny = sample_at(nozzle_ids[1], t)
	var nz = sample_at(nozzle_ids[2], t)
	var pos = null
	if nx != null and ny != null and nz != null:
		pos = [float(nx), float(ny), float(nz)]
	var q := [1.0, 0.0, 0.0, 0.0]
	var has_q := _full_channel(attitude_ids[0]).size() > 0
	if has_q:
		# All four components must have exactly one value per sample; a component with another
		# length counts as absent (0, and the attitude is the identity if w is absent).
		var cw: Array = _full_channel(attitude_ids[0])
		var cx: Array = _full_channel(attitude_ids[1])
		var cy: Array = _full_channel(attitude_ids[2])
		var cz: Array = _full_channel(attitude_ids[3])
		var qa := _normalize(_q(cw[i], cx[i] if cx.size() else 0.0, cy[i] if cy.size() else 0.0, cz[i] if cz.size() else 0.0))
		if i < times.size() - 1 and cw[i + 1] != null:
			var qb := _normalize(_q(cw[i + 1], cx[i + 1] if cx.size() else 0.0, cy[i + 1] if cy.size() else 0.0, cz[i + 1] if cz.size() else 0.0))
			var den := times[i + 1] - times[i]
			if den == 0.0:
				den = 1.0
			var f := clampf((t - times[i]) / den, 0.0, 1.0)
			q = slerp_three(qa, qb, f)
		else:
			q = qa
	return {"position": pos, "quaternion": q, "index": i}


# Plume length in metres from the applied throttle of the sample at t (rocket.js: 6 + 22 * throttle
# when the engine is on). Illustrative presentation of a recorded value.
func plume_length(t: float) -> float:
	var thr = sample_value("act_throttle", t)
	var eng = sample_value(engine_id, t) if channels.has(engine_id) else null
	var on: bool
	if eng != null:
		on = int(eng) == 1
	else:
		on = thr != null and float(thr) > 0.0
	if on and thr != null and float(thr) != 0.0:
		return 6.0 + 22.0 * float(thr)
	return 0.0


func outcome() -> Dictionary:
	var o = data.get("outcome", {})
	return o if typeof(o) == TYPE_DICTIONARY else {}


func safety() -> Dictionary:
	var s = data.get("safety", {})
	return s if typeof(s) == TYPE_DICTIONARY else {}


func pad() -> Dictionary:
	var p = data.get("scene", {}).get("pad", {})
	var c = p.get("centre_m", [0.0, 0.0])
	return {
		"cx": float(c[0]) if c is Array and c.size() == 2 else 0.0,
		"cy": float(c[1]) if c is Array and c.size() == 2 else 0.0,
		"land": float(p.get("landing_radius_m")) if p.get("landing_radius_m") is float else -1.0,
		"keep": float(p.get("keep_out_radius_m")) if p.get("keep_out_radius_m") is float else -1.0,
	}
