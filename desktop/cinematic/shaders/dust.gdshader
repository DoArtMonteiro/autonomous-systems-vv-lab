// Ground dust and debris cloud thrown out by the exhaust close to the ground (illustration).
// Ray-marched in a box (cull_front: every pixel is shaded once, also from inside the cloud); the
// density is value noise carried outwards with the record time, scaled by `strength`, which the
// caller derives from the recorded throttle and the nozzle height above the drawn ground. Nothing
// here reads the wall clock.
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_front, shadows_disabled, fog_disabled;

uniform sampler2D depth_tex : hint_depth_texture, filter_nearest;
uniform float logical_t = 0.0;
uniform float strength = 1.0;      // 0..1
uniform float heat = 0.0;          // warm glow of the exhaust inside the cloud, 0..1
uniform vec3 dust_colour : source_color = vec3(0.74, 0.68, 0.60);
uniform vec3 sun_dir = vec3(0.4, 0.5, 0.6);  // world, towards the sun
uniform float half_height = 0.3;   // box half-height in box units (the mesh is 2 x 2*half_height x 2)

varying vec3 v_local;
varying vec3 v_cam;
varying vec3 v_sun;
varying float v_scale;

float h31(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
float noise3(vec3 p) {
	vec3 i = floor(p); vec3 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(mix(h31(i), h31(i + vec3(1, 0, 0)), f.x), mix(h31(i + vec3(0, 1, 0)), h31(i + vec3(1, 1, 0)), f.x), f.y),
		mix(mix(h31(i + vec3(0, 0, 1)), h31(i + vec3(1, 0, 1)), f.x), mix(h31(i + vec3(0, 1, 1)), h31(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}

float density(vec3 p, bool detail) {
	float rr = length(p.xz);
	if (rr >= 1.0 || p.y < 0.0 || p.y > half_height * 2.0) return 0.0;
	float yy = p.y;
	float body = smoothstep(1.0, 0.45, rr) * exp(-yy / (half_height * 0.7)) * smoothstep(0.0, 0.5 * half_height, yy);
	// Outward flow: the noise field slides away from the axis and rises slowly with the record time.
	vec2 dir = p.xz / max(rr, 1e-3);
	vec3 q = vec3(p.x - dir.x * logical_t * 0.9, p.y * 1.7 - logical_t * 0.25, p.z - dir.y * logical_t * 0.9) * 2.7;
	float n = noise3(q) * 0.55 + noise3(q * 2.1 + 7.3) * 0.3;
	if (detail) n += noise3(q * 4.4 + 2.2) * 0.15; else n += 0.075;
	float d = body * smoothstep(0.34, 0.62, n + 0.26 * (1.0 - rr));
	return d * strength;
}

void vertex() {
	v_local = VERTEX;
	mat4 inv_model = inverse(MODEL_MATRIX);
	v_cam = (inv_model * INV_VIEW_MATRIX[3]).xyz;
	v_sun = normalize((inv_model * vec4(sun_dir, 0.0)).xyz);
	v_scale = length(MODEL_MATRIX[0].xyz);
}

void fragment() {
	vec3 ro = v_cam;
	vec3 rd = normalize(v_local - ro);
	vec3 he = vec3(1.0, half_height, 1.0);
	vec3 inv = 1.0 / (rd + vec3(1e-6));
	vec3 t0 = (-he - ro) * inv;
	vec3 t1 = (he - ro) * inv;
	float tmin = max(max(min(t0.x, t1.x), min(t0.y, t1.y)), min(t0.z, t1.z));
	float tmax = min(min(max(t0.x, t1.x), max(t0.y, t1.y)), max(t0.z, t1.z));
	float entry = max(tmin, 0.0);
	// Stop at the scene: terrain and stage in front of the back face hide the cloud behind them.
	float depth = textureLod(depth_tex, SCREEN_UV, 0.0).x;
	vec4 ndc = vec4(SCREEN_UV * 2.0 - 1.0, depth, 1.0);
	vec4 vp = INV_PROJECTION_MATRIX * ndc;
	float scene_d = length(vp.xyz / vp.w) / v_scale;
	float t_end = min(tmax, scene_d);
	if (t_end <= entry) discard;
	const int STEPS = 22;
	float dt = (t_end - entry) / float(STEPS);
	float jitter = fract(52.9829189 * fract(dot(FRAGCOORD.xy, vec2(0.06711056, 0.00583715))));
	float T = 1.0;
	vec3 acc = vec3(0.0);
	for (int i = 0; i < STEPS; i++) {
		float t = entry + (float(i) + jitter) * dt;
		// Box centre is the node origin; the cloud's y runs from the ground (box bottom) up.
		vec3 p = ro + rd * t + vec3(0.0, half_height, 0.0);
		float d = density(p, true);
		if (d > 0.002) {
			float shade = exp(-density(p + v_sun * 0.18, false) * 1.6);
			float amb = mix(0.55, 1.0, clamp(p.y / (half_height * 1.2), 0.0, 1.0));
			vec3 col = dust_colour * (0.38 + 0.9 * shade) * amb;
			float rr = length(p.xz);
			col += vec3(1.0, 0.55, 0.22) * heat * exp(-rr * 5.5) * exp(-p.y / (half_height * 0.45)) * 0.55;
			float a = 1.0 - exp(-d * dt * v_scale * 0.11);
			acc += T * a * col;
			T *= 1.0 - a;
			if (T < 0.02) break;
		}
	}
	float alpha = 1.0 - T;
	if (alpha < 0.003) discard;
	ALBEDO = acc / max(alpha, 1e-4);
	ALPHA = alpha;
}
