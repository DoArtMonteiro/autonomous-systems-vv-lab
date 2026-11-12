# Headless probe: builds the stage under a vehicle node exactly as main.gd does and prints the
# bounding box of its solid meshes (the plume is excluded) in the vehicle's local frame.
# godot --headless --path <project> -s res://tools/stage_probe.gd
extends SceneTree


func _initialize() -> void:
	var Stage = load("res://scripts/stage.gd")
	var vehicle := Node3D.new()
	root.add_child(vehicle)
	var s: Dictionary = Stage.build(vehicle)
	var lo := Vector3(INF, INF, INF)
	var hi := Vector3(-INF, -INF, -INF)
	var n_mesh := 0
	for n in vehicle.find_children("*", "MeshInstance3D", true, false):
		if n.get_parent().name.begins_with("Plume"):
			continue
		n_mesh += 1
		var box: AABB = n.mesh.get_aabb()
		# Transform of the mesh node in the vehicle's frame, from the local transforms (independent of
		# when the tree propagates global transforms).
		var rel := Transform3D()
		var c: Node = n
		while c != vehicle:
			rel = c.transform * rel
			c = c.get_parent()
		for i in 8:
			var p: Vector3 = rel * box.get_endpoint(i)
			lo = lo.min(p)
			hi = hi.max(p)
	print("STAGE ", JSON.stringify({"meshes": n_mesh, "model": s["model"] != null, "min": [lo.x, lo.y, lo.z], "max": [hi.x, hi.y, hi.z]}))
	quit(0)
