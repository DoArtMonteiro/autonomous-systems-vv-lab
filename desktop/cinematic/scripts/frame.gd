# Frames. The record and the pack share the model frame: x east, y north, z up, origin at the pad
# centre on the ground (heading 0; packs with another heading are refused, as vv-geo does). Godot is
# right-handed with y up, so the drawn frame is (x_g, y_g, z_g) = (east, up, -north). This is a
# proper rotation M; a recorded attitude R maps to M R M^T, i.e. the quaternion (w, x, y, z) of the
# record becomes Godot's Quaternion(x, z, -y, w). Body axes map the same way: the stage axis x_B is
# local +X of the stage node.
extends RefCounted


static func to_godot(e: float, n: float, u: float) -> Vector3:
	return Vector3(e, u, -n)


static func to_enu(v: Vector3) -> Array:
	return [float(v.x), float(-v.z), float(v.y)]


# Record quaternion [w, x, y, z] (body to model frame) as a Godot quaternion (local to world).
static func quat_to_godot(q: Array) -> Quaternion:
	return Quaternion(q[1], q[3], -q[2], q[0])


# Rotates the model-frame vector v by the record quaternion q = [w, x, y, z], in 64-bit floats.
static func rotate_enu(q: Array, v: Array) -> Array:
	var w: float = q[0]
	var x: float = q[1]
	var y: float = q[2]
	var z: float = q[3]
	# t = 2 * cross(q.xyz, v); v' = v + w * t + cross(q.xyz, t)
	var tx: float = 2.0 * (y * v[2] - z * v[1])
	var ty: float = 2.0 * (z * v[0] - x * v[2])
	var tz: float = 2.0 * (x * v[1] - y * v[0])
	return [v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx)]
