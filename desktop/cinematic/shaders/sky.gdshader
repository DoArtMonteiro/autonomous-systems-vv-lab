// Illustrative sky: a single-scattering-like gradient (deep zenith, pale hazy horizon, warm Mie
// halo around the sun), a sun disc and a thin layer of fair-weather cumulus. Static: the clouds do
// not move, so a frame at a given t is always the same. No weather is part of the model.
shader_type sky;

uniform vec3 zenith : source_color = vec3(0.13, 0.32, 0.66);
uniform vec3 horizon : source_color = vec3(0.72, 0.80, 0.89);
uniform vec3 sun_haze : source_color = vec3(1.0, 0.9, 0.74);
uniform vec3 ground : source_color = vec3(0.42, 0.46, 0.48);
uniform float energy = 1.0;
uniform float cloud_cover = 0.3;

float h21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(h21(i), h21(i + vec2(1.0, 0.0)), f.x), mix(h21(i + vec2(0.0, 1.0)), h21(i + vec2(1.0, 1.0)), f.x), f.y);
}
float fbm(vec2 p) {
	float a = 0.5; float s = 0.0;
	for (int k = 0; k < 5; k++) { s += a * vnoise(p); p = p * 2.03 + vec2(17.1, 9.3); a *= 0.5; }
	return s;
}

void sky() {
	vec3 d = EYEDIR;
	float h = d.y;
	vec3 sun = LIGHT0_ENABLED ? LIGHT0_DIRECTION : vec3(0.0, 0.45, 0.89);
	float mu = max(dot(d, sun), 0.0);
	float up = max(h, 0.0);
	// Optical-depth-like blend: the horizon band is wide and pale, the zenith deep.
	vec3 c = mix(horizon, zenith, 1.0 - exp(-up * 3.2));
	c = mix(c, mix(horizon, sun_haze, 0.55), pow(mu, 6.0) * 0.55 * exp(-up * 2.0));
	c += sun_haze * (0.18 * pow(mu, 12.0) + 0.6 * pow(mu, 180.0));
	if (AT_CUBEMAP_PASS == false && mu > 0.99996) c += vec3(18.0, 16.0, 13.0);
	// Clouds: projected on a plane, thinning towards the horizon.
	if (h > 0.01) {
		vec2 p = d.xz / (h + 0.08) * 0.7;
		float n = fbm(p + vec2(3.7, 1.1));
		float cov = smoothstep(1.0 - cloud_cover, 1.0 - cloud_cover + 0.4, n);
		cov *= smoothstep(0.01, 0.12, h);
		float lit = 0.75 + 0.35 * pow(mu, 3.0) + 0.25 * fbm(p * 2.0 + sun.xz);
		vec3 cc = mix(vec3(0.82, 0.85, 0.9), vec3(1.05, 1.02, 0.97), clamp(lit - 0.6, 0.0, 1.0));
		c = mix(c, cc, cov * 0.85);
	}
	// Below the horizon: the horizon haze (the fog samples this radiance over distant ground, so
	// fogged land meets the sky without a band); the ground colour only far below.
	if (h < 0.0) c = mix(horizon, ground, smoothstep(0.25, 0.9, -h));
	COLOR = c * energy;
}
