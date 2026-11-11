// Illustrative sky: a single-scattering-like gradient (deep zenith, pale hazy horizon, warm Mie halo
// and disc around the sun) and two lit cloud layers: fair-weather cumulus on a plane at 2.2 km and a
// thin cirrus veil at 8 km, both shaded by sampling the cloud density towards the sun. Static: the
// clouds do not move, so a frame at a given t is always the same. No weather is part of the model.
shader_type sky;

uniform vec3 zenith : source_color = vec3(0.11, 0.30, 0.66);
uniform vec3 horizon : source_color = vec3(0.70, 0.79, 0.89);
uniform vec3 sun_haze : source_color = vec3(1.0, 0.9, 0.74);
uniform vec3 ground : source_color = vec3(0.42, 0.46, 0.48);
uniform float energy = 1.0;
uniform float cloud_cover = 0.62;
uniform float cumulus_height = 1700.0;
uniform float cirrus_height = 8000.0;
uniform float dip = 0.0;      // dip of the horizon below the camera, radians (the Earth's limb)
uniform float space = 0.0;   // 0 at the ground, 1 in space: the sky darkens with the camera's recorded altitude

float h21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(h21(i), h21(i + vec2(1.0, 0.0)), f.x), mix(h21(i + vec2(0.0, 1.0)), h21(i + vec2(1.0, 1.0)), f.x), f.y);
}
float fbm(vec2 p, int oct) {
	float a = 0.5; float s = 0.0;
	for (int k = 0; k < oct; k++) { s += a * vnoise(p); p = p * 2.03 + vec2(17.1, 9.3); a *= 0.5; }
	return s;
}

// Cumulus density at a point of the cloud plane (metres east/north).
float cumulus(vec2 p) {
	vec2 q = p / 2100.0;
	float base = fbm(q + vec2(3.7, 1.1), 5);
	float c = smoothstep(1.0 - cloud_cover, 1.0 - cloud_cover + 0.22, base);
	float erode = fbm(q * 5.0 + vec2(8.0, 2.0), 3);
	return clamp(c * (1.15 - 0.55 * erode) - 0.05, 0.0, 1.0);
}

void sky() {
	vec3 d = EYEDIR;
	float h = d.y;
	vec3 sun = LIGHT0_ENABLED ? LIGHT0_DIRECTION : vec3(0.0, 0.45, 0.89);
	float mu = max(dot(d, sun), 0.0);
	float up = max(h, 0.0);
	// Optical-depth-like blend: a wide pale horizon band, a deep zenith, lighter towards the sun.
	vec3 c = mix(horizon, zenith, pow(1.0 - exp(-up * 3.0), 0.9));
	c *= 1.0 + 0.16 * pow(mu, 2.0) * (1.0 - up * 0.5);
	c = mix(c, mix(horizon, sun_haze, 0.55), pow(mu, 6.0) * 0.5 * exp(-up * 2.0));
	c += sun_haze * (0.18 * pow(mu, 12.0) + 0.6 * pow(mu, 180.0));
	if (AT_CUBEMAP_PASS == false && mu > 0.99996) c += vec3(18.0, 16.0, 13.0);
	// Clouds.
	if (h > 0.012) {
		vec2 sxz = normalize(sun.xz + vec2(1e-4));
		float haze_k = 1.0 - exp(-0.045 / (h + 0.01));   // far clouds fade into the horizon haze
		// Cirrus veil: stretched streaks, thin, high.
		{
			vec2 p = d.xz / h * cirrus_height;
			vec2 q = vec2(p.x / 9000.0, p.y / 2600.0);
			float n = fbm(q + vec2(11.0, 4.0), 4);
			float v = smoothstep(0.52, 0.8, n) * 0.38 * smoothstep(0.02, 0.2, h);
			vec3 cc = mix(vec3(0.86, 0.9, 0.97), vec3(1.0, 0.97, 0.92), pow(mu, 3.0));
			c = mix(c, cc, v * (1.0 - haze_k * 0.7));
		}
		// Cumulus: density, light from the sun side, shaded undersides.
		{
			vec2 p = d.xz / h * cumulus_height;
			float dens = cumulus(p);
			if (dens > 0.003) {
				float ds = cumulus(p + sxz * 420.0);
				float ds2 = cumulus(p + sxz * 1100.0);
				float shade = clamp(1.0 - (ds * 1.1 + ds2 * 0.6) + 0.15, 0.0, 1.0);
				float thick = clamp(dens * 1.4, 0.0, 1.0);
				vec3 lit = vec3(1.08, 1.04, 0.97);
				vec3 dark = vec3(0.48, 0.55, 0.68);
				vec3 cc = mix(dark, lit, shade);
				cc = mix(cc, lit * 1.1, pow(mu, 4.0) * 0.5 * (1.0 - thick * 0.5));       // silver lining towards the sun
				cc = mix(cc, vec3(0.75, 0.82, 0.92), haze_k);
				float a = smoothstep(0.0, 0.7, dens) * (1.0 - haze_k * 0.85);
				c = mix(c, cc, a * smoothstep(0.012, 0.09, h));
			}
		}
	}
	// Below the horizon: the horizon haze (the fog samples this radiance over distant ground, so
	// fogged land meets the sky without a band); the ground colour only far below.
	if (h < 0.0) c = mix(horizon, ground, smoothstep(0.25, 0.9, -h));
	// With altitude the blue sky thins out to black; the sun and the horizon glow remain.
	c *= 1.0 - 0.985 * space * (1.0 - pow(mu, 80.0));
	// Thin bright limb of the atmosphere just above the Earth's edge, seen from space (illustrative).
	float limb = exp(-max(h + sin(dip), 0.0) * 70.0) * step(-sin(dip) - 0.002, h);
	c += vec3(0.28, 0.52, 1.0) * limb * space * 0.9;
	COLOR = c * energy;
}
