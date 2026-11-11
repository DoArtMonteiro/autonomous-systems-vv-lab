# Command line of the Cinematic View (arguments after "--"). Studio launches it with fixed arguments;
# every value is checked here and anything unknown is refused.
extends RefCounted

const CAMERAS := ["director", "follow", "pad", "closeup", "wide", "overhead", "lowwide"]
const PROFILES := ["auto", "performance", "balanced", "high", "ultra", "custom"]

var run_dir := ""
var env_dir := ""
var pose_dump: PackedFloat64Array = PackedFloat64Array()
var has_pose_dump := false
var profile := "auto"
var custom := {}
var vram_bytes := -1
var camera := "director"
var start_t := NAN
var shot_path := ""
var bench_path := ""
var bench_seconds := 12.0
var bench_t0 := NAN
var bench_t1 := NAN
var play := false
var controls := true
var presentation := false
var has_camera_pose := false
var camera_pose: PackedFloat64Array = PackedFloat64Array()  # east, north, up of the eye; of the target; vertical fov in degrees
var error := ""


static func usage() -> String:
	return "usage: -- --run <run dir> [--env <pack dir>] [--pose-dump t1,t2,...] [--profile auto|performance|balanced|high|ultra|custom] [--custom key=value,...] [--vram-bytes N] [--camera director|follow|pad|closeup|wide|overhead] [--t seconds] [--play] [--controls shown|hidden] [--presentation] [--camera-pose ex,ey,ez,tx,ty,tz,fov] [--shot out.png] [--bench out.json --bench-seconds S --bench-from T --bench-to T]"


static func parse(args: PackedStringArray) -> RefCounted:
	var c = load("res://scripts/cli.gd").new()
	var i := 0
	while i < args.size():
		var k := args[i]
		var needs_value := k in ["--run", "--env", "--pose-dump", "--profile", "--custom", "--vram-bytes", "--camera", "--t", "--shot", "--bench", "--bench-seconds", "--bench-from", "--bench-to", "--controls", "--camera-pose"]
		var v := ""
		if needs_value:
			if i + 1 >= args.size():
				c.error = "%s needs a value" % k
				return c
			v = args[i + 1]
			i += 2
		else:
			i += 1
		match k:
			"--run":
				c.run_dir = v
			"--env":
				c.env_dir = v
			"--pose-dump":
				c.has_pose_dump = true
				for part in v.split(",", false):
					if not part.strip_edges().is_valid_float():
						c.error = "--pose-dump takes numbers separated by commas"
						return c
					c.pose_dump.append(part.strip_edges().to_float())
			"--profile":
				if not (v in PROFILES):
					c.error = "unknown profile %s" % v
					return c
				c.profile = v
			"--custom":
				for kv in v.split(",", false):
					var p := kv.split("=")
					if p.size() != 2:
						c.error = "--custom takes key=value pairs"
						return c
					c.custom[p[0].strip_edges()] = p[1].strip_edges()
			"--vram-bytes":
				if not v.is_valid_int():
					c.error = "--vram-bytes takes an integer"
					return c
				c.vram_bytes = v.to_int()
			"--camera":
				if not (v in CAMERAS):
					c.error = "unknown camera %s" % v
					return c
				c.camera = v
			"--t":
				if not v.is_valid_float():
					c.error = "--t takes a number"
					return c
				c.start_t = v.to_float()
			"--shot":
				c.shot_path = v
			"--bench":
				c.bench_path = v
			"--bench-seconds":
				c.bench_seconds = clampf(v.to_float(), 1.0, 120.0)
			"--bench-from":
				c.bench_t0 = v.to_float()
			"--bench-to":
				c.bench_t1 = v.to_float()
			"--play":
				c.play = true
			"--presentation":
				c.presentation = true
			"--camera-pose":
				var parts := v.split(",", false)
				if parts.size() != 7:
					c.error = "--camera-pose takes seven numbers: eye east,north,up; target east,north,up; vertical fov in degrees"
					return c
				for part in parts:
					if not part.strip_edges().is_valid_float():
						c.error = "--camera-pose takes seven numbers separated by commas"
						return c
					c.camera_pose.append(part.strip_edges().to_float())
				if c.camera_pose[6] < 1.0 or c.camera_pose[6] > 120.0:
					c.error = "--camera-pose fov must be between 1 and 120 degrees"
					return c
				c.has_camera_pose = true
			"--controls":
				if not (v in ["shown", "hidden"]):
					c.error = "--controls takes shown or hidden"
					return c
				c.controls = v == "shown"
			_:
				c.error = "unknown argument %s" % k
				return c
	if c.run_dir == "":
		c.error = "--run is required"
	elif c.env_dir == "" and not c.has_pose_dump:
		c.error = "--env is required (except with --pose-dump)"
	return c
