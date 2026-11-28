extends SceneTree
## Test harness for desktop/cinematic/scripts/guard.gd: reads a JSON list of cases from the first user
## argument, calls the guard's pure decision for each and prints the results as one JSON line.
## Run headless through godot_launch only (tests/test_cinematic_guard.py).


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var cases = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var guard = load("res://scripts/guard.gd")
	var out := []
	for c in cases:
		out.append(guard.decide(c["name"], c["token"], c["nonce"], c["user"]))
	print("GUARD_RESULTS=" + JSON.stringify(out))
	quit()
