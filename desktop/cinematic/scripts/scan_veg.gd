# Scanned vegetation and rocks (CC0, assets/cc0/{trees,shrubs,rocks}) in the near field of the pad.
#
# Positions, heights and crown radii are the pack's (the lidar vegetation): within RADIUS metres of the
# pad centre, and up to a budget of the nearest, a lidar tree of 9 m or less and a lidar shrub are drawn
# as a scanned model scaled to the recorded height and crown radius, with a small hash-chosen hue and
# brightness variation (the instance colour); the old shapes are then not drawn for those plants. Taller
# trees (the scanned trees are 1 to 4 m high) keep the old shapes. The boulders have no data behind them:
# they are scattered by a hash on open ground at 45 to 520 m from the pad, an illustration the label
# says so. Everything is a function of position, so it is the same in every run.
extends RefCounted

const Assets := preload("res://scripts/assets.gd")

const RADIUS := 520.0
const MAX_TREES := 70
const MAX_SHRUBS := 420
const MAX_ROCKS := 48
const TILE := 256.0

const TREES := ["island_tree_02", "pine_sapling_small"]
const SHRUBS := ["searsia_lucida", "wild_rooibos_bush", "othonna_cerarioides", "searsia_burchellii"]
const ROCKS := ["namaqualand_boulder_03", "namaqualand_boulder_04", "namaqualand_boulder_05", "namaqualand_boulder_06", "namaqualand_boulders_01"]


static func _hash(a: int, b: int, s: int) -> float:
	var h := ((a * 374761393) + (b * 668265263) + (s * 2246822519)) & 0xffffffff
	h = ((h ^ (h >> 13)) * 1274126177) & 0xffffffff
	return float((h ^ (h >> 16)) & 0xffffffff) / 4294967296.0


# The variants of a model: [{mesh, height, width}] (one per child mesh of the glb, origin at the bottom
# centre), with materials prepared for instancing (instance colours multiply the albedo) and textures
# at most `tex_side` pixels on a side with mipmaps.
static func _variants(kind: String, id: String, tex_side: int) -> Array:
	var root := Assets.load_glb("cc0/%s/%s/%s.glb" % [kind, id, id])
	var out := []
	if root == null:
		return out
	for n in root.find_children("*", "MeshInstance3D", true, false):
		var mesh: ArrayMesh = n.mesh
		if mesh == null:
			continue
		for i in mesh.get_surface_count():
			var m = mesh.surface_get_material(i)
			if m is StandardMaterial3D:
				var d: StandardMaterial3D = m.duplicate()
				d.vertex_color_use_as_albedo = true
				d.albedo_texture = _prep(d.albedo_texture, tex_side, false)
				d.normal_texture = _prep(d.normal_texture, tex_side, true)
				d.roughness_texture = _prep(d.roughness_texture, tex_side, false)
				d.metallic_texture = _prep(d.metallic_texture, tex_side, false)
				d.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
				mesh.surface_set_material(i, d)
		var box := mesh.get_aabb()
		out.append({"mesh": mesh, "height": maxf(box.size.y, 0.05), "width": maxf(maxf(box.size.x, box.size.z), 0.05)})
	root.queue_free()
	return out


static func _prep(tex: Texture2D, side: int, normal: bool) -> Texture2D:
	if tex == null:
		return null
	var img := tex.get_image()
	if img == null:
		return tex
	if img.is_compressed():
		img.decompress()
	var m := maxi(img.get_width(), img.get_height())
	if m > side:
		var k := float(side) / m
		img.resize(maxi(1, int(img.get_width() * k)), maxi(1, int(img.get_height() * k)), Image.INTERPOLATE_BILINEAR)
		img.generate_mipmaps(normal)
	elif not img.has_mipmaps():
		img.generate_mipmaps(normal)
	return ImageTexture.create_from_image(img)


# Chooses and draws the scanned plants and rocks; returns the set of pack vegetation indices that were
# replaced (the old shapes skip them) and fills `stats`. `density` is the profile's share (0 to 1).
static func build(pack, parent: Node3D, st: Dictionary, stats: Dictionary, pad: Vector2, extra := []) -> Dictionary:
	var replaced := {}
	var density: float = st.get("scan_veg", 0.0)
	if density <= 0.0:
		return replaced
	var side: int = clampi(int(st.get("tex_max", 1024)) / 2, 256, 1024)
	var veg: Dictionary = pack.vegetation
	var tree_v := []
	for id in TREES:
		tree_v.append_array(_variants("trees", id, side))
	var shrub_v := []
	for id in SHRUBS:
		shrub_v.append_array(_variants("shrubs", id, side))
	var rock_v := []
	for id in ROCKS:
		rock_v.append_array(_variants("rocks", id, side))
	if tree_v.is_empty() or shrub_v.is_empty():
		return replaced
	# Candidates by distance from the pad, the nearest first.
	# Centres: the pad (up to RADIUS) and, for the ground views, the observer (a fixed function of the
	# pack: 420 m out, clear of the canopy) up to 170 m, each with its own share of the budget.
	var centres := [[pad, RADIUS, 44.0]]
	for e in extra:
		centres.append([e, 170.0, 0.0])
	var cand := []
	if not veg.is_empty():
		for i in veg["n"]:
			var best := INF
			for c in centres:
				var dx: float = veg["x"][i] - c[0].x
				var dy: float = veg["y"][i] - c[0].y
				var d2 := dx * dx + dy * dy
				if d2 > c[1] * c[1] or d2 < c[2] * c[2]:
					continue
				best = minf(best, d2 / (c[1] * c[1]))
			if best == INF:
				continue
			var tree: bool = veg["kind"][i] == 1
			if tree and veg["h"][i] > 9.0:
				continue
			cand.append([best, i, tree])
	cand.sort_custom(func(a, b): return a[0] < b[0])
	var tiles := {}
	var n_tree := 0
	var n_shrub := 0
	var max_t := int(MAX_TREES * density) * centres.size()
	var max_s := int(MAX_SHRUBS * density) * centres.size()
	for c in cand:
		var i: int = c[1]
		var tree: bool = c[2]
		if tree and n_tree >= max_t:
			continue
		if not tree and n_shrub >= max_s:
			continue
		var x: float = veg["x"][i]
		var y: float = veg["y"][i]
		var hx := int(round(x * 10.0))
		var hy := int(round(y * 10.0))
		var pool: Array = tree_v if tree else shrub_v
		var v: Dictionary = pool[int(_hash(hx, hy, 1) * pool.size()) % pool.size()]
		var h: float = veg["h"][i]
		var sy := clampf(h / v["height"], 0.35, 4.0)
		var sxz := lerpf(sy, clampf(2.0 * veg["r"][i] / v["width"], 0.35, 4.0), 0.5)
		var yaw := _hash(hx, hy, 2) * TAU
		var tint := 0.82 + 0.36 * _hash(hx, hy, 3)
		var hue := _hash(hx, hy, 4) - 0.5
		var img_c := Color(float(veg["rgb"][3 * i]) / 255.0, float(veg["rgb"][3 * i + 1]) / 255.0, float(veg["rgb"][3 * i + 2]) / 255.0)
		var col := Color(tint * (1.0 + 0.16 * hue), tint, tint * (1.0 - 0.2 * hue)).lerp(img_c * 2.2, 0.12)
		col.a = 1.0
		var xf := Transform3D(Basis(Vector3.UP, yaw).scaled(Vector3(sxz, sy, sxz)), Vector3(x, pack.ground(x, y) - 0.05 * sy, -y))
		_add(tiles, v, x, y, xf, col)
		replaced[i] = true
		if tree:
			n_tree += 1
		else:
			n_shrub += 1
	# Boulders: no data behind them, so a hash on a ring of open ground.
	var n_rock := 0
	if not rock_v.is_empty():
		var tries := 0
		while n_rock < int(MAX_ROCKS * density) and tries < 4000:
			tries += 1
			var a := _hash(tries, 11, 5) * TAU
			var rr := 46.0 + (RADIUS - 46.0) * sqrt(_hash(tries, 13, 6))
			var x := pad.x + rr * cos(a)
			var y := pad.y + rr * sin(a)
			var v: Dictionary = rock_v[int(_hash(tries, 17, 7) * rock_v.size()) % rock_v.size()]
			var s := 0.3 + 0.9 * pow(_hash(tries, 19, 8), 2.0)
			var xf := Transform3D(Basis(Vector3.UP, _hash(tries, 23, 9) * TAU).scaled(Vector3(s, s * (0.8 + 0.4 * _hash(tries, 29, 10)), s)), Vector3(x, pack.ground(x, y) - 0.12 * s, -y))
			var tint := 0.8 + 0.3 * _hash(tries, 31, 12)
			_add(tiles, v, x, y, xf, Color(tint, tint, tint))
			n_rock += 1
	var shadows: bool = st.get("vegetation_shadows", false)
	var count := 0
	for key in tiles:
		for vid in tiles[key]:
			var e: Dictionary = tiles[key][vid]
			var mm := MultiMesh.new()
			mm.transform_format = MultiMesh.TRANSFORM_3D
			mm.use_colors = true
			mm.mesh = e["mesh"]
			mm.instance_count = e["xf"].size()
			for j in e["xf"].size():
				mm.set_instance_transform(j, e["xf"][j])
				mm.set_instance_color(j, e["col"][j])
			var mi := MultiMeshInstance3D.new()
			mi.multimesh = mm
			mi.layers = 2   # not on the decals' layer: the pad's decals would paint over them
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if shadows else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			parent.add_child(mi)
			count += e["xf"].size()
	stats["scanned_trees"] = n_tree
	stats["scanned_shrubs"] = n_shrub
	stats["scanned_rocks"] = n_rock
	return replaced


static func _add(tiles: Dictionary, v: Dictionary, x: float, y: float, xf: Transform3D, col: Color) -> void:
	var key := Vector2i(int(floor(x / TILE)), int(floor(y / TILE)))
	if not tiles.has(key):
		tiles[key] = {}
	var vid: int = v["mesh"].get_instance_id()
	if not tiles[key].has(vid):
		tiles[key][vid] = {"mesh": v["mesh"], "xf": [], "col": []}
	tiles[key][vid]["xf"].append(xf)
	tiles[key][vid]["col"].append(col)
