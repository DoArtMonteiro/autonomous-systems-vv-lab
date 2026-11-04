# VV Lab Cinematic View: entry point. Reads a run directory and an environment pack directory,
# validates them, builds the scene and replays the record. It never simulates: the stage pose at
# logical time t comes only from record.pose_at(t).
#
# Exit codes: 0 done, 2 bad arguments, 3 invalid run record, 4 invalid or tampered pack.
extends Node3D

const Cli := preload("res://scripts/cli.gd")
const RunRecord := preload("res://scripts/record.gd")
const Frame := preload("res://scripts/frame.gd")

var cli
var record
var vehicle: Node3D


func _ready() -> void:
	cli = Cli.parse(OS.get_cmdline_user_args())
	if cli.error != "":
		_fail(2, cli.error + "\n" + Cli.usage())
		return
	record = RunRecord.load_dir(cli.run_dir)
	if record.error != "":
		_fail(3, "run: " + record.error)
		return
	vehicle = Node3D.new()
	vehicle.name = "Vehicle"
	add_child(vehicle)
	if cli.has_pose_dump:
		_pose_dump()
		return


func _fail(code: int, message: String) -> void:
	printerr("cinematic: " + message)
	get_tree().quit(code)


# Places the vehicle node at the recorded pose of logical time t; returns the pose (64-bit).
func apply_pose(t: float) -> Dictionary:
	var p: Dictionary = record.pose_at(t)
	if p["position"] != null:
		vehicle.position = Frame.to_godot(p["position"][0], p["position"][1], p["position"][2])
	vehicle.basis = Basis(Frame.quat_to_godot(p["quaternion"]).normalized())
	return p


# Headless check of what is drawn: for each t, the pose from the record (64-bit, model frame) and
# the transform of the drawn stage node read back from the scene and converted to the model frame.
func _pose_dump() -> void:
	for t in cli.pose_dump:
		var p := apply_pose(t)
		var gt := vehicle.global_transform
		var axis := gt.basis.x.normalized()
		var out := {
			"t": t,
			"index": p["index"],
			"position_enu": p["position"],
			"quaternion_wxyz": p["quaternion"],
			"axis_enu": Frame.rotate_enu(p["quaternion"], [1.0, 0.0, 0.0]),
			"drawn_position_enu": Frame.to_enu(gt.origin),
			"drawn_axis_enu": Frame.to_enu(axis),
			"plume_m": record.plume_length(t),
		}
		print("POSE " + JSON.stringify(out, "", true, true))
	get_tree().quit(0)
