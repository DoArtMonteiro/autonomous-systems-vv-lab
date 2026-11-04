// Illustrative exhaust plume. Its length is the technical view's rule on the recorded applied
// throttle; everything else (colour, turbulence, glow) is drawn, not modelled. The turbulence is a
// function of the record time `logical_t`, so a frame at a given t is always the same.
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled;

uniform vec3 colour : source_color = vec3(1.0, 0.6, 0.24);
uniform float intensity = 3.0;
uniform float logical_t = 0.0;
uniform float core = 0.0;  // 1 for the bright inner core

varying float v_f;   // 0 at the nozzle exit, 1 at the tip
varying vec3 v_local;

float h31(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
float noise3(vec3 p) {
	vec3 i = floor(p); vec3 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	float n000 = h31(i), n100 = h31(i + vec3(1, 0, 0)), n010 = h31(i + vec3(0, 1, 0)), n110 = h31(i + vec3(1, 1, 0));
	float n001 = h31(i + vec3(0, 0, 1)), n101 = h31(i + vec3(1, 0, 1)), n011 = h31(i + vec3(0, 1, 1)), n111 = h31(i + vec3(1, 1, 1));
	return mix(mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y), mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y), f.z);
}

void vertex() {
	v_f = clamp(0.5 - VERTEX.y, 0.0, 1.0); // centred mesh: +0.5 is the nozzle end
	v_local = VERTEX;
}

void fragment() {
	float n = noise3(vec3(v_local.x * 3.0, v_local.y * 9.0 + logical_t * 14.0, v_local.z * 3.0)) * 0.6
		+ noise3(vec3(v_local.x * 7.0, v_local.y * 23.0 + logical_t * 31.0, v_local.z * 7.0)) * 0.4;
	float along = pow(1.0 - v_f, mix(1.6, 3.0, core));
	// Fresnel-like falloff so the cone reads as a volume, not a shell.
	float rim = pow(clamp(abs(dot(normalize(NORMAL), normalize(VIEW))), 0.0, 1.0), 1.5);
	float a = along * rim * (0.55 + 0.45 * n);
	// Shock-diamond banding near the nozzle (illustration).
	a *= 1.0 + 0.35 * core * smoothstep(0.0, 0.08, v_f) * (0.5 + 0.5 * cos(v_f * 60.0));
	vec3 c = mix(colour, vec3(1.0, 0.93, 0.8), core);
	ALBEDO = c * intensity * a;
}
