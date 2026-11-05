# Writes the licence texts compiled into the running Godot binary, for the module's notices:
#   godot --headless --path desktop/cinematic -s res://tools/licence_dump.gd -- <out dir>
# Output: godot-LICENSE.txt (Engine.get_license_text) and godot-COPYRIGHT.txt (third-party components
# from Engine.get_copyright_info, with the licence texts from Engine.get_license_info).
extends SceneTree


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1:
		printerr("usage: -- <out dir>")
		quit(2)
		return
	var out := args[0]
	DirAccess.make_dir_recursive_absolute(out)
	var f := FileAccess.open(out.path_join("godot-LICENSE.txt"), FileAccess.WRITE)
	f.store_string("Godot Engine %s\n\n%s\n" % [Engine.get_version_info()["string"], Engine.get_license_text()])
	f.close()
	var c := FileAccess.open(out.path_join("godot-COPYRIGHT.txt"), FileAccess.WRITE)
	c.store_string("Third-party components of the Godot Engine binary, as reported by Engine.get_copyright_info().\n\n")
	for comp in Engine.get_copyright_info():
		c.store_string("Component: %s\n" % comp["name"])
		for part in comp["parts"]:
			c.store_string("  Files: %s\n  Copyright: %s\n  Licence: %s\n" % [", ".join(part["files"]), "; ".join(part["copyright"]), part["license"]])
		c.store_string("\n")
	var info := Engine.get_license_info()
	for k in info:
		c.store_string("----- Licence: %s -----\n%s\n\n" % [k, info[k]])
	c.close()
	print("licences written to ", out)
	quit(0)
