# Image-based sky: a CC0 HDRI panorama (assets/cc0/hdri) shown by shaders/sky.gdshader, which is also
# the radiance the engine lights and reflects with. Of the three staged HDRIs only spiaggia_di_mondello has
# its sun near the scene's (elevation 25.3 degrees against 27); the other two have it at 74 degrees and
# would light the scene twice, so they are not shipped. The panorama is only turned about the vertical axis,
# so that its sun sits at the scene sun's azimuth.
extends RefCounted

const Assets := preload("res://scripts/assets.gd")

# Position of the sun in each panorama (u, v of the equirectangular image), measured by
# tools/hdri_probe.gd (centroid of the pixels above half the peak).
const SUN_UV := {"spiaggia_di_mondello": Vector2(0.60088473, 0.35945242)}


# Loads panorama `id` into `mat` (a ShaderMaterial of sky.gdshader). `sun_dir` is the scene sun's
# direction in the drawn frame. Returns false (the procedural sky stays) if the file cannot be read.
static func apply(mat: ShaderMaterial, id: String, sun_dir: Vector3, max_side := 4096) -> bool:
	if not SUN_UV.has(id):
		return false
	var img := Image.new()
	if img.load(Assets.DIR + "cc0/hdri/%s/%s_4k.hdr" % [id, id]) != OK:
		printerr("cinematic: cannot read the HDRI %s" % id)
		return false
	if img.get_width() > max_side:
		img.resize(max_side, max_side / 2, Image.INTERPOLATE_BILINEAR)
	img.convert(Image.FORMAT_RGBE9995)
	var target_u := atan2(sun_dir.x, -sun_dir.z) / TAU + 0.5
	# The haze band: the mean colour of the sky at 25 to 40 degrees of elevation away from the sun (the
	# sun's side and its halo are left out), lightened a little towards white.
	var sum := Color(0, 0, 0)
	var n := 0
	var w := img.get_width()
	var h := img.get_height()
	for k in 48:
		var u := float(k) / 48.0
		if absf(fposmod(u - SUN_UV[id].x + 0.5, 1.0) - 0.5) < 0.22:
			continue
		for e in [25.0, 30.0, 35.0, 40.0]:
			var v: float = (90.0 - float(e)) / 180.0
			var c: Color = img.get_pixel(int(u * w) % w, int(v * h))
			sum += Color(minf(c.r, 4.0), minf(c.g, 4.0), minf(c.b, 4.0))
			n += 1
	var band := Color(sum.r / n, sum.g / n, sum.b / n).lerp(Color(1.1, 1.1, 1.1), 0.3)
	mat.set_shader_parameter("hdri_band", Vector3(band.r, band.g, band.b))
	mat.set_shader_parameter("hdri", ImageTexture.create_from_image(img))
	mat.set_shader_parameter("use_hdri", true)
	mat.set_shader_parameter("hdri_yaw", SUN_UV[id].x - target_u)
	return true
