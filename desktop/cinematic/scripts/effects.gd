# Effects where the exhaust meets the ground, all drawn from recorded values only: the nozzle's
# height above the drawn terrain, the applied throttle and the record time. Stateless (shaders of
# `logical_t`, no particles), so a frame at a given t is always the same.
#   - dust and debris cloud (ray-marched volume, shaders/dust.gdshader)
#   - exhaust glow spreading over the ground (shaders/ground_glow.gdshader)
#   - warm light on the ground
#   - contact shadow under the stage (a projected soft shadow; the sun shadow is separate)
extends RefCounted

const REACH := 70.0   # nozzle height (m) below which the ground effects begin


static func _radial_texture(dark: bool) -> ImageTexture:
	var img := Image.create(128, 128, true, Image.FORMAT_RGBA8)
	for y in 128:
		for x in 128:
			var r := Vector2(x - 63.5, y - 63.5).length() / 64.0
			var a := pow(clampf(1.0 - r, 0.0, 1.0), 1.6)
			img.set_pixel(x, y, Color(0.0, 0.0, 0.0, a) if dark else Color(1, 1, 1, a))
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


# Flared skirt: from the engines (radius 0.16, height 1) out to the ground ring (radius 1, height 0),
# unit scale; UV.x around, UV.y = 0 at the engines and 1 on the ground ring.
static func _skirt_mesh(rings: int, segs: int) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for i in rings:
		for s in segs:
			var q := []
			for dv in [[0, 0], [1, 0], [1, 1], [0, 1]]:
				var t: float = float(i + int(dv[1])) / rings
				var a: float = TAU * float(s + int(dv[0])) / segs
				var r := 0.16 + 0.84 * pow(t, 1.3)
				q.append([Vector3(r * cos(a), pow(1.0 - t, 1.4), r * sin(a)), Vector2(float(s + int(dv[0])) / segs, t)])
			for k in [0, 1, 2, 0, 2, 3]:
				st.set_uv(q[k][1])
				st.add_vertex(q[k][0])
	st.generate_normals()
	return st.commit()


static func build(parent: Node3D, sun_world: Vector3) -> Dictionary:
	var fx := {}
	var light := OmniLight3D.new()
	light.light_color = Color(1.0, 0.66, 0.38)
	light.omni_range = 110.0
	light.omni_attenuation = 1.3
	# Throttle-driven exhaust light with shadows: the stage's feet, the pad props and the dust throw
	# and receive them. It does not light the volumetric fog (it made a glowing ball in the haze).
	light.shadow_enabled = true
	light.shadow_bias = 0.05
	light.light_volumetric_fog_energy = 0.0
	parent.add_child(light)
	fx["light"] = light
	# Dust volume: a box of half-height DUST_HH (in box units), bottom on the ground.
	var hh := 0.17
	var dm := ShaderMaterial.new()
	dm.shader = load("res://shaders/dust.gdshader")
	dm.set_shader_parameter("sun_dir", sun_world)
	dm.set_shader_parameter("half_height", hh)
	var bm := BoxMesh.new()
	bm.size = Vector3(2.0, 2.0 * hh, 2.0)
	var dust := MeshInstance3D.new()
	dust.mesh = bm
	dust.material_override = dm
	dust.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	dust.extra_cull_margin = 500.0
	dust.layers = 2   # decals (layer 1 only) would paint the pad texture over the effect
	parent.add_child(dust)
	fx["dust"] = dust
	fx["dust_mat"] = dm
	fx["dust_hh"] = hh
	# Ground glow.
	var gm := ShaderMaterial.new()
	gm.shader = load("res://shaders/ground_glow.gdshader")
	gm.render_priority = 4
	var q := QuadMesh.new()
	q.size = Vector2(2, 2)
	q.orientation = PlaneMesh.FACE_Y
	var glow := MeshInstance3D.new()
	glow.mesh = q
	glow.material_override = gm
	glow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	glow.layers = 2
	parent.add_child(glow)
	fx["glow"] = glow
	fx["glow_mat"] = gm
	# Flared flame skirt around the stage's foot (unit mesh, scaled to the spread).
	# Three nested shells (outer orange, middle yellow, white-hot core), each with its own noise: hot gas
	# spreading over the ground in layers, not one flat ring.
	var flame := Node3D.new()
	parent.add_child(flame)
	var skirt := _skirt_mesh(16, 56)
	var mats := []
	var layers := [
		[1.0, Color(0.95, 0.30, 0.06), Color(1.0, 0.72, 0.32), 0.75, 0.0, 5],
		[0.66, Color(1.0, 0.52, 0.12), Color(1.0, 0.86, 0.5), 0.85, 3.1, 6],
		[0.34, Color(1.0, 0.78, 0.36), Color(1.0, 0.97, 0.82), 1.0, 7.7, 7],
	]
	for L in layers:
		var fm := ShaderMaterial.new()
		fm.shader = load("res://shaders/ground_flame.gdshader")
		fm.render_priority = L[5]   # after the dust volume: fire in front of the dust it lights
		fm.set_shader_parameter("warm", L[1])
		fm.set_shader_parameter("hot", L[2])
		fm.set_shader_parameter("alpha_k", L[3])
		fm.set_shader_parameter("seed", L[4])
		var mi := MeshInstance3D.new()
		mi.mesh = skirt
		mi.material_override = fm
		mi.scale = Vector3(L[0], 0.55 + 0.45 * L[0], L[0])
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mi.extra_cull_margin = 100.0
		mi.layers = 2
		flame.add_child(mi)
		mats.append(fm)
	fx["flame"] = flame
	fx["flame_mats"] = mats
	# Contact shadow.
	var decal := Decal.new()
	decal.texture_albedo = _radial_texture(true)
	decal.size = Vector3(16, 8, 16)
	decal.cull_mask = 1   # the terrain and world layer only: the stage and the pad props are on layer 2
	decal.upper_fade = 0.3
	decal.lower_fade = 0.3
	parent.add_child(decal)
	fx["contact"] = decal
	return fx


# p: nozzle position (ENU), gz: drawn ground height under it, len: plume length (0 = engine off).
static func update(fx: Dictionary, p: Vector3, gz: float, plume_len: float, throttle: float, logical_t: float, to_godot: Callable) -> void:
	var h := p.z - gz
	var on: bool = plume_len > 0.0 and h < REACH
	var light: OmniLight3D = fx["light"]
	var dust: MeshInstance3D = fx["dust"]
	var glow: MeshInstance3D = fx["glow"]
	var contact: Decal = fx["contact"]
	var flame: Node3D = fx["flame"]
	light.visible = on
	flame.visible = plume_len > 0.0 and h < 0.6 * plume_len + 2.0
	dust.visible = on
	glow.visible = plume_len > 0.0 and h < plume_len
	# Contact shadow: present whenever the stage is within 90 m of the ground, strongest at touchdown.
	var ck := clampf(1.0 - maxf(0.0, h) / 90.0, 0.0, 1.0)
	contact.visible = ck > 0.02
	if contact.visible:
		contact.position = to_godot.call(Vector3(p.x, p.y, gz + 3.0))
		var cs := 12.0 + 18.0 * (1.0 - ck)
		contact.size = Vector3(cs, 10.0, cs)
		contact.modulate = Color(1, 1, 1, 0.7 * ck)
	if glow.visible:
		var ks := clampf(1.0 - maxf(0.0, h) / plume_len, 0.0, 1.0)
		var rs := 6.0 + 15.0 * ks
		glow.position = to_godot.call(Vector3(p.x, p.y, gz + 0.3))
		glow.scale = Vector3(rs, 1.0, rs)
		fx["glow_mat"].set_shader_parameter("logical_t", logical_t)
		fx["glow_mat"].set_shader_parameter("strength", (0.35 + 0.65 * ks) * 0.5)
	if flame.visible:
		var kf := clampf(1.0 - maxf(0.0, h) / (0.6 * plume_len + 2.0), 0.0, 1.0)
		var rf := 4.5 + 7.0 * kf
		flame.position = to_godot.call(Vector3(p.x, p.y, gz + 0.05))
		flame.scale = Vector3(rf, (1.8 + 2.2 * throttle) * (0.4 + 0.6 * kf), rf)
		for fm in fx["flame_mats"]:
			fm.set_shader_parameter("logical_t", logical_t)
			fm.set_shader_parameter("strength", (0.5 + 0.9 * kf) * (0.5 + 0.5 * throttle))
	if not on:
		return
	var k := (1.0 - maxf(0.0, h) / REACH) * minf(1.0, plume_len / 28.0)
	var rd := 12.0 + 40.0 * k
	var hh: float = fx["dust_hh"]
	var gp: Vector3 = to_godot.call(Vector3(p.x, p.y, gz))
	dust.position = gp + Vector3(0, hh * rd, 0)
	dust.scale = Vector3(rd, rd, rd)
	var dm: ShaderMaterial = fx["dust_mat"]
	dm.set_shader_parameter("logical_t", logical_t)
	dm.set_shader_parameter("strength", clampf(k * 1.5, 0.0, 1.0) * (0.45 + 0.55 * throttle))
	dm.set_shader_parameter("heat", k)
	light.position = to_godot.call(Vector3(p.x, p.y, gz + maxf(2.5, minf(h, 30.0) * 0.4)))
	light.light_energy = 60.0 * k * (0.4 + 0.6 * throttle)
