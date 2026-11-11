
import bpy
import json
import math
import sys

from pathlib import Path
from mathutils import Vector, Matrix


# ==================================================
# 1. PATHS AND CONFIGURATION
# ==================================================

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from scene_controller import SceneController

CONFIG_PATH = PROJECT_ROOT / "config" / "scene.json"

SCENE_PATH = PROJECT_ROOT / "blender" / "scenes" / "conveyor.blend"

IMAGE_PATH = (
    PROJECT_ROOT / "results" / "images" / "conveyor_preview.png"
)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


config = load_config()


# ==================================================
# 2. COLLECTIONS
# ==================================================

def create_collection(name):
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def move_to_collection(obj, collection):
    for old_collection in list(obj.users_collection):
        old_collection.objects.unlink(obj)

    collection.objects.link(obj)


# ==================================================
# 3. MATERIALS
# ==================================================

def create_material(
    name,
    color,
    metallic=0.0,
    roughness=0.5
):
    material = bpy.data.materials.new(name)

    material.diffuse_color = (*color, 1.0)

    principled = material.node_tree.nodes.get(
        "Principled BSDF"
    )

    if principled is None:
        principled = material.node_tree.nodes.new(
            "ShaderNodeBsdfPrincipled"
        )

        output = material.node_tree.nodes.get(
            "Material Output"
        )

        if output is None:
            output = material.node_tree.nodes.new(
                "ShaderNodeOutputMaterial"
            )

        material.node_tree.links.new(
            principled.outputs["BSDF"],
            output.inputs["Surface"]
        )

    principled.inputs["Base Color"].default_value = (
        *color, 1.0
    )

    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = roughness

    return material


# ==================================================
# 4. CONTROLLERS
# ==================================================

def create_controller(name, collection):
    controller = bpy.data.objects.new(name, None)

    controller.empty_display_type = "PLAIN_AXES"
    controller.empty_display_size = 0.3

    collection.objects.link(controller)

    return controller


def parent_object(obj, parent):
    obj.parent = parent

    # Preserve local coordinates.
    obj.matrix_parent_inverse = Matrix.Identity(4)


def set_transform(obj, position, rotation):
    obj.location = position

    obj.rotation_euler = [
        math.radians(angle)
        for angle in rotation
    ]


# ==================================================
# 5. GEOMETRY HELPERS
# ==================================================

def create_cube(
    name,
    location,
    dimensions,
    material,
    collection,
    parent=None,
    bevel=0.01
):
    bpy.ops.mesh.primitive_cube_add(
        size=1,
        location=location
    )

    obj = bpy.context.object
    obj.name = name

    obj.dimensions = dimensions

    bpy.ops.object.transform_apply(
        location=False,
        rotation=False,
        scale=True
    )

    obj.data.materials.append(material)

    if bevel > 0:
        modifier = obj.modifiers.new(
            name="Edge_Bevel",
            type="BEVEL"
        )

        modifier.width = bevel
        modifier.segments = 3

        normal_modifier = obj.modifiers.new(
            name="Weighted_Normals",
            type="WEIGHTED_NORMAL"
        )

    move_to_collection(obj, collection)

    if parent is not None:
        parent_object(obj, parent)

    return obj


def create_roller(
    name,
    location,
    radius,
    width,
    material,
    collection,
    parent,
    segments=48
):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=segments,
        radius=radius,
        depth=width,
        location=location,
        rotation=(math.radians(90), 0, 0)
    )

    obj = bpy.context.object
    obj.name = name

    obj.data.materials.append(material)

    bevel = obj.modifiers.new(
        name="Roller_Bevel",
        type="BEVEL"
    )

    bevel.width = 0.008
    bevel.segments = 3

    obj.modifiers.new(
        name="Weighted_Normals",
        type="WEIGHTED_NORMAL"
    )

    move_to_collection(obj, collection)
    parent_object(obj, parent)

    return obj


# ==================================================
# 6. CONVEYOR MODEL
# ==================================================

def create_conveyor(
    conveyor_config,
    collection
):
    length = conveyor_config["length"]
    width = conveyor_config["width"]
    height = conveyor_config["height"]

    belt_thickness = conveyor_config["belt_thickness"]

    rail_width = conveyor_config["rail_width"]
    rail_height = conveyor_config["rail_height"]

    leg_width = conveyor_config["leg_width"]

    roller_radius = conveyor_config["roller_radius"]

    # Materials
    belt_material = create_material(
        "Belt_Material",
        conveyor_config["belt_color"],
        roughness=0.85
    )

    frame_material = create_material(
        "Frame_Material",
        conveyor_config["frame_color"],
        metallic=0.75,
        roughness=0.3
    )

    roller_material = create_material(
        "Roller_Material",
        (0.35, 0.38, 0.42),
        metallic=0.8,
        roughness=0.25
    )

    # Main controller
    conveyor_controller = create_controller(
        "Conveyor_Controller",
        collection
    )

    # Independent belt controller
    belt_controller = create_controller(
        "Belt_Controller",
        collection
    )

    parent_object(
        belt_controller,
        conveyor_controller
    )

    # ----------------------------------------------
    # Conveyor belt
    # ----------------------------------------------

    belt_center_z = height - belt_thickness / 2

    create_cube(
        "Conveyor_Belt",
        (0, 0, belt_center_z),
        (length, width, belt_thickness),
        belt_material,
        collection,
        parent=belt_controller,
        bevel=0.005
    )

    # ----------------------------------------------
    # Rollers
    # ----------------------------------------------

    roller_width = width + 0.02

    roller_x = length / 2 - roller_radius

    for side in [-1, 1]:
        create_roller(
            f"Roller_{side}",
            (
                side * roller_x,
                0,
                height - roller_radius
            ),
            roller_radius,
            roller_width,
            roller_material,
            collection,
            belt_controller,
            conveyor_config["roller_segments"]
        )

    # ----------------------------------------------
    # Side rails
    # ----------------------------------------------

    # rail_top_above_belt: на сколько верх борта выше верха ленты.
    # Нужен, чтобы внутренняя грань дальнего борта была видна камере
    # (на ней стоят ArUco-панели). Без параметра - прежняя геометрия.
    rail_top_above_belt = conveyor_config.get("rail_top_above_belt")
    if rail_top_above_belt is None:
        rail_z = height - rail_height / 4
    else:
        rail_z = height + float(rail_top_above_belt) - rail_height / 2

    for side in [-1, 1]:
        create_cube(
            f"Side_Rail_{side}",
            (
                0,
                side * (width / 2 + rail_width / 2),
                rail_z
            ),
            (
                length,
                rail_width,
                rail_height
            ),
            frame_material,
            collection,
            parent=conveyor_controller,
            bevel=0.012
        )

    # ----------------------------------------------
    # Frame legs
    # ----------------------------------------------

    frame_bottom = 0.0
    frame_top = height - belt_thickness

    leg_height = frame_top - frame_bottom

    leg_positions_x = [
        -length * 0.4,
        length * 0.4
    ]

    leg_positions_y = [
        -width * 0.4,
        width * 0.4
    ]

    leg_number = 1

    for x in leg_positions_x:
        for y in leg_positions_y:
            create_cube(
                f"Frame_Leg_{leg_number}",
                (
                    x,
                    y,
                    frame_bottom + leg_height / 2
                ),
                (
                    leg_width,
                    leg_width,
                    leg_height
                ),
                frame_material,
                collection,
                parent=conveyor_controller,
                bevel=0.008
            )

            leg_number += 1

    # ----------------------------------------------
    # Longitudinal frame beams
    # ----------------------------------------------

    beam_z = height * 0.48

    for side in [-1, 1]:
        create_cube(
            f"Frame_Long_Beam_{side}",
            (
                0,
                side * width * 0.4,
                beam_z
            ),
            (
                length * 0.92,
                0.07,
                0.08
            ),
            frame_material,
            collection,
            parent=conveyor_controller
        )

    # ----------------------------------------------
    # Cross beams
    # ----------------------------------------------

    for index, x in enumerate(
        [-length * 0.35, length * 0.35],
        start=1
    ):
        create_cube(
            f"Frame_Cross_Beam_{index}",
            (
                x,
                0,
                beam_z
            ),
            (
                0.07,
                width * 0.85,
                0.08
            ),
            frame_material,
            collection,
            parent=conveyor_controller
        )

    # Apply conveyor transform
    set_transform(
        conveyor_controller,
        conveyor_config["position"],
        conveyor_config["rotation"]
    )

    return conveyor_controller, belt_controller


# ==================================================
# 7. CAMERA
# ==================================================

def create_camera(
    camera_config,
    collection
):
    controller = create_controller(
        "Camera_Controller",
        collection
    )

    camera_data = bpy.data.cameras.new(
        "Virtual_Camera_Data"
    )

    camera = bpy.data.objects.new(
        "Virtual_Camera",
        camera_data
    )

    collection.objects.link(camera)

    parent_object(camera, controller)

    # Controller transform is separate from the camera's local pose.
    set_transform(
        controller,
        camera_config.get("controller_position", [0.0, 0.0, 0.0]),
        camera_config.get("controller_rotation", [0.0, 0.0, 0.0])
    )

    camera.location = camera_config["position"]

    # Aim at target in the camera-controller's local coordinate system.
    direction = Vector(camera_config["target"]) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    # Optical parameters: new nested config schema.
    sensor = camera_config["sensor"]
    lens = camera_config["lens"]

    camera_data.lens = float(lens["focal_length_mm"])
    camera_data.sensor_width = float(sensor["width_mm"])
    camera_data.sensor_height = float(sensor["height_mm"])
    camera_data.sensor_fit = "HORIZONTAL"

    camera_data.clip_start = float(camera_config.get("clip_start", 0.01))
    camera_data.clip_end = float(camera_config.get("clip_end", 100.0))

    camera_data.dof.use_dof = bool(camera_config.get("depth_of_field", False))

    bpy.context.scene.camera = camera

    return controller, camera


# ==================================================
# 8. ENVIRONMENT
# ==================================================

def create_environment(
    environment_config,
    collection
):
    floor_material = create_material(
        "Floor_Material",
        (0.32, 0.34, 0.37),
        roughness=0.8
    )

    create_cube(
        "Environment_Floor",
        (
            0,
            0,
            environment_config["floor_height"]
        ),
        (
            environment_config["floor_size"],
            environment_config["floor_size"],
            0.1
        ),
        floor_material,
        collection,
        bevel=0
    )


def create_lighting(collection):
    light_data = bpy.data.lights.new(
        name="Main_Area_Light",
        type="AREA"
    )

    light = bpy.data.objects.new(
        name="Main_Area_Light",
        object_data=light_data
    )

    collection.objects.link(light)

    light.location = (0, -1.5, 3.5)

    light_data.energy = 450
    light_data.shape = "DISK"
    light_data.size = 3.0

    # Additional fill light
    fill_data = bpy.data.lights.new(
        name="Fill_Light",
        type="AREA"
    )

    fill = bpy.data.objects.new(
        name="Fill_Light",
        object_data=fill_data
    )

    collection.objects.link(fill)

    fill.location = (1.5, 1.5, 2.5)

    fill_data.energy = 200
    fill_data.size = 2.5


# ==================================================
# 9. RENDER SETTINGS
# ==================================================

def configure_render(config):
    scene = bpy.context.scene

    scene.render.engine = config["render"]["engine"]

    camera = config["camera"]

    scene.render.resolution_x = camera["resolution"][0]
    scene.render.resolution_y = camera["resolution"][1]

    scene.render.resolution_percentage = (
        config["render"]["resolution_percentage"]
    )

    # FPS is an experiment/output parameter and is set by run_experiment.py.
    # Keep a sensible default in the saved scene; experiment.json overrides it.
    scene.render.fps = int(config.get("render", {}).get("default_fps", 30))

    scene.render.image_settings.file_format = config["render"].get("image_format", "PNG")
    scene.render.image_settings.color_mode = "RGB"

    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    scene.render.image_settings.color_depth = "8"

    scene.world.color = (0.25, 0.25, 0.25)

    # EEVEE sampling
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = (
            config["render"]["samples"]
        )


# ==================================================
# 10. BUILD SCENE
# ==================================================

def main():
    # Remove previous scene objects and collections
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    for collection in list(bpy.data.collections):
        if collection.users == 0:
            bpy.data.collections.remove(collection)

    scene = bpy.context.scene

    conveyor_collection = create_collection(
        "CONVEYOR"
    )

    camera_collection = create_collection(
        "CAMERA"
    )

    environment_collection = create_collection(
        "ENVIRONMENT"
    )

    # Build components
    conveyor_controller, belt_controller = create_conveyor(
        config["conveyor"],
        conveyor_collection
    )

    camera_controller, camera = create_camera(
        config["camera"],
        camera_collection
    )

    create_environment(
        config["environment"],
        environment_collection
    )

    create_lighting(environment_collection)

    configure_render(config)

    # Иерархия Scene_Controller -> Conveyor/Camera/Lighting строится здесь,
    # чтобы сохранённая сцена была полной, а add_aruco / run_experiment
    # только открывали её.
    bpy.context.view_layer.update()
    SceneController(build_hierarchy=True)

    # Save scene
    SCENE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    IMAGE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    scene.render.filepath = str(IMAGE_PATH)

    bpy.ops.wm.save_as_mainfile(
        filepath=str(SCENE_PATH)
    )

    # Render preview
    bpy.ops.render.render(write_still=True)

    print("\n===================================")
    print("CONVEYOR SCENE CREATED SUCCESSFULLY")
    print("===================================")

    print(f"Scene: {SCENE_PATH}")
    print(f"Image: {IMAGE_PATH}")

    print("Controllers:")
    print(f" - {conveyor_controller.name}")
    print(f" - {belt_controller.name}")
    print(f" - {camera_controller.name}")

    print("===================================\n")


if __name__ == "__main__":
    main()