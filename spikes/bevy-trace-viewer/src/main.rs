//! Spike: show a recorded vv-lab ground-vehicle trace in 3D with Bevy. It renders only
//! recorded per-tick positions (x_mm, y_mm -> X, -Z metres); height and orientation are
//! not simulated. One recorded tick per frame; no interpolation.
//!
//! Usage: bevy_trace_viewer <trace.json> <screenshot.png>

use bevy::prelude::*;
use bevy::render::view::screenshot::{save_to_disk, Screenshot};
use std::time::Instant;

#[derive(Resource)]
struct Trace {
    states: Vec<serde_json::Value>,
    screenshot: String,
    started: Instant,
    frame: usize,
}

#[derive(Resource)]
struct GeometryJson(serde_json::Value, String);

#[derive(Component)]
struct Vehicle;

#[derive(Component)]
struct Info;

fn p(x_mm: f64, y_mm: f64, h: f32) -> Vec3 {
    Vec3::new((x_mm / 1000.0) as f32, h, -(y_mm / 1000.0) as f32)
}

fn main() {
    let started = Instant::now();
    let args: Vec<String> = std::env::args().collect();
    let text = std::fs::read_to_string(&args[1]).expect("cannot read trace");
    let trace: serde_json::Value = serde_json::from_str(&text).expect("trace is not JSON");
    let states = trace["states"].as_array().cloned().unwrap_or_default();
    App::new()
        .add_plugins(DefaultPlugins.set(WindowPlugin {
            primary_window: Some(Window {
                resolution: (1280.0_f32, 720.0_f32).into(),
                title: "vv-lab Bevy spike".into(),
                ..default()
            }),
            ..default()
        }))
        .insert_resource(Trace {
            states,
            screenshot: args[2].clone(),
            started,
            frame: 0,
        })
        .insert_resource(GeometryJson(
            trace["geometry"].clone(),
            trace["run_id"].as_str().unwrap_or("").to_string(),
        ))
        .add_systems(Startup, setup)
        .add_systems(Update, step)
        .run();
}

fn cube(
    commands: &mut Commands,
    meshes: &mut Assets<Mesh>,
    materials: &mut Assets<StandardMaterial>,
    size: Vec3,
    pos: Vec3,
    color: Color,
) -> Entity {
    commands
        .spawn((
            Mesh3d(meshes.add(Cuboid::new(size.x, size.y, size.z))),
            MeshMaterial3d(materials.add(StandardMaterial {
                base_color: color,
                ..default()
            })),
            Transform::from_translation(pos),
        ))
        .id()
}

fn setup(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    geometry: Res<GeometryJson>,
    trace: Res<Trace>,
) {
    let g = &geometry.0;
    let b = &g["bounds"];
    let f = |v: &serde_json::Value| v.as_f64().unwrap_or(0.0);
    let (x0, x1, y0, y1) = (
        f(&b["min_x_mm"]),
        f(&b["max_x_mm"]),
        f(&b["min_y_mm"]),
        f(&b["max_y_mm"]),
    );
    cube(
        &mut commands,
        &mut meshes,
        &mut materials,
        Vec3::new(
            ((x1 - x0) / 1000.0) as f32,
            0.02,
            ((y1 - y0) / 1000.0) as f32,
        ),
        p((x0 + x1) / 2.0, (y0 + y1) / 2.0, -0.01),
        Color::srgb(0.22, 0.24, 0.26),
    );
    if let Some(zone) = g["restricted_zone"].as_array() {
        let xs: Vec<f64> = zone.iter().map(|q| f(&q["x_mm"])).collect();
        let ys: Vec<f64> = zone.iter().map(|q| f(&q["y_mm"])).collect();
        let (zx0, zx1) = (
            xs.iter().cloned().fold(f64::MAX, f64::min),
            xs.iter().cloned().fold(f64::MIN, f64::max),
        );
        let (zy0, zy1) = (
            ys.iter().cloned().fold(f64::MAX, f64::min),
            ys.iter().cloned().fold(f64::MIN, f64::max),
        );
        cube(
            &mut commands,
            &mut meshes,
            &mut materials,
            Vec3::new(
                ((zx1 - zx0) / 1000.0) as f32,
                0.3,
                ((zy1 - zy0) / 1000.0) as f32,
            ),
            p((zx0 + zx1) / 2.0, (zy0 + zy1) / 2.0, 0.15),
            Color::srgb(0.8, 0.2, 0.2),
        );
    }
    for wp in g["waypoints"].as_array().into_iter().flatten() {
        cube(
            &mut commands,
            &mut meshes,
            &mut materials,
            Vec3::new(0.2, 0.6, 0.2),
            p(f(&wp["x_mm"]), f(&wp["y_mm"]), 0.3),
            Color::srgb(0.2, 0.8, 0.4),
        );
    }
    let start = &g["start"];
    let v = cube(
        &mut commands,
        &mut meshes,
        &mut materials,
        Vec3::new(0.4, 0.25, 0.3),
        p(f(&start["x_mm"]), f(&start["y_mm"]), 0.125),
        Color::srgb(0.25, 0.55, 0.95),
    );
    commands.entity(v).insert(Vehicle);
    commands.spawn((
        DirectionalLight {
            illuminance: 8000.0,
            ..default()
        },
        Transform::from_rotation(Quat::from_euler(EulerRot::XYZ, -1.0, 0.5, 0.0)),
    ));
    commands.spawn((
        Camera3d::default(),
        Transform::from_xyz(3.5, 6.0, 2.5).looking_at(Vec3::new(3.5, 0.0, -2.5), Vec3::Y),
    ));
    commands.spawn((
        Text::new(""),
        Info,
        Node {
            position_type: PositionType::Absolute,
            top: Val::Px(12.0),
            left: Val::Px(16.0),
            ..default()
        },
    ));
    commands.spawn((
        Text::new(format!(
            "2D kinematic model shown in 3D: positions are recorded integer mm on a plane; height, orientation and dynamics are NOT simulated. Run {}.",
            geometry.1
        )),
        TextFont { font_size: 16.0, ..default() },
        Node { position_type: PositionType::Absolute, bottom: Val::Px(12.0), left: Val::Px(16.0), ..default() },
    ));
    println!(
        "SPIKE setup_ms={} ticks={}",
        trace.started.elapsed().as_millis(),
        trace.states.len()
    );
}

fn step(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut trace: ResMut<Trace>,
    mut vehicle: Query<&mut Transform, With<Vehicle>>,
    mut info: Query<&mut Text, With<Info>>,
    mut exit: EventWriter<AppExit>,
) {
    let frame = trace.frame;
    trace.frame += 1;
    if frame == 0 {
        println!(
            "SPIKE first_frame_ms={}",
            trace.started.elapsed().as_millis()
        );
    }
    // Hold on the 8th recorded tick for HOLD frames: Bevy compiles pipelines asynchronously,
    // so early frames can render nothing. The screenshot is taken during the hold.
    const HOLD: usize = 90;
    let i = if frame < 8 {
        frame
    } else if frame < 8 + HOLD {
        usize::MAX
    } else {
        frame - HOLD
    };
    if frame == 8 + HOLD - 10 {
        let path = trace.screenshot.clone();
        commands
            .spawn(Screenshot::primary_window())
            .observe(save_to_disk(path));
    }
    if i == usize::MAX {
        return;
    }
    if i < trace.states.len() {
        let s = trace.states[i].clone();
        let n = |k: &str| s[k].as_f64().unwrap_or(0.0);
        if n("x_mm") != n("from_x_mm") || n("y_mm") != n("from_y_mm") {
            let a = p(n("from_x_mm"), n("from_y_mm"), 0.03);
            let e = p(n("x_mm"), n("y_mm"), 0.03);
            let fallback = s["safety_state"] == "fallback";
            cube(
                &mut commands,
                &mut meshes,
                &mut materials,
                Vec3::new(
                    (e.x - a.x).abs().max(0.05),
                    0.04,
                    (e.z - a.z).abs().max(0.05),
                ),
                (a + e) / 2.0,
                if fallback {
                    Color::srgb(0.95, 0.5, 0.2)
                } else {
                    Color::srgb(0.3, 0.6, 1.0)
                },
            );
        }
        let pos = p(n("x_mm"), n("y_mm"), 0.125);
        for mut t in &mut vehicle {
            t.translation = pos;
            // Fidelity check: rendered position mapped back to millimetres.
            println!(
                "SPIKE tick={} rendered_mm={},{}",
                s["tick"],
                (t.translation.x * 1000.0).round() as i64,
                (-t.translation.z * 1000.0).round() as i64
            );
        }
        for mut text in &mut info {
            text.0 = format!(
                "tick {}  safety {}  position ({}, {}) mm",
                s["tick"],
                s["safety_state"].as_str().unwrap_or("?"),
                n("x_mm"),
                n("y_mm")
            );
        }
    } else if i > trace.states.len() + 20 {
        println!("SPIKE done_ms={}", trace.started.elapsed().as_millis());
        exit.write(AppExit::Success);
    }
}
