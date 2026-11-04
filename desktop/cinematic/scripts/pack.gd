# Environment pack (vv-geo-environment v1 to v3), read for display. Before any file is used its size
# and SHA-256 are checked against environment.json; a mismatch refuses the whole pack. File names
# are the fixed names of the schema, never paths taken from the manifest. Heights and the terrain
# sampling follow desktop/studio/ui/js/environments.js (gridAt, detailWeight, terrainAt), so the
# drawn surface is the one the technical view draws.
extends RefCounted

const SCHEMAS := ["vv-geo-environment.v1", "vv-geo-environment.v2", "vv-geo-environment.v3"]
const MAX_MANIFEST_BYTES := 1024 * 1024
const MAX_FILE_BYTES := 64 * 1024 * 1024

var dir := ""
var m: Dictionary = {}
var error := ""
var verified: Array = []  # [{file, bytes, sha256}]

# Base grid and the optional detail layer: {up: PackedFloat32Array, cols, rows, s, x0, y0, image: Image}
var base: Dictionary = {}
var detail: Dictionary = {}  # empty when the pack has none; else also half, blend
var features = null  # Dictionary or null
var vegetation: Dictionary = {}  # {n, x, y, h, r: PackedFloat32Array, kind, rgb: PackedByteArray}


static func load_dir(path: String) -> RefCounted:
	var p = load("res://scripts/pack.gd").new()
	p.dir = path
	p._load()
	return p


func _fail(msg: String) -> void:
	if error == "":
		error = msg


func _load() -> void:
	var mpath := dir.path_join("environment.json")
	if not FileAccess.file_exists(mpath):
		_fail("no environment.json in the pack directory")
		return
	var f := FileAccess.open(mpath, FileAccess.READ)
	if f == null or f.get_length() > MAX_MANIFEST_BYTES:
		_fail("environment.json cannot be read or is too large")
		return
	var parsed = JSON.parse_string(f.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		_fail("environment.json is not a JSON object")
		return
	m = parsed
	if not (str(m.get("schema", "")) in SCHEMAS):
		_fail("unknown pack schema %s" % str(m.get("schema", "")))
		return
	var frame = m.get("frame", {})
	if typeof(frame) != TYPE_DICTIONARY or str(frame.get("kind", "")) != "enu-tangent-plane":
		_fail("the pack frame is not an ENU tangent plane")
		return
	if float(frame.get("heading_deg", NAN)) != 0.0:
		_fail("only packs with heading 0 are supported (as vv-geo)")
		return
	# Base layer.
	base = _layer(m.get("height", {}), m.get("image", {}), "height.u16", "image.jpg")
	if error != "":
		return
	for l in m.get("layers", []):
		if typeof(l) == TYPE_DICTIONARY and str(l.get("role", "")) == "detail":
			detail = _layer(l.get("height", {}), l.get("image", {}), "detail-height.u16", "detail-image.jpg")
			if error != "":
				return
			detail["half"] = float(l.get("extent_m", 0.0))
			detail["blend"] = float(l.get("blend_m", 0.0))
	var w = m.get("world", null)
	if typeof(w) == TYPE_DICTIONARY:
		if typeof(w.get("features")) == TYPE_DICTIONARY:
			var bytes := _verified_bytes(w["features"], "features.json")
			if error != "":
				return
			features = JSON.parse_string(bytes.get_string_from_utf8())
			if typeof(features) != TYPE_DICTIONARY or not (features.get("buildings") is Array and features.get("lidar_structures") is Array and features.get("structures") is Array):
				_fail("features.json does not have the declared lists")
				return
		if typeof(w.get("vegetation")) == TYPE_DICTIONARY:
			var vb := _verified_bytes(w["vegetation"], "vegetation.bin")
			if error != "":
				return
			if vb.size() % 12 != 0:
				_fail("vegetation.bin is not a whole number of 12-byte records")
				return
			_parse_vegetation(vb)


# Reads `name` from the pack and checks it against the manifest entry `e` ({file, bytes, sha256}).
func _verified_bytes(e: Dictionary, name: String) -> PackedByteArray:
	if str(e.get("file", "")) != name:
		_fail("manifest names %s where %s is expected" % [str(e.get("file", "")), name])
		return PackedByteArray()
	var path := dir.path_join(name)
	if not FileAccess.file_exists(path):
		_fail("%s is missing" % name)
		return PackedByteArray()
	var f := FileAccess.open(path, FileAccess.READ)
	var n := f.get_length()
	if n > MAX_FILE_BYTES or n != int(e.get("bytes", -1)):
		_fail("%s has %d bytes, the manifest declares %s" % [name, n, str(e.get("bytes", "?"))])
		return PackedByteArray()
	var bytes := f.get_buffer(n)
	var h := HashingContext.new()
	h.start(HashingContext.HASH_SHA256)
	h.update(bytes)
	var hex := h.finish().hex_encode()
	if hex != str(e.get("sha256", "")).to_lower():
		_fail("%s does not match its SHA-256 in environment.json (tampered or damaged)" % name)
		return PackedByteArray()
	verified.append({"file": name, "bytes": n, "sha256": hex})
	return bytes


func _layer(hm: Dictionary, im: Dictionary, hname: String, iname: String) -> Dictionary:
	var hb := _verified_bytes(hm, hname)
	if error != "":
		return {}
	var cols := int(hm.get("columns", 0))
	var rows := int(hm.get("rows", 0))
	if cols < 2 or rows < 2 or hb.size() != cols * rows * 2:
		_fail("%s does not have the declared size" % hname)
		return {}
	if str(hm.get("encoding", "")) != "uint16-le":
		_fail("%s is not uint16-le" % hname)
		return {}
	var scale := float(hm.get("scale_m", 0.0))
	var offset := float(hm.get("offset_m", 0.0))
	var up := PackedFloat32Array()
	up.resize(cols * rows)
	for i in cols * rows:
		up[i] = hb.decode_u16(i * 2) * scale + offset
	var ib := _verified_bytes(im, iname)
	if error != "":
		return {}
	var img := Image.new()
	if img.load_jpg_from_buffer(ib) != OK:
		_fail("%s is not a readable JPEG" % iname)
		return {}
	var first = hm.get("first_node_m", [0.0, 0.0])
	return {"up": up, "cols": cols, "rows": rows, "s": float(hm.get("spacing_m", 1.0)), "x0": float(first[0]), "y0": float(first[1]), "image": img}


func _parse_vegetation(b: PackedByteArray) -> void:
	var n := b.size() / 12
	var x := PackedFloat32Array()
	var y := PackedFloat32Array()
	var h := PackedFloat32Array()
	var r := PackedFloat32Array()
	var kind := PackedByteArray()
	var rgb := PackedByteArray()
	x.resize(n)
	y.resize(n)
	h.resize(n)
	r.resize(n)
	kind.resize(n)
	rgb.resize(n * 3)
	for i in n:
		var o := i * 12
		x[i] = b.decode_s16(o) / 10.0
		y[i] = b.decode_s16(o + 2) / 10.0
		h[i] = b.decode_u16(o + 4) / 100.0
		r[i] = b[o + 6] / 10.0
		kind[i] = b[o + 7]
		rgb[3 * i] = b[o + 8]
		rgb[3 * i + 1] = b[o + 9]
		rgb[3 * i + 2] = b[o + 10]
	vegetation = {"n": n, "x": x, "y": y, "h": h, "r": r, "kind": kind, "rgb": rgb}


func extent() -> float:
	return float(m.get("extent_m", 0.0))


func orthometric_origin() -> float:
	var o = m.get("origin", {})
	return float(o.get("orthometric_height_m", NAN)) if typeof(o) == TYPE_DICTIONARY else NAN


# ENU up of one height grid at (east, north) on its drawn triangles; NAN outside (gridAt).
static func grid_at(g: Dictionary, e: float, n: float) -> float:
	var fx: float = (e - g["x0"]) / g["s"]
	var fy: float = (g["y0"] - n) / g["s"]
	if not (fx >= 0.0 and fy >= 0.0 and fx <= g["cols"] - 1 and fy <= g["rows"] - 1):
		return NAN
	var cols: int = g["cols"]
	var c: int = mini(cols - 2, int(floor(fx)))
	var r: int = mini(g["rows"] - 2, int(floor(fy)))
	var tx := fx - c
	var ty := fy - r
	var up: PackedFloat32Array = g["up"]
	var a: float = up[r * cols + c]
	var b: float = up[r * cols + c + 1]
	var d: float = up[(r + 1) * cols + c]
	var gg: float = up[(r + 1) * cols + c + 1]
	# Cells split into (a, d, b) and (b, d, g), as the meshes are built.
	if tx + ty <= 1.0:
		return a + (b - a) * tx + (d - a) * ty
	return gg + (d - gg) * (1.0 - tx) + (b - gg) * (1.0 - ty)


static func detail_weight(d: Dictionary, e: float, n: float) -> float:
	var inside: float = d["half"] - maxf(absf(e), absf(n))
	if inside < 0.0:
		return 0.0
	return minf(1.0, inside / d["blend"]) if d["blend"] > 0.0 else 1.0


# ENU up of the drawn terrain: detail where it covers the point, blending into the base over its
# edge margin; NAN outside the pack (terrainAt).
func terrain_at(e: float, n: float) -> float:
	var b := grid_at(base, e, n)
	if not detail.is_empty():
		var u := grid_at(detail, e, n)
		if not is_nan(u):
			var w := detail_weight(detail, e, n)
			return u if (w >= 1.0 or is_nan(b)) else b + (u - b) * w
	return b


func ground(e: float, n: float) -> float:
	var g := terrain_at(e, n)
	return 0.0 if is_nan(g) else g


func credits() -> PackedStringArray:
	# The short credit line of every source, without repeats (the full attributions are in the pack).
	var out := PackedStringArray()
	for s in m.get("sources", []):
		if typeof(s) == TYPE_DICTIONARY:
			var c := str(s.get("credit", s.get("attribution", "")))
			if c != "" and not (c in out):
				out.append(c)
	return out
