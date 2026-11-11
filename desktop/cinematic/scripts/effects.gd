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


static func build(parent: Node3D, sun_world: Vector3) -> Dictionary:
	var fx := {}
	var light := OmniLight3D.new()
	light.light_color = Color(1.0, 0.66, 0.38)
	light.omni_range = 140.0
	light.omni_attenuation = 1.6
	light.light_volumetric_fog_energy = 0.0
	parent.add_child(light)
	fx["light"] = light
	# Dust volume: a box of half-height DUST_HH (in box units), bottom on the ground.
	var hh := 0.24
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
	parent.add_child(dust)
	fx["dust"] = dust
	fx["dust_mat"] = dm
	fx["dust_hh"] = hh
	# Ground glow.
	var gm := ShaderMaterial.new()
	gm.shader = load("res://shaders/ground_glow.gdshader")
	var q := QuadMesh.new()
	q.size = Vector2(2, 2)
	q.orientation = PlaneMesh.FACE_Y
	var glow := MeshInstance3D.new()
	glow.mesh = q
	glow.material_override = gm
	glow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(glow)
	fx["glow"] = glow
	fx["glow_mat"] = gm
	# Contact shadow.
	var decal := Decal.new()
	decal.texture_albedo = _radial_texture(true)
	decal.size = Vector3(16, 8, 16)
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
	light.visible = on
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
		fx["glow_mat"].set_shader_parameter("strength", 0.35 + 0.65 * ks)
	if not on:
		return
	var k := (1.0 - maxf(0.0, h) / REACH) * minf(1.0, plume_len / 28.0)
	var rd := 12.0 + 58.0 * k
	var hh: float = fx["dust_hh"]
	var gp: Vector3 = to_godot.call(Vector3(p.x, p.y, gz))
	dust.position = gp + Vector3(0, hh * rd, 0)
	dust.scale = Vector3(rd, rd, rd)
	var dm: ShaderMaterial = fx["dust_mat"]
	dm.set_shader_parameter("logical_t", logical_t)
	dm.set_shader_parameter("strength", clampf(k * 1.7, 0.0, 1.0) * (0.45 + 0.55 * throttle))
	dm.set_shader_parameter("heat", k)
	light.position = to_godot.call(Vector3(p.x, p.y, gz + maxf(2.0, minf(h, 30.0) * 0.4)))
	light.light_energy = 14.0 * k
