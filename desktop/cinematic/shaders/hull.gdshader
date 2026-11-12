// Skin of the illustrative stage: scanned PBR metal (CC0, assets/cc0/hull: Metal016 white painted
// metal for the body, Metal027 black paint for the interstage and top, Metal046B dirty metal for the
// engine section) tiled over the Blender-authored UVs, modulated by the baked skin texture (panel
// tone, welds, drips, a soot gradient rising from the engines, occlusion beside legs and fins). The
// exhaust lights the lower hull with the recorded throttle and the nozzle's height (`hot`).
shader_type spatial;

uniform sampler2D mod_alb : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D mod_orm : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D mod_nrm : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray hull_alb : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray hull_nrm : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray hull_rgh : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray hull_met : filter_linear_mipmap_anisotropic, repeat_enable;
uniform float tile_u = 8.0;     // tiles around the circumference (about 1.45 m each)
uniform float tile_v = 29.0;    // tiles along the 42 m
uniform float length_m = 42.0;
uniform float hot = 0.0;        // 0..1: how much the exhaust lights the lower hull
uniform float logical_t = 0.0;

float h21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vn(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(h21(i), h21(i + vec2(1.0, 0.0)), f.x), mix(h21(i + vec2(0.0, 1.0)), h21(i + vec2(1.0, 1.0)), f.x), f.y);
}

void fragment() {
	// glTF flips v: UV.y = 0 is the top (z = 42 m), 1 the nozzle end.
	float z = (1.0 - UV.y) * length_m;
	float w_eng = 1.0 - smoothstep(3.1, 3.45, z);
	float w_top = smoothstep(35.35, 35.7, z);
	float w_body = clamp(1.0 - w_eng - w_top, 0.0, 1.0);
	vec2 uv = vec2(UV.x * tile_u, (1.0 - UV.y) * tile_v);
	vec2 uv_b = uv * 0.43 + vec2(0.29, 0.61);
	float mix_b = 0.3 + 0.3 * vn(UV * vec2(9.0, 40.0));
	vec3 a0 = mix(texture(hull_alb, vec3(uv, 0.0)).rgb, texture(hull_alb, vec3(uv_b, 0.0)).rgb, mix_b);
	vec3 a1 = texture(hull_alb, vec3(uv, 1.0)).rgb;
	vec3 a2 = texture(hull_alb, vec3(uv, 2.0)).rgb;
	vec3 scan = a0 * w_body + a1 * w_top + a2 * w_eng;
	// The scanned white paint carries pink and brown blotches: keep its brightness variation, half its colour.
	scan = mix(vec3(dot(scan, vec3(0.299, 0.587, 0.114))), scan, 0.45);
	vec4 m = texture(mod_alb, UV);
	ALBEDO = scan * m.rgb;
	float r0 = mix(texture(hull_rgh, vec3(uv, 0.0)).r, texture(hull_rgh, vec3(uv_b, 0.0)).r, mix_b);
	float r1 = texture(hull_rgh, vec3(uv, 1.0)).r;
	float r2 = texture(hull_rgh, vec3(uv, 2.0)).r;
	float scan_r = r0 * w_body + r1 * w_top + r2 * w_eng;
	float baked_r = texture(mod_orm, UV).g;
	ROUGHNESS = clamp(scan_r * (0.6 + 0.9 * baked_r), 0.38, 1.0);
	float met0 = texture(hull_met, vec3(uv, 0.0)).r;
	float met2 = texture(hull_met, vec3(uv, 2.0)).r;
	// Painted metal: only scratches and the engine section are metallic.
	METALLIC = clamp(met0 * w_body * 0.12 + met2 * w_eng * 0.7 + texture(mod_orm, UV).b * 0.2, 0.0, 1.0);
	SPECULAR = 0.5;
	// Normal: the baked welds and panel seams plus the scan's micro-relief (UDN blend).
	vec3 n_scan = texture(hull_nrm, vec3(uv, 0.0)).xyz * w_body + texture(hull_nrm, vec3(uv, 1.0)).xyz * w_top + texture(hull_nrm, vec3(uv, 2.0)).xyz * w_eng;
	vec3 n_bake = texture(mod_nrm, UV).xyz;
	vec2 nxy = (n_scan.xy * 2.0 - 1.0) * 0.45 + (n_bake.xy * 2.0 - 1.0);
	NORMAL_MAP = vec3(nxy * 0.5 + 0.5, 1.0);
	NORMAL_MAP_DEPTH = 1.0;
	// Exhaust light on the lower hull: warm, strongest at the engine end, broken by noise.
	float near = (1.0 - smoothstep(0.0, 10.0, z)) * hot;
	float flick = 0.7 + 0.5 * vn(vec2(UV.x * 30.0, z * 0.6 - logical_t * 9.0));
	EMISSION = vec3(1.0, 0.42, 0.12) * near * flick * 0.9 * (0.4 + 0.6 * clamp(scan.r * 2.0, 0.0, 1.0));
}
