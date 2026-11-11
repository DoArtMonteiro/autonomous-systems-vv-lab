// Terrain of an environment pack: the pack image as albedo on the pack heights (data), lit by the
// engine's PBR pipeline. Illustrative only: the darkening of aerial albedo, the fine grain near the
// camera, and the water finish where the heights are at mean sea level and the image is dark.
// `role` 0 is the base grid (its fragments inside the detail square are dropped, with 2 m of
// overlap), 1 the detail layer, which crossfades into the base image over its blend margin with the
// same weight as its heights blend into the base grid.
shader_type spatial;
render_mode depth_draw_opaque, cull_back;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D base_tex : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform int role = 0;
uniform float half_extent = 9000.0;   // half side of this layer's image (m)
uniform float base_half = 9000.0;     // half side of the base image (m)
uniform float detail_half = 0.0;      // 0 when the pack has no detail layer
uniform float detail_blend = 1.0;
uniform float grain = 0.07;
uniform float logical_t = 0.0;        // record time, so the water ripple is a function of t
uniform float blur_lod = 0.0;         // > 0 for the ground beyond the pack
// Mean land and water colours of the pack image (linear). Over the last edge_fade_m of the base
// grid the image fades into them, and the ground beyond the pack uses them: no edge is visible.
uniform vec3 land_avg : source_color = vec3(0.2);
uniform vec3 water_avg : source_color = vec3(0.05, 0.08, 0.1);
uniform float edge_fade_m = 2500.0;
uniform float beyond_sea = 0.5;  // fraction of the pack edge that is sea: one neutral colour beyond

varying vec2 v_xy;
varying float v_sea;

float h21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(h21(i), h21(i + vec2(1.0, 0.0)), f.x), mix(h21(i + vec2(0.0, 1.0)), h21(i + vec2(1.0, 1.0)), f.x), f.y);
}

void vertex() {
	v_xy = vec2(VERTEX.x, -VERTEX.z); // east, north
	v_sea = COLOR.a;
}

void fragment() {
	if (role == 0 && detail_half > 0.0 && max(abs(v_xy.x), abs(v_xy.y)) < detail_half - 2.0) {
		discard;
	}
	vec2 uv = vec2((v_xy.x + half_extent) / (2.0 * half_extent), (half_extent - v_xy.y) / (2.0 * half_extent));
	vec3 c = blur_lod > 0.0 ? textureLod(albedo_tex, clamp(uv, 0.0, 1.0), blur_lod).rgb : texture(albedo_tex, uv).rgb;
	float edge_e = 0.0;
	if (role == 0) {
		float e = blur_lod > 0.0 ? 1.0 : smoothstep(half_extent - edge_fade_m, half_extent, max(abs(v_xy.x), abs(v_xy.y)));
		c = mix(c, mix(land_avg, water_avg, beyond_sea), e);
		edge_e = e;
	}
	float dist = length(VERTEX);
	if (role == 1) {
		float d_in = detail_half - max(abs(v_xy.x), abs(v_xy.y));
		vec2 buv = vec2((v_xy.x + base_half) / (2.0 * base_half), (base_half - v_xy.y) / (2.0 * base_half));
		c = mix(texture(base_tex, buv).rgb, c, clamp(d_in / max(detail_blend, 1e-3), 0.0, 1.0));
		float gk = (1.0 - smoothstep(40.0, 320.0, dist)) * grain;
		float gn = vnoise(v_xy * 2.3) * 0.55 + vnoise(v_xy * 7.9) * 0.3 + vnoise(v_xy * 23.0) * 0.15;
		c *= 1.0 + gk * (gn - 0.5) * 2.0;
	}
	// Aerial photographs are exposed brightly: bring them towards ground albedos, and clamp the
	// brightest surfaces (concrete, sand) to an albedo of about 0.55 so they do not read white.
	c *= 0.8;
	float l0 = dot(c, vec3(0.2126, 0.7152, 0.0722));
	if (l0 > 0.3) c *= min(0.3 + (l0 - 0.3) * 0.25, 0.38) / l0;
	float lum = dot(c, vec3(0.2126, 0.7152, 0.0722));
	// Water: heights at mean sea level (data) and an image that is not bright (no beach or slab).
	// Its colour is a water body colour, not darkened imagery, so the pack and the ground beyond it
	// match; the look comes from a low roughness that reflects the sky.
	float water = smoothstep(0.5, 0.95, v_sea) * (1.0 - smoothstep(0.2, 0.28, lum)) * (1.0 - edge_e);
	c = mix(c, c * 0.7 + vec3(0.0, 0.006, 0.01), water);
	ALBEDO = c;
	ROUGHNESS = mix(mix(0.92, 0.45, edge_e * beyond_sea), 0.05, water);
	SPECULAR = mix(0.35, 0.5, water);
	if (water > 0.01) {
		// Illustrative ripple on the water normal, driven by the record time (no wall clock).
		vec2 p = v_xy * 0.08;
		float a = vnoise(p + vec2(logical_t * 0.21, logical_t * 0.13));
		float b = vnoise(p * 2.7 - vec2(logical_t * 0.17, 0.0));
		vec3 n_w = normalize(vec3((a - 0.5) * 0.18 + (b - 0.5) * 0.09, 1.0, (b - 0.5) * 0.18));
		NORMAL = normalize(mix(NORMAL, (VIEW_MATRIX * vec4(n_w, 0.0)).xyz, water * (1.0 - smoothstep(200.0, 3000.0, dist))));
	}
}
