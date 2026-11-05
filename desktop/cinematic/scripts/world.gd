# World layer of a v3 pack (features.json, vegetation.bin), as world-layer.js reads it.
# Data: footprints (OSM, lidar outlines), heights with their source, point structures, vegetation
# positions, heights, crown radii and image colours. Illustrative: walls, flat roofs, structure
# shapes, crown shapes, foliage cards and the colour detail. Deterministic: every per-instance
# variation is a hash of the record's position; the density setting keeps a hash-chosen subset.
extends RefCounted

const TILE := 256.0
const FOLIAGE_LUM := 0.11


static func lin(v: int) -> float:
	var c := v / 255.0
	return c / 12.92 if c <= 0.04045 else pow((c + 0.055) / 1.055, 2.4)


static func hash2(a: int, b: int) -> float:
	# 32-bit integer hash, the same as world-layer.js hash2.
	var h := ((a * 374761393) + (b * 668265263)) & 0xffffffff
	h = ((h ^ (h >> 13)) * 1274126177) & 0xffffffff
	return float((h ^ (h >> 16)) & 0xffffffff) / 4294967296.0


# Appends triangle (a, b, c) facing along `n` (Godot front faces are clockwise).
static func _tri(v: PackedVector3Array, nv: PackedVector3Array, cv: PackedColorArray, a: Vector3, b: Vector3, c: Vector3, n: Vector3, col: Color, foot_y := -INF) -> void:
	if (b - a).cross(c - a).dot(n) > 0.0:
		var t := b
		b = c
		c = t
	v.append(a); v.append(b); v.append(c)
	nv.append(n); nv.append(n); nv.append(n)
	for p in [a, b, c]:
		var k := col
		k.a = 0.0 if p.y <= foot_y + 0.001 else 1.0
		cv.append(k)


static func _mesh(v: PackedVector3Array, nv: PackedVector3Array, cv: PackedColorArray, uv := PackedVector2Array()) -> ArrayMesh:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = v
	arrays[Mesh.ARRAY_NORMAL] = nv
	arrays[Mesh.ARRAY_COLOR] = cv
	if uv.size():
		arrays[Mesh.ARRAY_TEX_UV] = uv
	var m := ArrayMesh.new()
	if v.size():
		m.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return m


static func build(pack, parent: Node3D, settings: Dictionary) -> Dictionary:
	var stats := {"buildings": 0, "lidar_structures": 0, "structures": 0, "trees": 0, "shrubs": 0, "drawn_vegetation": 0, "tiles": 0}
	var group := Node3D.new()
	group.name = "WorldLayer"
	parent.add_child(group)
	if pack.features != null:
		_buildings(pack, group, stats)
	if not pack.vegetation.is_empty():
		_vegetation(pack, group, settings, stats)
	return {"group": group, "stats": stats}


static func _buildings(pack, group: Node3D, stats: Dictionary) -> void:
	var f: Dictionary = pack.features
	var v := PackedVector3Array()
	var nv := PackedVector3Array()
	var cv := PackedColorArray()
	var concrete := Color(0.5, 0.49, 0.46)
	var pale := Color(0.62, 0.63, 0.64)
	var list: Array = f["buildings"] + f["lidar_structures"]
	stats["buildings"] = f["buildings"].size()
	stats["lidar_structures"] = f["lidar_structures"].size()
	for b in list:
		var ring: Array = b["ring_dm"]
		var n := ring.size() / 2
		if n < 3:
			continue
		var pts := PackedVector2Array()
		var gmin := INF
		var gsum := 0.0
		for i in n:
			var x: float = ring[2 * i] / 10.0
			var y: float = ring[2 * i + 1] / 10.0
			pts.append(Vector2(x, y))
			var g: float = pack.ground(x, y)
			gmin = minf(gmin, g)
			gsum += g
		var base := gmin - 0.4
		# Estimated heights (no lidar, no OSM tag) are drawn at most 3.5 m tall and paler, as in
		# the technical view, so they do not read as measured buildings.
		var est: bool = str(b.get("hs", "")) == "default"
		var top: float = gsum / n + (minf(3.5, b["h_dm"] / 10.0) if est else b["h_dm"] / 10.0)
		var roof := Color(lin(int(b["roof"][0])), lin(int(b["roof"][1])), lin(int(b["roof"][2])))
		if est:
			roof = roof.lerp(pale, 0.35)
		var wall := roof.lerp(pale if est else concrete, 0.6)
		for i in n:
			var j := (i + 1) % n
			var a2 := pts[i]
			var b2 := pts[j]
			var d := b2 - a2
			var ln := maxf(d.length(), 1e-6)
			var out := Vector3(d.y / ln, 0.0, d.x / ln)  # ENU (dy, -dx, 0) in the Godot frame
			var p0 := Vector3(a2.x, base, -a2.y)
			var p1 := Vector3(b2.x, base, -b2.y)
			var p2 := Vector3(b2.x, top, -b2.y)
			var p3 := Vector3(a2.x, top, -a2.y)
			_tri(v, nv, cv, p0, p1, p2, out, wall, base)
			_tri(v, nv, cv, p0, p2, p3, out, wall, base)
		var tris := Geometry2D.triangulate_polygon(pts)
		for k in range(0, tris.size(), 3):
			var q0 := pts[tris[k]]
			var q1 := pts[tris[k + 1]]
			var q2 := pts[tris[k + 2]]
			_tri(v, nv, cv, Vector3(q0.x, top, -q0.y), Vector3(q1.x, top, -q1.y), Vector3(q2.x, top, -q2.y), Vector3.UP, roof)
	# Point structures: a tapered column at the mapped position and height (illustrative shape).
	for s in f["structures"]:
		var h: float = s["h_dm"] / 10.0
		var r: float = maxf(0.3, s["r_dm"] / 10.0)
		var x: float = s["x_dm"] / 10.0
		var y: float = s["y_dm"] / 10.0
		var g: float = pack.ground(x, y)
		var col := Color(0.70, 0.70, 0.67)
		var seg := 12
		for k in seg:
			var a0 := TAU * k / seg
			var a1 := TAU * (k + 1) / seg
			var dn := Vector3(cos((a0 + a1) / 2.0), 0.15, -sin((a0 + a1) / 2.0)).normalized()
			var b0 := Vector3(x + r * cos(a0), g, -(y + r * sin(a0)))
			var b1 := Vector3(x + r * cos(a1), g, -(y + r * sin(a1)))
			var t0 := Vector3(x + 0.7 * r * cos(a0), g + h, -(y + 0.7 * r * sin(a0)))
			var t1 := Vector3(x + 0.7 * r * cos(a1), g + h, -(y + 0.7 * r * sin(a1)))
			_tri(v, nv, cv, b0, b1, t1, dn, col)
			_tri(v, nv, cv, b0, t1, t0, dn, col)
			_tri(v, nv, cv, Vector3(x, g + h, -y), t0, t1, Vector3.UP, col)
		stats["structures"] += 1
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/building.gdshader")
	var mi := MeshInstance3D.new()
	mi.name = "Footprints"
	mi.mesh = _mesh(v, nv, cv)
	mi.material_override = mat
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	group.add_child(mi)


# --- vegetation ---------------------------------------------------------------------------------

# A lumpy crown (ellipsoid displaced by a fixed pattern), centred at height cz, radii (rx, rz),
# with a darker underside in the vertex colour; plus an optional trunk. Unit plant: 1 m tall.
static func _plant_mesh(cz: float, rx: float, rz: float, seed: float, rings: int, trunk: bool, dark: float) -> ArrayMesh:
	var sm := SphereMesh.new()
	sm.radius = 1.0
	sm.height = 2.0
	sm.radial_segments = rings * 2
	sm.rings = rings
	var a := sm.get_mesh_arrays()
	var pv: PackedVector3Array = a[Mesh.ARRAY_VERTEX]
	var pn: PackedVector3Array = a[Mesh.ARRAY_NORMAL]
	var idx: PackedInt32Array = a[Mesh.ARRAY_INDEX]
	var v := PackedVector3Array()
	var nv := PackedVector3Array()
	var cv := PackedColorArray()
	for k in idx.size():
		var u := pv[idx[k]].normalized()  # Godot frame: y up
		var e := Vector3(u.x, -u.z, u.y)  # ENU, for the same pattern as world-layer.js
		var nn := 0.8 + 0.2 * sin(e.x * 5.1 + seed) * sin(e.y * 4.3 + 2.0 * seed) * sin(e.z * 3.7 + 1.3) + 0.06 * sin(e.x * 13.0 + e.y * 11.0 + seed)
		var p := Vector3(u.x * rx * nn, cz + u.y * rz * nn, u.z * rx * nn)
		v.append(p)
		nv.append(Vector3(p.x / rx, (p.y - cz) / rz, p.z / rx).normalized())
		var ao := (0.5 + 0.5 * clampf((p.y - (cz - rz)) / (2.0 * rz), 0.0, 1.0)) * dark
		cv.append(Color(ao, ao, ao))
	if trunk:
		var seg := 6
		for s in seg:
			var a0 := TAU * s / seg
			var a1 := TAU * (s + 1) / seg
			var q0 := Vector3(0.055 * cos(a0), 0.0, 0.055 * sin(a0))
			var q1 := Vector3(0.055 * cos(a1), 0.0, 0.055 * sin(a1))
			var q2 := Vector3(0.035 * cos(a1), 0.42, 0.035 * sin(a1))
			var q3 := Vector3(0.035 * cos(a0), 0.42, 0.035 * sin(a0))
			var on := Vector3(cos((a0 + a1) / 2.0), 0.0, sin((a0 + a1) / 2.0))
			var tc := Color(0.5, 0.4, 0.3) * dark
			tc.a = 1.0
			_tri(v, nv, cv, q0, q1, q2, on, tc)
			_tri(v, nv, cv, q0, q2, q3, on, tc)
	# SphereMesh triangles are already wound for Godot.
	return _mesh(v, nv, cv)


# Foliage cards inside a crown: n quads of the leaf texture with normals pointing out of the crown.
static func _cards_mesh(n: int, cz: float, rx: float, rz: float, seed: int) -> ArrayMesh:
	var v := PackedVector3Array()
	var nv := PackedVector3Array()
	var cv := PackedColorArray()
	var uv := PackedVector2Array()
	var s0 := seed
	var rng := func() -> float:
		s0 = (s0 * 16807) % 2147483647
		return float(s0) / 2147483647.0
	for k in n:
		var th: float = rng.call() * TAU
		var ph: float = acos(2.0 * rng.call() - 1.0)
		var rr: float = 0.25 + 0.5 * rng.call()
		var c := Vector3(sin(ph) * cos(th) * rx * rr, cz + cos(ph) * rz * rr, sin(ph) * sin(th) * rx * rr)
		var size: float = (0.75 + 0.35 * rng.call()) * maxf(rx, rz)
		var w := Vector3(rng.call() - 0.5, rng.call() - 0.5, rng.call() - 0.5).normalized()
		var a := Vector3.UP.cross(w)
		if a.length_squared() < 1e-4:
			a = Vector3.RIGHT
		a = a.normalized()
		var b := w.cross(a).normalized()
		var corners := [[-1, -1, 0, 0], [1, -1, 1, 0], [1, 1, 1, 1], [-1, -1, 0, 0], [1, 1, 1, 1], [-1, 1, 0, 1]]
		for q in corners:
			var p: Vector3 = c + (a * q[0] + b * q[1]) * size * 0.5
			v.append(p)
			nv.append(Vector3(p.x / rx, (p.y - cz) / rz, p.z / rx).normalized())
			uv.append(Vector2(q[2], q[3]))
			var ao := 0.55 + 0.45 * clampf((p.y - (cz - rz)) / (2.0 * rz), 0.0, 1.0)
			cv.append(Color(ao, ao, ao))
	return _mesh(v, nv, cv, uv)


static func leaf_texture() -> ImageTexture:
	var img := Image.create(256, 256, true, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	var seed := 977
	for k in 900:
		seed = (seed * 1103515245 + 12345) & 0x7fffffff
		var a := float(seed) / 0x7fffffff * TAU
		seed = (seed * 1103515245 + 12345) & 0x7fffffff
		var r := sqrt(float(seed) / 0x7fffffff) * 118.0
		seed = (seed * 1103515245 + 12345) & 0x7fffffff
		var tone := float(seed) / 0x7fffffff
		var cx := 128.0 + cos(a) * r
		var cy := 128.0 + sin(a) * r
		var val := clampf((150.0 + 105.0 * tone - (r / 118.0) * 50.0) / 255.0, 0.0, 1.0)
		var col := Color(val, val, val * 0.92, 1.0)
		var rx := 3.5 + 3.0 * tone
		var ry := 1.6 + 1.2 * tone
		var ang := tone * PI * 3.0
		for dy in range(-6, 7):
			for dx in range(-6, 7):
				var lx := dx * cos(ang) + dy * sin(ang)
				var ly := -dx * sin(ang) + dy * cos(ang)
				if (lx * lx) / (rx * rx) + (ly * ly) / (ry * ry) <= 1.0:
					var px := int(cx) + dx
					var py := int(cy) + dy
					if px >= 0 and py >= 0 and px < 256 and py < 256:
						img.set_pixel(px, py, col)
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


static func _vegetation(pack, group: Node3D, st: Dictionary, stats: Dictionary) -> void:
	var veg: Dictionary = pack.vegetation
	var density: float = st.get("vegetation_density", 1.0)
	var lod_near: float = st.get("lod_near_m", 700.0)
	var lod_far: float = st.get("lod_far_m", 3200.0)
	var cards_on: bool = st.get("foliage_cards", true)
	var shadows_near: bool = st.get("vegetation_shadows", true)
	# Crown archetypes (illustrative shapes; position, height and crown radius are data): trees as a
	# rounded broadleaf, a conical conifer and a flat umbrella crown; shrubs as a mound and a low,
	# spreading clump. The archetype is chosen from the lidar height and a hash of the position.
	var arche := {
		"tree0": {"core": _plant_mesh(0.64, 0.36, 0.26, 1.7, 6, true, 0.6), "cards": _cards_mesh(14, 0.64, 0.5, 0.36, 4021), "far": _plant_mesh(0.64, 0.5, 0.36, 1.7, 4, true, 1.0)},
		"tree1": {"core": _plant_mesh(0.6, 0.22, 0.36, 3.1, 6, true, 0.6), "cards": _cards_mesh(12, 0.6, 0.3, 0.4, 991), "far": _plant_mesh(0.6, 0.3, 0.4, 3.1, 4, true, 1.0)},
		"tree2": {"core": _plant_mesh(0.78, 0.42, 0.14, 5.3, 6, true, 0.6), "cards": _cards_mesh(12, 0.78, 0.56, 0.18, 2203), "far": _plant_mesh(0.78, 0.56, 0.18, 5.3, 4, true, 1.0)},
		"shrub0": {"core": _plant_mesh(0.42, 0.36, 0.4, 0.4, 6, false, 0.6), "cards": _cards_mesh(10, 0.46, 0.5, 0.5, 733), "far": _plant_mesh(0.44, 0.5, 0.56, 0.4, 4, false, 1.0)},
		"shrub1": {"core": _plant_mesh(0.34, 0.44, 0.3, 2.2, 6, false, 0.6), "cards": _cards_mesh(10, 0.36, 0.56, 0.34, 1597), "far": _plant_mesh(0.34, 0.56, 0.34, 2.2, 4, false, 1.0)},
	}
	var crown_mat := StandardMaterial3D.new()
	crown_mat.vertex_color_use_as_albedo = true
	crown_mat.roughness = 0.95
	crown_mat.metallic_specular = 0.25
	var card_mat := StandardMaterial3D.new()
	card_mat.vertex_color_use_as_albedo = true
	card_mat.albedo_texture = leaf_texture()
	card_mat.albedo_color = Color(1.2, 1.2, 1.2)
	card_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	card_mat.alpha_scissor_threshold = 0.45
	card_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	card_mat.roughness = 0.9
	card_mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	var tiles := {}
	for i in veg["n"]:
		var x: float = veg["x"][i]
		var y: float = veg["y"][i]
		var hx := int(round(x * 10.0))
		var hy := int(round(y * 10.0))
		if density < 1.0 and hash2(hx + 101, hy - 37) >= density:
			continue
		var key := Vector2i(int(floor(x / TILE)), int(floor(y / TILE)))
		var hv := hash2(hx - 911, hy + 577)
		var arch := ""
		if veg["kind"][i] == 1:
			if veg["h"][i] > 12.0:
				arch = "tree1" if hv < 0.6 else "tree0"
			else:
				arch = "tree0" if hv < 0.45 else ("tree2" if hv < 0.75 else "tree1")
		else:
			arch = "shrub0" if hv < 0.6 else "shrub1"
		if not tiles.has(key):
			tiles[key] = {}
		if not tiles[key].has(arch):
			tiles[key][arch] = []
		tiles[key][arch].append(i)
	for key in tiles:
		for kind in tiles[key]:
			var ids: Array = tiles[key][kind]
			if ids.is_empty():
				continue
			var mm_near := MultiMesh.new()
			mm_near.transform_format = MultiMesh.TRANSFORM_3D
			mm_near.use_colors = true
			mm_near.instance_count = ids.size()
			for j in ids.size():
				var i: int = ids[j]
				var x: float = veg["x"][i]
				var y: float = veg["y"][i]
				var h: float = veg["h"][i]
				var hx := int(round(x * 10.0))
				var hy := int(round(y * 10.0))
				var jitter := hash2(hx, hy)
				var d := minf(2.0 * veg["r"][i] * (0.9 + 0.2 * hash2(hy, hx)), h * 1.7 + 0.8)
				var basis := Basis(Vector3.UP, jitter * TAU).scaled(Vector3(d, h, d * (0.85 + 0.3 * jitter)))
				mm_near.set_instance_transform(j, Transform3D(basis, Vector3(x, pack.ground(x, y) - 0.15, -y)))
				var r0 := lin(veg["rgb"][3 * i])
				var g0 := lin(veg["rgb"][3 * i + 1])
				var b0 := lin(veg["rgb"][3 * i + 2])
				var lum := 0.2126 * r0 + 0.7152 * g0 + 0.0722 * b0
				var k := minf(5.0, (FOLIAGE_LUM * (0.7 + 0.6 * hash2(hx + 7, hy - 3))) / maxf(lum, 1e-3))
				# Hue spread per plant (illustrative): towards yellow-green or blue-green.
				var hs := hash2(hy + 13, hx - 29) - 0.5
				var col := Color(minf(1.0, r0 * k * (1.0 + 0.25 * hs)), minf(1.0, g0 * k * (1.0 + 0.08 * hs)), minf(1.0, b0 * k * (1.0 - 0.3 * hs)))
				if kind == "tree1":
					col = col.darkened(0.2)
				mm_near.set_instance_color(j, col)
			stats["trees" if kind.begins_with("tree") else "shrubs"] += ids.size()
			var parts := [["core", crown_mat, 0.0, lod_near, shadows_near], ["far", crown_mat, lod_near, lod_far, false]]
			if cards_on:
				parts.append(["cards", card_mat, 0.0, lod_near, shadows_near])
			for part in parts:
				var mm: MultiMesh = mm_near if part[0] == "core" else mm_near.duplicate()
				mm.mesh = arche[kind][part[0]]
				var mi := MultiMeshInstance3D.new()
				mi.multimesh = mm
				mi.material_override = part[1]
				mi.visibility_range_begin = part[2]
				mi.visibility_range_end = part[3]
				mi.visibility_range_end_margin = 40.0
				mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if part[4] else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				group.add_child(mi)
			stats["tiles"] += 1
	stats["drawn_vegetation"] = stats["trees"] + stats["shrubs"]
