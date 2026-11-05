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
	if str(d.get("schema", "")) != "vv-run.v1":
		error = "record schema is not vv-run.v1"
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
	var has_q := channels.has(attitude_ids[0])
	if has_q:
		var cw: Array = channels[attitude_ids[0]]
		var cx: Array = channels[attitude_ids[1]] if channels.has(attitude_ids[1]) else []
		var cy: Array = channels[attitude_ids[2]] if channels.has(attitude_ids[2]) else []
		var cz: Array = channels[attitude_ids[3]] if channels.has(attitude_ids[3]) else []
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
