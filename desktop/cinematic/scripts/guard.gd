extends Node
## Runtime guard of the development project: defence in depth, not the main protection.
##
## The main protection is structural: in the repository this project has the development name
## ("VV Lab Cinematic Dev", `config/name` and `config/custom_user_dir_name`), so Godot keeps its
## user data in "%APPDATA%/VV Lab Cinematic Dev", never in the folder of the installed module
## ("VV Lab Cinematic"). Only scripts/cinematic/package_module.py stamps the release name when it
## packages the module, and it leaves this script and its autoload entry out.
##
## This script is the first autoload. When the name is not the release one it quits with a non-zero
## code unless the launch token of the authorised launcher (desktop/studio/tests/godot_launch.py) is
## valid and the resolved user data folder lies inside the token's folder and outside the installed
## module's folders. Godot may have created its log file and caches before any script runs (see
## docs/incidents/2026-11-23-webview2-profile.md), so this check cannot prevent those writes; the
## development name does. It protects against accidental misuse only: it has no secret.

const RELEASE_NAME := "VV Lab Cinematic"
const REFUSED_EXIT := 78
const ENV_LAUNCH := "VVLAB_DEV_LAUNCH"
const ENV_NONCE := "VVLAB_DEV_NONCE"

var _why := ""


func _init() -> void:
	var app_name := str(ProjectSettings.get_setting("application/config/custom_user_dir_name", ""))
	if app_name == RELEASE_NAME:
		return
	_why = decide(
		app_name,
		OS.get_environment(ENV_LAUNCH),
		OS.get_environment(ENV_NONCE),
		OS.get_user_data_dir(),
	)


func _enter_tree() -> void:
	if _why != "":
		printerr("VV Lab Cinematic (development): refused to start: " + _why)
		get_tree().quit(REFUSED_EXIT)


## The empty string when the start is allowed, else the reason. Pure apart from reading the token file.
static func decide(app_name: String, token_path: String, nonce: String, user_dir: String) -> String:
	if app_name == RELEASE_NAME:
		return ""
	if token_path == "" or nonce == "":
		return "no launch token: this development project was not started by the authorised launcher"
	if not FileAccess.file_exists(token_path):
		return "the launch token cannot be read"
	var token = JSON.parse_string(FileAccess.get_file_as_string(token_path))
	if typeof(token) != TYPE_DICTIONARY:
		return "the launch token is not valid"
	if str(token.get("nonce", "")) != nonce:
		return "the launch nonce does not match the token"
	var dir := _norm(str(token.get("token_dir", "")))
	if dir == "":
		return "the launch token has no folder"
	var user := _norm(user_dir)
	if user == "" or not _under(user, dir):
		return "the user data folder " + user + " is outside the token folder"
	var protected = token.get("protected", [])
	if typeof(protected) != TYPE_ARRAY:
		return "the launch token lists no protected folders"
	for p in protected:
		var root := _norm(str(p))
		if root != "" and (_under(user, root) or _under(root, user)):
			return "the user data folder " + user + " is in or contains installed data " + root
	return ""


static func _norm(path: String) -> String:
	var p := path.replace("\\", "/")
	if p.begins_with("//?/") or p.begins_with("//./"):
		p = p.substr(4)
	elif p.begins_with("//"):
		return ""  # a network path is never a token folder
	while p.length() > 1 and p.ends_with("/"):
		p = p.substr(0, p.length() - 1)
	return p.to_lower()


static func _under(path: String, root: String) -> bool:
	return path == root or path.begins_with(root + "/")
