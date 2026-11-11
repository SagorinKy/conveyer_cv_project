"""Render a deterministic frame sequence and Ground Truth from a .blend scene.

Example (PowerShell, from project root):
  & "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" `
    --background "blender\\scenes\\conveyor.blend" `
    --python "blender\\scripts\\run_experiment.py" `
    -- --config "config\\experiment.json"

The script writes PNG frames and ground_truth.json under results/.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
import csv

import bpy
from mathutils import Vector

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from scene_controller import SceneController
from aruco_panels import find_tracking_boards
from motion import Vibration


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def world_pose(obj):
    bpy.context.view_layer.update()
    loc = obj.matrix_world.translation
    rot = obj.matrix_world.to_euler("XYZ")
    return {
        "position_m": [float(v) for v in loc],
        "rotation_rad": [float(v) for v in rot],
        "rotation_deg": [float(math.degrees(v)) for v in rot],
    }


def camera_intrinsics(camera_obj, scene):
    data = camera_obj.data
    width = scene.render.resolution_x * scene.render.resolution_percentage / 100.0
    height = scene.render.resolution_y * scene.render.resolution_percentage / 100.0

    # The selected sensor and render resolutions have matching 1.6 aspect ratios.
    # With HORIZONTAL sensor fit, both focal lengths are computed from their
    # corresponding physical sensor dimensions.
    fx = data.lens * width / data.sensor_width
    fy = data.lens * height / data.sensor_height
    cx = width / 2.0
    cy = height / 2.0

    return {
        "fx": float(fx), "fy": float(fy), "cx": float(cx), "cy": float(cy),
        "K": [[float(fx), 0.0, float(cx)],
              [0.0, float(fy), float(cy)],
              [0.0, 0.0, 1.0]],
        "resolution": [int(width), int(height)],
        "focal_length_mm": float(data.lens),
        "sensor_width_mm": float(data.sensor_width),
        "sensor_height_mm": float(data.sensor_height),
    }


def apply_scene_camera_config(scene_config, controller):
    """Apply camera settings from config/scene.json to the opened .blend.

    `controller` is the SceneController; camera settings go to controller.camera.
    """
    camera_cfg = scene_config["camera"]
    sensor_cfg = camera_cfg["sensor"]
    lens_cfg = camera_cfg["lens"]

    cam_ctrl = controller.camera          # CameraController (empty + camera)
    cam_ctrl.object.location = camera_cfg.get(
        "controller_position", [0.0, 0.0, 0.0]
    )
    cam_ctrl.object.rotation_mode = "XYZ"
    cam_ctrl.object.rotation_euler = [
        math.radians(float(v))
        for v in camera_cfg.get("controller_rotation", [0.0, 0.0, 0.0])
    ]

    camera_obj = cam_ctrl.camera          # bpy camera object
    camera_obj.location = camera_cfg["position"]
    direction = Vector(camera_cfg["target"]) - camera_obj.location
    camera_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    cam_ctrl.set_intrinsics(
        focal_length=lens_cfg["focal_length_mm"],
        sensor_width=sensor_cfg["width_mm"],
        sensor_height=sensor_cfg["height_mm"],
        resolution_x=camera_cfg["resolution"][0],
        resolution_y=camera_cfg["resolution"][1],
        clip_start=camera_cfg.get("clip_start", 0.01),
        clip_end=camera_cfg.get("clip_end", 100.0),
        depth_of_field=camera_cfg.get("depth_of_field", False),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/experiment.json")
    args, _unknown = parser.parse_known_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    config_path = (PROJECT_ROOT / args.config).resolve()
    cfg = load_json(config_path)

    scene_config_path = PROJECT_ROOT / "config" / "scene.json"
    scene_config = load_json(scene_config_path)

    controller = SceneController(build_hierarchy=True)
    scene = bpy.context.scene

    # Re-apply camera settings from scene.json, so the experiment does not
    # depend on stale camera values saved in conveyor.blend.
    apply_scene_camera_config(scene_config, controller)

    # ArUco-панели добавляются отдельной командой (python main.py aruco).
    # Здесь мы их только находим в открытой сцене.
    tracking_boards = find_tracking_boards()
    belt_obj = bpy.data.objects.get("Belt_Controller")
    if not tracking_boards:
        print("WARNING: в сцене нет ArUco-панелей. Запусти: python main.py aruco")

    fps = int(cfg.get("fps", scene.render.fps))
    duration_s = float(cfg.get("duration_s", 5.0))
    frame_count = max(1, int(round(fps * duration_s)))
    start_frame = int(cfg.get("start_frame", 1))
    seed = int(cfg.get("seed", 42))

    scene.render.fps = fps
    scene.frame_start = start_frame
    scene.frame_end = start_frame + frame_count - 1

    output_dir = (PROJECT_ROOT / cfg.get("output_dir", "results/experiment")).resolve()
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    base = {
        "scene": {
            "location": controller.root.location.copy(),
            "rotation": controller.root.rotation_euler.copy(),
        },
        "conveyor": {
            "location": controller.conveyor.object.location.copy(),
            "rotation": controller.conveyor.object.rotation_euler.copy(),
        },
        "camera": {
            "location": controller.camera.object.location.copy(),
            "rotation": controller.camera.object.rotation_euler.copy(),
        },
    }

    motion_cfg = cfg.get("motion", {})
    vibration_cfg = cfg.get("vibration", {})
    vibrations = {
        "scene": Vibration.from_dict(vibration_cfg.get("scene", {})),
        "conveyor": Vibration.from_dict(vibration_cfg.get("conveyor", {})),
        "camera": Vibration.from_dict(vibration_cfg.get("camera", {})),
    }

    # Linear velocities are in metres/second and angular velocities in degrees/second.
    velocities = {
        "scene": motion_cfg.get("scene_velocity_m_s", [0, 0, 0]),
        "conveyor": motion_cfg.get("conveyor_velocity_m_s", [0, 0, 0]),
        "camera": motion_cfg.get("camera_velocity_m_s", [0, 0, 0]),
    }
    angular = {
        "scene": motion_cfg.get("scene_angular_velocity_deg_s", [0, 0, 0]),
        "conveyor": motion_cfg.get("conveyor_angular_velocity_deg_s", [0, 0, 0]),
        "camera": motion_cfg.get("camera_angular_velocity_deg_s", [0, 0, 0]),
    }
    targets = {
        "scene": controller.root,
        "conveyor": controller.conveyor.object,
        "camera": controller.camera.object,
    }

    ground_truth = {
        "metadata": {
            "fps": fps, "duration_s": duration_s, "frame_count": frame_count,
            "seed": seed, "config": str(config_path),
            "scene_config": str(scene_config_path),
            "camera_model": scene_config["camera"].get("model"),
            "sensor_model": scene_config["camera"]["sensor"].get("model"),
            "lens_model": scene_config["camera"]["lens"].get("model"),
            "note": "Positions are world-space metres; rotations are XYZ Euler."
        },
        "frames": []
    }

    # Combine global seed with each configured vibration seed.
    for vib in vibrations.values():
        vib.seed += seed
    
    for index in range(frame_count):
        frame = start_frame + index
        time_s = index / float(fps)
        scene.frame_set(frame)

        for key, obj in targets.items():
            base_loc = base[key]["location"]
            base_rot = base[key]["rotation"]
            vib = vibrations[key]
            offset = vib.offset(time_s, index)
            velocity = velocities[key]
            angular_velocity = angular[key]

            obj.location = (
                base_loc.x + float(velocity[0]) * time_s + offset[0],
                base_loc.y + float(velocity[1]) * time_s + offset[1],
                base_loc.z + float(velocity[2]) * time_s + offset[2],
            )
            obj.rotation_mode = "XYZ"
            obj.rotation_euler = (
                base_rot.x + math.radians(float(angular_velocity[0])) * time_s,
                base_rot.y + math.radians(float(angular_velocity[1])) * time_s,
                base_rot.z + math.radians(float(angular_velocity[2])) * time_s,
            )

        controller.update()
        bpy.context.view_layer.update()
        board_poses = {
            name: world_pose(obj)
            for name, obj in tracking_boards.items()
        }
        scene.camera = controller.camera.camera
        scene.render.filepath = str(frames_dir / f"frame_{frame:06d}.png")
        bpy.ops.render.render(write_still=True)

        ground_truth["frames"].append({
            "frame": frame,
            "time_s": time_s,
            "scene": world_pose(controller.root),
            "conveyor": world_pose(controller.conveyor.object),
            "camera_controller": world_pose(controller.camera.object),
            "camera": world_pose(controller.camera.camera),
            "camera_intrinsics": camera_intrinsics(controller.camera.camera, scene),
            "belt": world_pose(belt_obj) if belt_obj else None,
            "tracking_boards": board_poses,
        })


    if tracking_boards:
        csv_path = output_dir / "aruco_ground_truth.csv"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            fields = [
                "frame", "time_s", "board",
                "x_m", "y_m", "z_m",
                "rx_rad", "ry_rad", "rz_rad",
                "rx_deg", "ry_deg", "rz_deg"
            ]
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for frame_data in ground_truth["frames"]:
                for board_name, pose in frame_data["tracking_boards"].items():
                    writer.writerow({
                        "frame": frame_data["frame"],
                        "time_s": frame_data["time_s"],
                        "board": board_name,
                        "x_m": pose["position_m"][0],
                        "y_m": pose["position_m"][1],
                        "z_m": pose["position_m"][2],
                        "rx_rad": pose["rotation_rad"][0],
                        "ry_rad": pose["rotation_rad"][1],
                        "rz_rad": pose["rotation_rad"][2],
                        "rx_deg": pose["rotation_deg"][0],
                        "ry_deg": pose["rotation_deg"][1],
                        "rz_deg": pose["rotation_deg"][2],
                    })
        print(f"ArUco Ground Truth CSV: {csv_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    gt_path = output_dir / "ground_truth.json"
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, ensure_ascii=False, indent=2)

    print(f"Experiment complete: {frame_count} frames")
    print(f"Frames: {frames_dir}")
    print(f"Ground Truth: {gt_path}")


if __name__ == "__main__":
    main()
