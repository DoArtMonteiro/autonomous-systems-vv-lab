// Exhaust spreading over the ground where the plume reaches it (illustration): a warm glow, blended
// over the ground (an additive layer on pale concrete is pushed to white by the tone mapper),
// brightest under the nozzle, with a faint shock ring and angular turbulence moving with the record
// time. Drawn only while the recorded engine is on and the nozzle is within the plume's reach.
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, shadows_disabled, fog_disabled;

uniform float logical_t = 0.0;
uniform float strength = 1.0;
uniform vec3 colour : source_color = vec3(1.0, 0.5, 0.2);

float h21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float n2(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(h21(i), h21(i + vec2(1, 0)), f.x), mix(h21(i + vec2(0, 1)), h21(i + vec2(1, 1)), f.x), f.y);
}

void fragment() {
	vec2 q = UV * 2.0 - 1.0;
	float r = length(q);
	if (r >= 1.0) discard;
	float ang = atan(q.y, q.x);
	float turb = 0.75 + 0.5 * n2(vec2(ang * 2.2 + logical_t * 7.0, r * 5.0 - logical_t * 12.0));
	float core = pow(1.0 - r, 4.5);
	float ring = exp(-pow((r - 0.62) * 8.0, 2.0)) * 0.35;
	float g = (core + ring) * turb;
	ALBEDO = mix(colour * 2.2, vec3(2.4, 1.9, 1.3), core);
	ALPHA = clamp(g * strength * 1.5, 0.0, 0.85);
}
