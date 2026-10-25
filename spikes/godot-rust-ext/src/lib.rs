//! Spike: a Godot class implemented in Rust that loads recorded positions from a
//! vv-lab trace. Evaluation only; it does not simulate anything.

use godot::prelude::*;

struct TraceExtension;

#[gdextension]
unsafe impl ExtensionLibrary for TraceExtension {}

#[derive(GodotClass)]
#[class(init, base = RefCounted)]
struct TraceSource {}

#[godot_api]
impl TraceSource {
    /// Recorded (x_mm, y_mm) per tick, or an empty array if the file is unreadable.
    #[func]
    fn load_positions(path: GString) -> PackedVector2Array {
        let Ok(text) = std::fs::read_to_string(path.to_string()) else {
            return PackedVector2Array::new();
        };
        let Ok(trace) = serde_json::from_str::<serde_json::Value>(&text) else {
            return PackedVector2Array::new();
        };
        let mut out = PackedVector2Array::new();
        for state in trace["states"].as_array().into_iter().flatten() {
            let x = state["x_mm"].as_i64().unwrap_or(i64::MIN) as f32;
            let y = state["y_mm"].as_i64().unwrap_or(i64::MIN) as f32;
            out.push(Vector2::new(x, y));
        }
        out
    }
}
