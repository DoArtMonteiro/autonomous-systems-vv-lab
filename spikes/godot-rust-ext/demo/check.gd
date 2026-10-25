extends Node
# Spike check: the Rust class TraceSource must return exactly the positions GDScript parses from the same file.
# Usage: godot --headless --path spikes/godot-rust-ext/demo -- <path to spikes/out/trace.json>

func _ready() -> void:
	var path: String = OS.get_cmdline_user_args()[0]
	if not ClassDB.class_exists("TraceSource"):
		print("SPIKE gdext_loaded=false")
		get_tree().quit(3)
		return
	var t0 := Time.get_ticks_usec()
	var from_rust: PackedVector2Array = ClassDB.instantiate("TraceSource").load_positions(path)
	var rust_us := Time.get_ticks_usec() - t0
	var trace: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	var mismatches := 0
	for i in trace["states"].size():
		var s: Dictionary = trace["states"][i]
		if i >= from_rust.size() or from_rust[i] != Vector2(s["x_mm"], s["y_mm"]):
			mismatches += 1
	print("SPIKE gdext_loaded=true positions=%d mismatches=%d rust_load_us=%d" % [from_rust.size(), mismatches, rust_us])
	get_tree().quit(0 if mismatches == 0 and from_rust.size() == trace["states"].size() else 4)
