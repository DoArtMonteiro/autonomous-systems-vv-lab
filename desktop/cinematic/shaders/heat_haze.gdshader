// Heat shimmer around the exhaust: a faint refraction of what is behind the plume, driven by the
// record time and the recorded throttle only. Illustrative; it is not a model of air density.
shader_type spatial;
render_mode unshaded, depth_draw_never, cull_disabled, shadows_disabled, fog_disabled;

uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap;
uniform float logical_t = 0.0;
uniform float strength = 0.004;
uniform float length_m = 20.0;
uniform float radius_m = 4.0;
uniform float clip_m = 1000.0;

varying vec3 v_m;
varying float v_f;

float h31(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
float noise3(vec3 p) {
	vec3 i = floor(p); vec3 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(mix(h31(i), h31(i + vec3(1, 0, 0)), f.x), mix(h31(i + vec3(0, 1, 0)), h31(i + vec3(1, 1, 0)), f.x), f.y),
		mix(mix(h31(i + vec3(0, 0, 1)), h31(i + vec3(1, 0, 1)), f.x), mix(h31(i + vec3(0, 1, 1)), h31(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}

// Normal of a degenerate triangle at the flame tip can be zero: never normalise that.
vec3 safe_n(vec3 n) {
	float l = length(n);
	return l > 1e-4 ? n / l : vec3(0.0, 0.0, 1.0);
}

void vertex() {
	v_f = UV.y;
	v_m = vec3(VERTEX.x * radius_m, VERTEX.y * length_m, VERTEX.z * radius_m);
}

void fragment() {
	float f = clamp(v_f, 0.0, 1.0);
	float a = f * length_m;
	if (a > clip_m) discard;
	float rim = pow(clamp(abs(dot(safe_n(NORMAL), normalize(VIEW))), 0.0, 1.0), 1.0);
	float mask = rim * smoothstep(0.0, 0.08, f) * (1.0 - smoothstep(0.55, 1.0, f)) * smoothstep(clip_m, clip_m - 2.0, a);
	vec3 p = vec3(v_m.x * 0.35, a * 0.16 - logical_t * 22.0, v_m.z * 0.35);
	vec2 off = vec2(noise3(p) - 0.5, noise3(p + vec3(31.4, 7.7, 2.9)) - 0.5) * strength * mask;
	ALBEDO = textureLod(screen_tex, SCREEN_UV + off, 0.0).rgb;
	ALPHA = clamp(mask * 4.0, 0.0, 1.0);
}
