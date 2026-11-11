# Graphics profiles. A profile only changes how the scene is drawn (shadow resolution, screen-space
# effects, sampling, vegetation density and distances), never what is drawn where: poses, terrain
# and the world layer's positions are the same in every profile.
#
# Automatic choice: Godot 4.7 does not report the capacity of the video memory (on this machine
# RenderingDevice.get_device_total_memory() returned 0), so the capacity comes from --vram-bytes
# (Studio reads the display adapter's HardwareInformation.qwMemorySize from the registry), else from
# that registry value read here with reg.exe and fixed arguments, else it is unknown and Balanced is
# used with a visible note. While running, if the video memory in use passes 85 % of the capacity,
# the profile steps down one level instead of failing.
extends RefCounted

const ORDER := ["performance", "balanced", "high", "ultra"]

const TABLE := {
	"performance": {"dof": false, "shadow_size": 2048, "cascades": 2, "soft_shadows": false, "ssao": false, "ssil": false, "volumetric_fog": false, "ssr": false, "render_scale": 0.75, "aa": "fxaa", "msaa": 0, "vegetation_density": 0.35, "lod_near_m": 350.0, "lod_far_m": 1500.0, "foliage_cards": false, "vegetation_shadows": false, "glow": true, "min_vram_gb": 2.0},
	"balanced": {"dof": true, "shadow_size": 4096, "cascades": 3, "soft_shadows": true, "ssao": true, "ssil": false, "volumetric_fog": false, "ssr": false, "render_scale": 1.0, "aa": "taa", "msaa": 0, "vegetation_density": 0.6, "lod_near_m": 500.0, "lod_far_m": 2400.0, "foliage_cards": true, "vegetation_shadows": false, "glow": true, "min_vram_gb": 4.0},
	"high": {"dof": true, "shadow_size": 4096, "cascades": 4, "soft_shadows": true, "ssao": true, "ssil": true, "volumetric_fog": true, "ssr": true, "render_scale": 1.0, "aa": "taa", "msaa": 2, "vegetation_density": 1.0, "lod_near_m": 700.0, "lod_far_m": 3200.0, "foliage_cards": true, "vegetation_shadows": true, "glow": true, "min_vram_gb": 8.0},
	"ultra": {"dof": true, "shadow_size": 8192, "cascades": 4, "soft_shadows": true, "ssao": true, "ssil": true, "volumetric_fog": true, "ssr": true, "render_scale": 1.0, "aa": "fsr2", "msaa": 4, "vegetation_density": 1.0, "lod_near_m": 1000.0, "lod_far_m": 4500.0, "foliage_cards": true, "vegetation_shadows": true, "glow": true, "min_vram_gb": 11.0},
}

const DISPLAY_CLASS := "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}"


# Video memory capacity in bytes and where it came from: {bytes, source}. bytes is -1 if unknown.
static func detect_vram(cli_bytes: int) -> Dictionary:
	if cli_bytes > 0:
		return {"bytes": cli_bytes, "source": "--vram-bytes"}
	var rd := RenderingServer.get_rendering_device()
	if rd != null and rd.get_device_total_memory() > 0:
		return {"bytes": rd.get_device_total_memory(), "source": "RenderingDevice"}
	if OS.get_name() == "Windows":
		var out := []
		# The system's own reg.exe by absolute path: a bare name could be shadowed by a file planted
		# next to the executable or in the working directory.
		var root := OS.get_environment("SystemRoot")
		var reg := root.path_join("System32/reg.exe") if root.is_absolute_path() else ""
		var code := OS.execute(reg, ["query", DISPLAY_CLASS, "/s", "/v", "HardwareInformation.qwMemorySize"], out, true)
		if code == 0 and out.size() > 0:
			var best := -1
			for line in str(out[0]).split("\n"):
				var parts := line.strip_edges().split(" ", false)
				if parts.size() >= 3 and parts[0] == "HardwareInformation.qwMemorySize" and parts[1] == "REG_QWORD":
					var v := parts[2].hex_to_int()
					best = maxi(best, v)
			if best > 0:
				return {"bytes": best, "source": "registry qwMemorySize"}
	return {"bytes": -1, "source": "unknown"}


static func auto_pick(vram: Dictionary) -> Dictionary:
	if RenderingServer.get_video_adapter_type() == RenderingDevice.DEVICE_TYPE_INTEGRATED_GPU:
		return {"profile": "performance", "reason": "integrated graphics adapter"}
	var b: int = vram["bytes"]
	if b <= 0:
		return {"profile": "balanced", "reason": "video memory capacity unknown: Balanced chosen, override with the profile menu"}
	var gb := b / 1.0e9
	var pick := "performance"
	for p in ORDER:
		if gb >= TABLE[p]["min_vram_gb"]:
			pick = p
	return {"profile": pick, "reason": "%.1f GB of video memory (%s)" % [gb, vram["source"]]}


# Settings of `name`; "custom" starts from Balanced and applies `custom` (key=value strings).
static func settings(name: String, custom: Dictionary) -> Dictionary:
	var base: Dictionary = (TABLE["balanced"] if name == "custom" else TABLE[name]).duplicate()
	if name == "custom":
		for k in custom:
			if not base.has(k):
				continue
			var v: String = custom[k]
			match typeof(base[k]):
				TYPE_BOOL:
					base[k] = v in ["1", "true", "on", "yes"]
				TYPE_INT:
					base[k] = v.to_int()
				TYPE_FLOAT:
					base[k] = v.to_float()
				_:
					base[k] = v
		base["shadow_size"] = clampi(base["shadow_size"], 1024, 8192)
		base["cascades"] = clampi(base["cascades"], 1, 4)
		base["render_scale"] = clampf(base["render_scale"], 0.5, 1.5)
		base["vegetation_density"] = clampf(base["vegetation_density"], 0.0, 1.0)
		base["lod_near_m"] = clampf(base["lod_near_m"], 50.0, 5000.0)
		base["lod_far_m"] = clampf(base["lod_far_m"], base["lod_near_m"], 10000.0)
		base["msaa"] = [0, 2, 4, 8][clampi([0, 2, 4, 8].find(int(base["msaa"])), 0, 3)]
	base["name"] = name
	return base


static func step_down(name: String) -> String:
	var i := ORDER.find(name)
	return ORDER[maxi(0, i - 1)] if i > 0 else "performance"


# Applies the drawing settings to the viewport, the environment and the sun.
static func apply(s: Dictionary, vp: Viewport, env: Environment, sun: DirectionalLight3D) -> void:
	RenderingServer.camera_attributes_set_dof_blur_quality(RenderingServer.DOF_BLUR_QUALITY_HIGH if str(s["name"]) == "ultra" else RenderingServer.DOF_BLUR_QUALITY_MEDIUM, false)
	RenderingServer.directional_shadow_atlas_set_size(int(s["shadow_size"]), true)
	RenderingServer.directional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_SOFT_HIGH if s["soft_shadows"] else RenderingServer.SHADOW_QUALITY_SOFT_LOW)
	var modes := [DirectionalLight3D.SHADOW_ORTHOGONAL, DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS, DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS, DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS]
	sun.directional_shadow_mode = modes[clampi(int(s["cascades"]) - 1, 0, 3)]
	# Angular size of the sun disc: with soft shadows on, penumbrae widen with distance (PCSS).
	sun.light_angular_distance = 0.53 if s["soft_shadows"] else 0.0
	env.ssao_enabled = s["ssao"]
	env.ssil_enabled = s["ssil"]
	env.ssr_enabled = s["ssr"]
	env.volumetric_fog_enabled = s["volumetric_fog"]
	env.glow_enabled = s["glow"]
	vp.scaling_3d_scale = float(s["render_scale"])
	vp.use_taa = false
	vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_DISABLED
	vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
	match str(s["aa"]):
		"taa":
			vp.use_taa = true
		"fsr2":
			vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_FSR2
		"fxaa":
			vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_FXAA
			if float(s["render_scale"]) < 1.0:
				vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_FSR
	var ms := {0: Viewport.MSAA_DISABLED, 2: Viewport.MSAA_2X, 4: Viewport.MSAA_4X, 8: Viewport.MSAA_8X}
	vp.msaa_3d = ms.get(int(s["msaa"]), Viewport.MSAA_DISABLED)
