# The landing pad, an illustration around the record's pad centre: a concrete slab with joints,
# cracks, exhaust staining and painted marks (a decal projected onto the drawn terrain, textures
# authored in assets-src/build_pad.py), a ring of flush edge lights, four floodlight masts and four
# markers. The record's rings (R5 landing radius, S2 keep-out) are data and drawn separately.
extends RefCounted

const Assets := preload("res://scripts/assets.gd")

const EXTENT := 80.0


static func _tex(name: String) -> ImageTexture:
	var img = Assets.load_image(name, true)
	return ImageTexture.create_from_image(img) if img != null else null


static func build(parent: Node3D, pack, cx: float, cy: float) -> Node3D:
	var root := Node3D.new()
	root.name = "PadIllustrative"
	parent.add_child(root)
	var lo := INF
	var hi := -INF
	for dx in [-36.0, -18.0, 0.0, 18.0, 36.0]:
		for dy in [-36.0, -18.0, 0.0, 18.0, 36.0]:
			var gz: float = pack.ground(cx + dx, cy + dy)
			lo = minf(lo, gz)
			hi = maxf(hi, gz)
	var decal := Decal.new()
	decal.name = "PadSlab"
	decal.texture_albedo = _tex("pad_albedo.png")
	decal.texture_normal = _tex("pad_normal.png")
	decal.texture_orm = _tex("pad_orm.png")
	decal.size = Vector3(EXTENT, (hi - lo) + 10.0, EXTENT)
	decal.position = Vector3(cx, (hi + lo) / 2.0, -cy)
	decal.upper_fade = 0.1
	decal.lower_fade = 0.1
	decal.normal_fade = 0.3
	root.add_child(decal)
	var props := Assets.load_glb("pad_props.glb")
	if props == null:
		return root
	var mast: Node3D = props.get_node_or_null("Mast")
	var edge: Node3D = props.get_node_or_null("EdgeLight")
	var marker: Node3D = props.get_node_or_null("Marker")
	var lamp := StandardMaterial3D.new()
	lamp.albedo_color = Color(0.55, 0.52, 0.46)
	lamp.emission_enabled = true
	lamp.emission = Color(1.0, 0.85, 0.6)
	lamp.emission_energy_multiplier = 1.4
	var place := func(src: Node3D, x: float, y: float, yaw: float) -> void:
		if src == null:
			return
		var n: Node3D = src.duplicate()
		n.position = Vector3(x, pack.ground(x, y), -y)
		n.rotation.y = yaw
		root.add_child(n)
	for k in 24:
		var a := TAU * k / 24.0
		place.call(edge, cx + 35.0 * cos(a), cy + 35.0 * sin(a), a)
	for k in 4:
		# Masts and markers keep clear of the closeup camera's line of sight (bearing 38 degrees).
		var a := deg_to_rad(100.0) + k * PI / 2.0
		place.call(mast, cx + 46.0 * cos(a), cy + 46.0 * sin(a), -a)
		place.call(marker, cx + 47.0 * cos(a + PI / 4.0), cy + 47.0 * sin(a + PI / 4.0), -a)
	# Lamp heads and edge lights glow (emission authored here: the glTF files carry no light data).
	for n in root.find_children("*", "MeshInstance3D", true, false):
		var m = n.mesh.surface_get_material(n.mesh.get_surface_count() - 1) if n.mesh != null else null
		if m is BaseMaterial3D and m.resource_name == "Lamp":
			n.set_surface_override_material(n.mesh.get_surface_count() - 1, lamp)
	return root
