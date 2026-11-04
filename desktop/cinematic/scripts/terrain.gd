# Terrain meshes of a pack: the base grid, the detail layer with the heights blended into the base
# over its margin (pack.terrain_at, as the technical view), and the ground beyond the pack. Vertices
# sit on the grid nodes and every cell is split into the same two triangles as gridAt samples, so the
# drawn surface is the sampled surface. Only the ground beyond the pack is illustrative.
extends RefCounted

const Frame := preload("res://scripts/frame.gd")
const EARTH_R := 6371000.0


# ArrayMesh of grid `g` with heights from `height_of(i, e, n)`; `drop_inside` > 0 drops cells whose
# four corners lie inside that half-extent (they are covered by the detail layer).
static func grid_mesh(pack, g: Dictionary, heights: PackedFloat32Array, drop_inside: float) -> ArrayMesh:
	var cols: int = g["cols"]
	var rows: int = g["rows"]
	var s: float = g["s"]
	var x0: float = g["x0"]
	var y0: float = g["y0"]
	var n := cols * rows
	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	var colours := PackedColorArray()
	verts.resize(n)
	norms.resize(n)
	colours.resize(n)
	var h0: float = pack.orthometric_origin()
	for r in rows:
		var nn := y0 - r * s
		for c in cols:
			var i := r * cols + c
			var e := x0 + c * s
			var z := heights[i]
			verts[i] = Vector3(e, z, -nn)
			# Central differences (one-sided at the edges) of the drawn heights.
			var zl := heights[i - 1] if c > 0 else z
			var zr := heights[i + 1] if c < cols - 1 else z
			var zn := heights[i - cols] if r > 0 else z
			var zs := heights[i + cols] if r < rows - 1 else z
			var dx := (zr - zl) / (s * (2.0 if (c > 0 and c < cols - 1) else 1.0))
			var dy := (zn - zs) / (s * (2.0 if (r > 0 and r < rows - 1) else 1.0))
			norms[i] = Vector3(-dx, 1.0, dy).normalized()
			var sea := 0.0
			if not is_nan(h0) and absf(z + h0 + (e * e + nn * nn) / (2.0 * EARTH_R)) < 0.6:
				sea = 1.0
			colours[i] = Color(1, 1, 1, sea)
	var idx := PackedInt32Array()
	idx.resize((cols - 1) * (rows - 1) * 6)
	var k := 0
	for r in rows - 1:
		var nn := y0 - r * s
		for c in cols - 1:
			if drop_inside > 0.0:
				var e0 := x0 + c * s
				if maxf(absf(e0), absf(e0 + s)) < drop_inside and maxf(absf(nn), absf(nn - s)) < drop_inside:
					continue
			var a := r * cols + c
			var b := a + 1
			var d := a + cols
			var ee := d + 1
			# Same split as gridAt: (a, d, b) and (b, d, e); clockwise as Godot's front faces.
			idx[k] = a; idx[k + 1] = b; idx[k + 2] = d
			idx[k + 3] = b; idx[k + 4] = ee; idx[k + 5] = d
			k += 6
	idx.resize(k)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = norms
	arrays[Mesh.ARRAY_COLOR] = colours
	arrays[Mesh.ARRAY_INDEX] = idx
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh


static func texture_of(img: Image) -> ImageTexture:
	var im := img.duplicate()
	if im.get_format() != Image.FORMAT_RGB8:
		im.convert(Image.FORMAT_RGB8)
	im.generate_mipmaps()
	return ImageTexture.create_from_image(im)


# Builds the terrain under `parent`. Returns {base, detail, beyond, materials, textures}.
static func build(pack, parent: Node3D) -> Dictionary:
	var shader: Shader = load("res://shaders/terrain.gdshader")
	var L: float = pack.extent()
	var has_detail: bool = not pack.detail.is_empty()
	var base_tex := texture_of(pack.base["image"])
	var mats: Array = []
	var bm := ShaderMaterial.new()
	bm.shader = shader
	bm.set_shader_parameter("albedo_tex", base_tex)
	bm.set_shader_parameter("role", 0)
	bm.set_shader_parameter("half_extent", L)
	bm.set_shader_parameter("base_half", L)
	bm.set_shader_parameter("detail_half", pack.detail["half"] if has_detail else 0.0)
	mats.append(bm)
	var base_mesh := grid_mesh(pack, pack.base, pack.base["up"], pack.detail["half"] if has_detail else 0.0)
	var base := MeshInstance3D.new()
	base.name = "TerrainBase"
	base.mesh = base_mesh
	base.material_override = bm
	parent.add_child(base)
	var out := {"base": base, "materials": mats, "textures": [base_tex]}
	if has_detail:
		var d: Dictionary = pack.detail
		var hs := PackedFloat32Array()
		hs.resize(d["cols"] * d["rows"])
		for r in d["rows"]:
			var nn: float = d["y0"] - r * d["s"]
			for c in d["cols"]:
				hs[r * d["cols"] + c] = pack.ground(d["x0"] + c * d["s"], nn)
		var dt := texture_of(d["image"])
		var dm := ShaderMaterial.new()
		dm.shader = shader
		dm.set_shader_parameter("albedo_tex", dt)
		dm.set_shader_parameter("base_tex", base_tex)
		dm.set_shader_parameter("role", 1)
		dm.set_shader_parameter("half_extent", d["half"])
		dm.set_shader_parameter("base_half", L)
		dm.set_shader_parameter("detail_half", d["half"])
		dm.set_shader_parameter("detail_blend", d["blend"])
		mats.append(dm)
		var det := MeshInstance3D.new()
		det.name = "TerrainDetail"
		det.mesh = grid_mesh(pack, d, hs, 0.0)
		det.material_override = dm
		parent.add_child(det)
		out["detail"] = det
		out["textures"].append(dt)
	out["beyond"] = _beyond(pack, parent)
	return out


# Ground beyond the pack (illustration): the pack's edge continued outwards, water at mean sea level
# where the edge is sea, otherwise the edge height and the image colour at the nearest edge point.
static func _beyond(pack, parent: Node3D) -> MeshInstance3D:
	var g: Dictionary = pack.base
	var L: float = pack.extent()
	var big := 90000.0
	var small: Image = g["image"].duplicate()
	small.resize(128, 128, Image.INTERPOLATE_BILINEAR)
	var h0: float = pack.orthometric_origin()
	if is_nan(h0):
		h0 = 0.0
	var quads := [[-big, L, big, big], [-big, -big, big, -L], [-big, -L, -L, L], [L, -L, big, L]]
	var verts := PackedVector3Array()
	var cols := PackedColorArray()
	var seg := 40
	for q in quads:
		var gx := []
		var gy := []
		for i in seg + 1:
			gx.append(_spaced(q[0], q[2], i, seg, L))
			gy.append(_spaced(q[1], q[3], i, seg, L))
		for i in seg:
			for j in seg:
				var cell := [[gx[i], gy[j]], [gx[i], gy[j + 1]], [gx[i + 1], gy[j + 1]], [gx[i], gy[j]], [gx[i + 1], gy[j + 1]], [gx[i + 1], gy[j]]]
				for p in cell:
					var ex := clampf(p[0], -L, L)
					var ny := clampf(p[1], -L, L)
					var z := Pack_edge_height(g, ex, ny)
					var sea := absf(z + h0 + (ex * ex + ny * ny) / (2.0 * EARTH_R)) < 0.6
					var zz: float = (-h0 - (p[0] * p[0] + p[1] * p[1]) / (2.0 * EARTH_R) - 0.25) if sea else z - 0.3
					verts.append(Vector3(p[0], zz, -p[1]))
					var u := clampi(int((ex + L) / (2.0 * L) * 128.0), 0, 127)
					var v := clampi(int((L - ny) / (2.0 * L) * 128.0), 0, 127)
					var col := small.get_pixel(u, v)
					cols.append(Color(col.r, col.g, col.b, 1.0 if sea else 0.0))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_COLOR] = cols
	var st := SurfaceTool.new()
	st.create_from_arrays(arrays)
	st.generate_normals()
	var mesh := st.commit()
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/beyond.gdshader")
	var mi := MeshInstance3D.new()
	mi.name = "BeyondPack"
	mi.mesh = mesh
	mi.material_override = mat
	parent.add_child(mi)
	return mi


static func _spaced(v0: float, v1: float, i: int, seg: int, L: float) -> float:
	var f := float(i) / seg
	if absf(v0) <= L + 1.0:
		return v0 + (v1 - v0) * f * f
	if absf(v1) <= L + 1.0:
		var k := float(seg - i) / seg
		return v0 + (v1 - v0) * (1.0 - k * k)
	return v0 + (v1 - v0) * f


static func Pack_edge_height(g: Dictionary, e: float, n: float) -> float:
	var c := clampi(int(round((e - g["x0"]) / g["s"])), 0, g["cols"] - 1)
	var r := clampi(int(round((g["y0"] - n) / g["s"])), 0, g["rows"] - 1)
	return g["up"][r * g["cols"] + c]
