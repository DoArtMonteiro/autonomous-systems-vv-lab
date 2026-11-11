# Runtime loading of the module's own authored assets (assets/*.glb, assets/*.png). The module ships
# raw files and no import cache (*.import is stripped when packaging), so nothing here uses load()
# on an asset: glTF binaries go through GLTFDocument and images through Image.load.
extends RefCounted

const DIR := "res://assets/"


# Scene root of assets/<name>.glb, or null (with an error printed) if it cannot be read.
static func load_glb(name: String) -> Node3D:
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	var err := doc.append_from_file(DIR + name, state)
	if err != OK:
		printerr("cinematic: cannot read asset %s (error %d)" % [name, err])
		return null
	var root = doc.generate_scene(state)
	return root if root is Node3D else null


# Image of assets/<name> (PNG or JPEG), with mipmaps, or null.
static func load_image(name: String, mipmaps := true) -> Image:
	var img := Image.new()
	var err := img.load(DIR + name)
	if err != OK:
		printerr("cinematic: cannot read image %s (error %d)" % [name, err])
		return null
	if mipmaps:
		img.generate_mipmaps()
	return img


# Image of any file under assets/ (relative path, e.g. "cc0/ground/Ground003/Ground003_albedo.jpg"),
# at most `max_side` pixels on its longer side, as RGB8 with mipmaps; null if it cannot be read.
static func load_rgb(rel: String, max_side := 2048, normal := false) -> Image:
	var img := Image.new()
	var err := img.load(DIR + rel)
	if err != OK:
		printerr("cinematic: cannot read image %s (error %d)" % [rel, err])
		return null
	if img.get_format() != Image.FORMAT_RGB8:
		img.convert(Image.FORMAT_RGB8)
	var m := maxi(img.get_width(), img.get_height())
	if m > max_side:
		var k := float(max_side) / m
		img.resize(maxi(1, int(img.get_width() * k)), maxi(1, int(img.get_height() * k)), Image.INTERPOLATE_LANCZOS)
	img.generate_mipmaps(normal)
	return img


# A texture array of equally sized RGB8 images (scans resized to one side length); null on failure.
static func texture_array(rels: Array, max_side: int, normal := false) -> Texture2DArray:
	var imgs: Array[Image] = []
	for r in rels:
		var im := load_rgb(r, max_side, normal)
		if im == null:
			return null
		if not imgs.is_empty() and (im.get_width() != imgs[0].get_width() or im.get_height() != imgs[0].get_height()):
			im.resize(imgs[0].get_width(), imgs[0].get_height(), Image.INTERPOLATE_LANCZOS)
			im.generate_mipmaps(normal)
		imgs.append(im)
	var arr := Texture2DArray.new()
	if arr.create_from_images(imgs) != OK:
		printerr("cinematic: cannot build a texture array")
		return null
	return arr
