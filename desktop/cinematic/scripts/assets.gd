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
