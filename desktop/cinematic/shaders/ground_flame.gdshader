// Exhaust spreading along the ground when the nozzle is at the ground (illustration): a flared skirt
// of turbulent flame around the stage's foot, running outwards from the engines to the ground, with
// streaks moving outwards with the record time. A function of the recorded throttle, the nozzle
// height and the record time only. Blended, not additive: an additive layer on pale ground is pushed
// to white by the tone mapper. Mesh: UV.x around, UV.y = 0 at the engines and 1 on the ground ring.
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, shadows_disabled, fog_disabled;

uniform float logical_t = 0.0;
uniform float strength = 1.0;
uniform vec3 hot : source_color = vec3(1.0, 0.72, 0.32);
uniform vec3 warm : source_color = vec3(0.95, 0.30, 0.06);

float h21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float n2(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(h21(i), h21(i + vec2(1, 0)), f.x), mix(h21(i + vec2(0, 1)), h21(i + vec2(1, 1)), f.x), f.y);
}
vec3 safe_n(vec3 n) {
	float l = length(n);
	return l > 1e-4 ? n / l : vec3(0.0, 1.0, 0.0);
}

void fragment() {
	float t = clamp(UV.y, 0.0, 1.0);
	float ang = UV.x * 6.28318;
	float streak = n2(vec2(cos(ang) * 4.0 + sin(ang) * 4.0 + ang * 2.0, t * 5.0 - logical_t * 16.0));
	float billow = n2(vec2(ang * 2.4 + 4.0, t * 3.0 - logical_t * 9.0));
	float rim = 0.45 + 0.55 * clamp(abs(dot(safe_n(NORMAL), normalize(VIEW))), 0.0, 1.0);
	float radial = pow(1.0 - t, 1.5) * smoothstep(0.0, 0.1, t);
	float a = rim * radial * (0.35 + 0.95 * streak) * (0.65 + 0.55 * billow) * strength;
	float heat = clamp(pow(1.0 - t, 1.4) * 1.5 + (streak - 0.5) * 0.4, 0.0, 1.0);
	ALBEDO = mix(warm, hot, heat);
	ALPHA = clamp(a * 1.25, 0.0, 0.9);
}
