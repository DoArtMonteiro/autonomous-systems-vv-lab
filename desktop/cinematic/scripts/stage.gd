# Illustrative first stage, with the dimensions of desktop/studio/ui/js/scenes/stage-model.js
# (radius 1.85 m, 42 m from the nozzle exit plane to the top of the interstage, tank 3.2 to 35.5 m).
# The landing model is a rigid body with no length, gear or control surfaces: nothing here moves with
# anything the model does not record. Legs and fins never deploy; the plume length follows the
# recorded applied throttle only. Body frame: +x along the stage axis from the nozzle exit plane.
extends RefCounted

const RADIUS := 1.85
const LENGTH := 42.0
const TANK := [3.2, 35.5]


static func _mat(colour: Color, rough: float, metal: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = colour
	m.roughness = rough
	m.metallic = metal
	return m


static func _tank_texture() -> ImageTexture:
	# Panel seams, a cable raceway and soot streaks rising from the engines (deterministic).
	var w := 512
	var h := 2048
	var img := Image.create(w, h, false, Image.FORMAT_RGB8)
	img.fill(Color(0.93, 0.945, 0.957))
	var seed := 4242
	var rnd := func() -> float:
		seed = (seed * 1103515245 + 12345) & 0x7fffffff
		return float(seed) / 0x7fffffff
	var streaks := []
	for k in 90:
		streaks.append([rnd.call() * w, h * (0.35 + 0.6 * rnd.call()), 2.0 + rnd.call() * 14.0, 0.12 + 0.25 * rnd.call()])
	var paint_c := Color(0.93, 0.945, 0.957)
	var soot_c := Color(0.19, 0.16, 0.14)
	var row_k := PackedFloat32Array()
	row_k.resize(h)
	for y in h:
		# Row 0 is the top of the tank; the engine end is at the bottom of the texture.
		var soot := clampf((float(y) / h - 0.45) / 0.55, 0.0, 1.0)
		row_k[y] = 0.62 * pow(soot, 1.6)
		img.fill_rect(Rect2i(0, y, w, 1), paint_c.lerp(soot_c, row_k[y]))
	for s in streaks:
		for y in range(int(s[1]), h):
			var k := maxf(row_k[y], s[3] * (float(y) - s[1]) / (h - s[1]))
			img.fill_rect(Rect2i(int(s[0]), y, int(s[2]), 1), paint_c.lerp(soot_c, k))
	for k in range(1, 9):
		var yy := int(k * h / 9.0)
		for x in w:
			img.set_pixel(x, yy, img.get_pixel(x, yy) * 0.82)
			img.set_pixel(x, yy + 1, img.get_pixel(x, yy + 1) * 0.86)
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


static func _lattice_texture() -> ImageTexture:
	var img := Image.create(128, 128, true, Image.FORMAT_RGBA8)
	for y in 128:
		for x in 128:
			var edge := x < 6 or y < 6 or x > 121 or y > 121
			var d1 := posmod(x - y, 18) < 3
			var d2 := posmod(x + y, 18) < 3
			img.set_pixel(x, y, Color(1, 1, 1, 1) if (edge or d1 or d2) else Color(0, 0, 0, 0))
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


# Lathe mesh along +y from a profile of (radius, y) points.
static func _lathe(profile: Array, segments: int) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for i in profile.size() - 1:
		for s in segments:
			var a0 := TAU * s / segments
			var a1 := TAU * (s + 1) / segments
			var p := [
				Vector3(profile[i].x * cos(a0), profile[i].y, profile[i].x * sin(a0)),
				Vector3(profile[i].x * cos(a1), profile[i].y, profile[i].x * sin(a1)),
				Vector3(profile[i + 1].x * cos(a1), profile[i + 1].y, profile[i + 1].x * sin(a1)),
				Vector3(profile[i + 1].x * cos(a0), profile[i + 1].y, profile[i + 1].x * sin(a0)),
			]
			for t in [[0, 1, 2], [0, 2, 3]]:
				for k in t:
					st.add_vertex(p[k])
	st.generate_normals()
	return st.commit()


# Builds the stage under `vehicle` (whose local +X is the body axis). Returns
# {body, plume_nodes, outer, core, light, materials}.
static func build(vehicle: Node3D) -> Dictionary:
	var body := Node3D.new()
	body.name = "StageIllustrative"
	body.rotation = Vector3(0, 0, -PI / 2.0)  # local +Y (the build axis) onto the body axis +X
	vehicle.add_child(body)
	var paint := _mat(Color(1, 1, 1), 0.38, 0.0)
	paint.albedo_texture = _tank_texture()
	paint.clearcoat_enabled = true
	paint.clearcoat = 0.25
	paint.clearcoat_roughness = 0.4
	var carbon := _mat(Color(0.10, 0.11, 0.13), 0.55, 0.2)
	var metal := _mat(Color(0.45, 0.47, 0.5), 0.3, 0.9)
	metal.cull_mode = BaseMaterial3D.CULL_DISABLED
	var shield := _mat(Color(0.23, 0.24, 0.26), 0.8, 0.2)
	var R := RADIUS
	var add := func(mesh: Mesh, mat: Material, pos: Vector3, rot := Vector3.ZERO) -> MeshInstance3D:
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.material_override = mat
		mi.position = pos
		mi.rotation = rot
		body.add_child(mi)
		return mi
	# Engines: seven bells, exit plane at y = 0.
	var prof := []
	for i in 13:
		var f := i / 12.0
		prof.append(Vector2(0.24 + 0.32 * pow(1.0 - f, 1.6), f * 2.0))
	var bell := _lathe(prof, 32)
	var spots := [Vector2.ZERO]
	for k in 6:
		spots.append(Vector2(1.18 * cos(k * PI / 3.0), 1.18 * sin(k * PI / 3.0)))
	for s in spots:
		add.call(bell, metal, Vector3(s.x, 0, s.y))
	var cyl := func(r_top: float, r_bot: float, h: float, segs := 64, caps := false) -> CylinderMesh:
		var c := CylinderMesh.new()
		c.top_radius = r_top
		c.bottom_radius = r_bot
		c.height = h
		c.radial_segments = segs
		c.rings = 1
		c.cap_top = caps
		c.cap_bottom = caps
		return c
	add.call(cyl.call(R * 1.02, R * 1.06, 1.3), shield, Vector3(0, 2.55, 0))
	add.call(cyl.call(R * 1.02, R * 1.02, 0.08, 48, true), shield, Vector3(0, 1.95, 0))
	var tank_mesh: CylinderMesh = cyl.call(R, R, TANK[1] - TANK[0], 96)
	add.call(tank_mesh, paint, Vector3(0, (TANK[0] + TANK[1]) / 2.0, 0))
	for y in [TANK[0] + 0.15, TANK[1] - 0.1]:
		add.call(cyl.call(R * 1.008, R * 1.008, 0.3, 96), carbon, Vector3(0, y, 0))
	add.call(cyl.call(R * 1.005, R * 1.005, LENGTH - TANK[1], 96), carbon, Vector3(0, (TANK[1] + LENGTH) / 2.0, 0))
	add.call(cyl.call(R, R, 0.05, 48, true), shield, Vector3(0, LENGTH - 0.6, 0))
	# Cable raceway along the tank (illustration).
	var race := BoxMesh.new()
	race.size = Vector3(0.22, TANK[1] - TANK[0] - 0.6, 0.16)
	add.call(race, carbon, Vector3(0, (TANK[0] + TANK[1]) / 2.0, R + 0.06))
	# Four lattice fins near the top, fixed (the model has no control surfaces).
	var fin_mat := _mat(Color(0.55, 0.58, 0.61), 0.45, 0.75)
	fin_mat.albedo_texture = _lattice_texture()
	fin_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	fin_mat.alpha_scissor_threshold = 0.5
	fin_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	var fin := QuadMesh.new()
	fin.size = Vector2(1.3, 1.5)
	for k in 4:
		var a := k * PI / 2.0 + PI / 4.0
		var fi: MeshInstance3D = add.call(fin, fin_mat, Vector3((R + 0.75) * cos(a), LENGTH - 2.2, (R + 0.75) * sin(a)))
		# The lattice faces along the axis and stands out radially.
		fi.basis = Basis.looking_at(Vector3.UP, Vector3(cos(a), 0, sin(a)))
	# Four landing legs, stowed along the lower body (the model has no landing gear).
	var leg := BoxMesh.new()
	leg.size = Vector3(0.75, 11.5, 0.5)
	for k in 4:
		var a := k * PI / 2.0
		var li: MeshInstance3D = add.call(leg, carbon, Vector3((R + 0.25) * cos(a), 2.0 + 5.75, (R + 0.25) * sin(a)))
		li.rotation = Vector3(0, -a, 0)
		var foot := BoxMesh.new()
		foot.size = Vector3(0.9, 0.5, 0.7)
		add.call(foot, metal, Vector3((R + 0.35) * cos(a), 2.2, (R + 0.35) * sin(a)), Vector3(0, -a, 0))
	# Plume (illustrative): outer flame and bright core along -y from the exit plane.
	var plume_shader: Shader = load("res://shaders/plume.gdshader")
	var cone := func(r: float) -> CylinderMesh:
		var c: CylinderMesh = cyl.call(r, r * 0.12, 1.0, 40)
		return c
	var outer_mat := ShaderMaterial.new()
	outer_mat.shader = plume_shader
	outer_mat.set_shader_parameter("colour", Color(1.0, 0.55, 0.2))
	outer_mat.set_shader_parameter("intensity", 2.6)
	var core_mat := ShaderMaterial.new()
	core_mat.shader = plume_shader
	core_mat.set_shader_parameter("core", 1.0)
	core_mat.set_shader_parameter("intensity", 6.0)
	var plume := Node3D.new()
	plume.name = "PlumeIllustrative"
	body.add_child(plume)
	var outer := MeshInstance3D.new()
	outer.mesh = cone.call(2.3)
	outer.material_override = outer_mat
	outer.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	plume.add_child(outer)
	var core := MeshInstance3D.new()
	core.mesh = cone.call(1.15)
	core.material_override = core_mat
	core.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	plume.add_child(core)
	# Nozzle glow (illustration): a camera-facing disc, visible whenever the engine is on.
	var gi := Image.create(128, 128, true, Image.FORMAT_RGBA8)
	for yy in 128:
		for xx in 128:
			var rr := Vector2(xx - 63.5, yy - 63.5).length() / 64.0
			var a := clampf(1.0 - rr, 0.0, 1.0)
			gi.set_pixel(xx, yy, Color(1.0, 0.82, 0.6, a * a))
	gi.generate_mipmaps()
	var gm := StandardMaterial3D.new()
	gm.albedo_texture = ImageTexture.create_from_image(gi)
	gm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	gm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	gm.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	gm.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	gm.albedo_color = Color(1.3, 1.0, 0.75)
	var gq := QuadMesh.new()
	gq.size = Vector2(8, 8)
	var glow := MeshInstance3D.new()
	glow.mesh = gq
	glow.material_override = gm
	glow.position = Vector3(0, 0.3, 0)
	glow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	plume.add_child(glow)
	var light := OmniLight3D.new()
	light.light_color = Color(1.0, 0.7, 0.4)
	light.omni_range = 120.0
	light.omni_attenuation = 1.6
	light.position = Vector3(0, -6, 0)
	light.shadow_enabled = false
	# The plume light must not light the volumetric fog (it made a glowing ball in the haze).
	light.light_volumetric_fog_energy = 0.0
	body.add_child(light)
	return {"body": body, "plume": plume, "outer": outer, "core": core, "light": light, "materials": [outer_mat, core_mat]}


# Plume length in metres (0 hides it), logical time for its turbulence.
static func set_plume(s: Dictionary, length: float, logical_t: float, clear_m := INF) -> void:
	var on := length > 0.0
	s["plume"].visible = on
	s["light"].visible = on
	if not on:
		return
	# Cylinder meshes are centred: shift so they run from y = 0 to y = -length.
	# The axial flame stops at the ground (it would otherwise be drawn inside the terrain).
	var shown := clampf(minf(length, clear_m + 1.0), 0.5, length)
	s["outer"].scale = Vector3(1, shown, 1)
	s["outer"].position = Vector3(0, -shown / 2.0, 0)
	var cl := minf(maxf(3.0, length * 0.32), shown)
	s["core"].scale = Vector3(1, cl, 1)
	s["core"].position = Vector3(0, -cl / 2.0, 0)
	s["light"].light_energy = 6.0 * minf(1.0, length / 28.0)
	for m in s["materials"]:
		m.set_shader_parameter("logical_t", logical_t)
