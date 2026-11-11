# Headless probe: godot --headless --path <project> -s res://tools/hdri_probe.gd -- <file.hdr>
# Prints the load time, the peak pixel and the direction of the sun (the brightest pixel, equirectangular).
extends SceneTree


func _initialize() -> void:
	var path := OS.get_cmdline_user_args()[0]
	var t0 := Time.get_ticks_msec()
	var img := Image.new()
	var err := img.load(path)
	var t1 := Time.get_ticks_msec()
	if err != OK:
		print("HDRI error ", err)
		quit(1)
		return
	var w := img.get_width()
	var h := img.get_height()
	var best := 0.0
	var bx := 0
	var by := 0
	var sum := 0.0
	var n := 0
	for y in range(0, h, 2):
		for x in range(0, w, 2):
			var c := img.get_pixel(x, y)
			var l := 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b
			if l > best:
				best = l
				bx = x
				by = y
			if y < h / 2:
				sum += l
				n += 1
	# Refine around the peak with a weighted centroid of the pixels above 50 % of it.
	var cx := 0.0
	var cy := 0.0
	var cw := 0.0
	for y in range(maxi(by - 40, 0), mini(by + 40, h)):
		for x in range(maxi(bx - 40, 0), mini(bx + 40, w)):
			var c2 := img.get_pixel(x, y)
			var l2 := 0.2126 * c2.r + 0.7152 * c2.g + 0.0722 * c2.b
			if l2 > 0.5 * best:
				cx += x * l2
				cy += y * l2
				cw += l2
	var u := cx / cw / w
	var v := cy / cw / h
	print("HDRI ", path.get_file(), " ", JSON.stringify({"w": w, "h": h, "format": img.get_format(), "load_ms": t1 - t0, "peak": best, "sun_u": u, "sun_v": v, "sun_elevation_deg": 90.0 - v * 180.0, "sun_azimuth_from_u_deg": (u - 0.5) * 360.0, "mean_upper_luminance": sum / n}))
	quit(0)
