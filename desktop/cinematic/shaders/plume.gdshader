// Illustrative exhaust plume, drawn as layered shells (outer flame, merged core, per-engine jets).
// Its length is the technical view's rule on the recorded applied throttle; everything else (colour,
// turbulence, shock diamonds) is drawn, not modelled. Every moving part is a function of the record
// time `logical_t` and of the recorded throttle, never of the wall clock, so a frame at a given t is
// always the same. Mesh: unit lathe, UV.x around, UV.y = 0 at the nozzle exit and 1 at the tip.
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled, fog_disabled;

uniform vec3 hot : source_color = vec3(1.0, 0.82, 0.55);
uniform vec3 warm : source_color = vec3(1.0, 0.42, 0.12);
uniform vec3 cool : source_color = vec3(0.55, 0.1, 0.04);
uniform float intensity = 2.0;
uniform float logical_t = 0.0;
uniform float throttle = 0.6;       // recorded applied throttle, 0..1
uniform float length_m = 20.0;
uniform float radius_m = 2.0;
uniform float diamonds = 0.0;       // shock-diamond strength (0 for the outer shell)
uniform float body_fade = 1.0;      // fades the nozzle end into the engine instead of a hard disc

varying vec3 v_m;      // position in metres, mesh-local axes
varying float v_f;

float h31(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
float noise3(vec3 p) {
	vec3 i = floor(p); vec3 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(mix(h31(i), h31(i + vec3(1, 0, 0)), f.x), mix(h31(i + vec3(0, 1, 0)), h31(i + vec3(1, 1, 0)), f.x), f.y),
		mix(mix(h31(i + vec3(0, 0, 1)), h31(i + vec3(1, 0, 1)), f.x), mix(h31(i + vec3(0, 1, 1)), h31(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}
float fbm3(vec3 p) {
	return 0.5 * noise3(p) + 0.25 * noise3(p * 2.03 + 5.1) + 0.125 * noise3(p * 4.1 + 9.7) + 0.0625 * noise3(p * 8.3 + 1.3);
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
	float f = clamp(v_f, 0.0, 1.0);   // interpolation can overshoot 1 at the tip; pow(negative) is NaN
	float a = f * length_m;
	// Turbulence advected down the plume with the record time (speed ~ 40 m/s).
	float n = fbm3(vec3(v_m.x * 0.55, a * 0.22 - logical_t * 40.0, v_m.z * 0.55));
	float n2 = noise3(vec3(v_m.x * 1.7 + 3.0, a * 0.7 - logical_t * 63.0, v_m.z * 1.7));
	// Volume-like falloff: bright where the view crosses the middle of the shell.
	float rim = pow(clamp(abs(dot(safe_n(NORMAL), normalize(VIEW))), 0.0, 1.0), 1.25);
	float along = pow(1.0 - f, 1.9);
	float tip = 1.0 - smoothstep(0.55, 1.0, f + (n - 0.5) * 0.25);
	float root = smoothstep(0.0, 0.03, f) * mix(1.0, smoothstep(0.0, 0.12, f), 1.0 - body_fade);
	float dens = rim * along * tip * root * (0.45 + 0.9 * n) * (0.85 + 0.3 * n2);
	// Mach diamonds: bright cells in the first third of the jet, stronger at high throttle.
	float spacing = mix(1.7, 2.7, throttle) * radius_m * 0.8;
	float cell = 0.5 + 0.5 * cos(6.28318 * a / spacing);
	float dm = diamonds * smoothstep(0.35, 0.9, throttle) * (1.0 - smoothstep(0.1, 0.55, f));
	dens *= 1.0 + dm * (pow(cell, 4.0) * 1.8 - 0.35);
	float heat = clamp(1.0 - f * 1.5 + (n - 0.5) * 0.5 + dm * pow(cell, 4.0) * 0.5, 0.0, 1.0);
	vec3 c = mix(cool, warm, smoothstep(0.0, 0.5, heat));
	c = mix(c, hot, smoothstep(0.45, 1.0, heat));
	ALBEDO = c * intensity * dens;
}
