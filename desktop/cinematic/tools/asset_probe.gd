# Headless probe: godot --headless --path <project> -s res://tools/asset_probe.gd -- <name.glb>
extends SceneTree

func _init() -> void:
	var Assets = load("res://scripts/assets.gd")
	var args := OS.get_cmdline_user_args()
	var root: Node3D = Assets.load_glb(args[0])
	if root == null:
		quit(1)
		return
	var lines := []
	for n in root.find_children("*", "", true, false):
		var d := {"name": n.name, "class": n.get_class()}
		if n is MeshInstance3D:
			var aabb: AABB = n.mesh.get_aabb()
			d["aabb"] = [aabb.position, aabb.end]
			var m = n.mesh.surface_get_material(0)
			if m is BaseMaterial3D:
				d["albedo_tex"] = m.albedo_texture != null
				if m.albedo_texture:
					d["tex_size"] = m.albedo_texture.get_size()
					d["mips"] = m.albedo_texture.get_image().has_mipmaps()
		lines.append(d)
	print("PROBE ", JSON.stringify(lines))
	quit(0)
