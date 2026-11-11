// Buildings and structures (illustrative surfaces on data footprints and heights). Roofs keep the
// colour the pack builder sampled from the image over each footprint, with membrane and gravel
// variation; walls get a procedural cladding: floor bands every 3.5 m, panel joints every 4 m,
// darker glazing strips and a darker plinth. Everything is a function of the world position.
shader_type spatial;
render_mode cull_back;

varying vec3 v_world;
varying vec3 v_wn;

float h21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(h21(i), h21(i + vec2(1.0, 0.0)), f.x), mix(h21(i + vec2(0.0, 1.0)), h21(i + vec2(1.0, 1.0)), f.x), f.y);
}

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	v_wn = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	vec3 base = COLOR.rgb;
	float dist = length(VERTEX);
	float detail = 1.0 - smoothstep(600.0, 2500.0, dist);
	if (v_wn.y > 0.7) {
		// Roof: image colour with large patches and fine grit.
		float n = vnoise(v_world.xz * 0.15) * 0.6 + vnoise(v_world.xz * 1.7) * 0.4;
		ALBEDO = base * (0.88 + 0.24 * n * detail);
		ROUGHNESS = 0.78 + 0.18 * n;
		SPECULAR = 0.35;
	} else {
		// Wall: along-wall coordinate from the horizontal position, height from y.
		float u = dot(v_world.xz, normalize(vec2(-v_wn.z, v_wn.x)));
		float y = v_world.y;
		float floor_band = smoothstep(0.0, 0.08, abs(fract(y / 3.5) - 0.5) - 0.42);
		float joint = smoothstep(0.0, 0.06, abs(fract(u / 4.0) - 0.5) - 0.46);
		float glazing = step(0.45, fract(y / 3.5)) * step(fract(y / 3.5), 0.8) * step(0.15, fract(u / 4.0)) * step(fract(u / 4.0), 0.85);
		vec3 c = base * (1.0 - 0.18 * floor_band * detail - 0.12 * joint * detail);
		c = mix(c, vec3(0.05, 0.07, 0.09), glazing * 0.75 * detail);
		c *= mix(0.62, 1.0, COLOR.a);  // plinth darkening (vertex alpha 0 at the foot)
		ALBEDO = c;
		ROUGHNESS = mix(0.82, 0.12, glazing * detail);
		METALLIC = 0.05 * glazing;
		SPECULAR = mix(0.4, 0.6, glazing);
	}
}
