// Ground beyond the pack (illustration: there is no data there). Vertex colour is the pack image at
// the nearest edge point (sRGB), alpha marks water at mean sea level.
shader_type spatial;
render_mode cull_back;

uniform float logical_t = 0.0;

vec3 to_linear(vec3 c) { return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(0.04045, c)); }

void fragment() {
	vec3 c = to_linear(COLOR.rgb) * 0.8;
	float water = smoothstep(0.5, 0.95, COLOR.a);
	c = mix(c, c * 0.5 + vec3(0.008, 0.03, 0.05), water);
	ALBEDO = c;
	ROUGHNESS = mix(0.97, 0.2, water);
	SPECULAR = mix(0.3, 0.55, water);
}
