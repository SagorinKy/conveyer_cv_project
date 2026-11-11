"""Controllers for the conveyor Blender scene.

Run inside Blender's Python environment. Object transforms are local to their
controller empties. Parenting preserves existing world transforms.
"""
from __future__ import annotations

import math
import bpy
from mathutils import Matrix, Euler, Vector


def _find_object(name):
    return bpy.data.objects.get(name)


def _ensure_empty(name):
    obj = _find_object(name)
    if obj is None:
        obj = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(obj)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.25
    return obj


def _parent_keep_world(child, parent):
    if child is None or child == parent:
        return
    
    bpy.context.view_layer.update()
    
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_world = world


def _set_xyz(target, value):
    if len(value) != 3:
        raise ValueError("Position/rotation must contain exactly 3 values")
    target[0], target[1], target[2] = map(float, value)


def _degrees_to_radians(values):
    return tuple(math.radians(float(v)) for v in values)


class TransformController:
    def __init__(self, obj):
        if obj is None:
            raise ValueError("Controller object was not found")
        self.object = obj

    def set_position(self, x=None, y=None, z=None):
        loc = list(self.object.location)
        for i, value in enumerate((x, y, z)):
            if value is not None:
                loc[i] = float(value)
        self.object.location = loc

    def move(self, x=0.0, y=0.0, z=0.0):
        self.object.location.x += float(x)
        self.object.location.y += float(y)
        self.object.location.z += float(z)

    def set_rotation(self, x=None, y=None, z=None):
        rot = list(self.object.rotation_euler)
        for i, value in enumerate((x, y, z)):
            if value is not None:
                rot[i] = math.radians(float(value))
        self.object.rotation_mode = "XYZ"
        self.object.rotation_euler = rot

    def rotate(self, x=0.0, y=0.0, z=0.0):
        self.object.rotation_mode = "XYZ"
        self.object.rotation_euler.x += math.radians(float(x))
        self.object.rotation_euler.y += math.radians(float(y))
        self.object.rotation_euler.z += math.radians(float(z))

    def set_scale(self, x=1.0, y=1.0, z=1.0):
        self.object.scale = (float(x), float(y), float(z))


class ConveyorController(TransformController):
    def __init__(self, obj):
        super().__init__(obj)

    def set_speed(self, speed_m_s):
        """Store nominal belt speed for experiment scripts; geometry animation
        can be added later without changing the controller interface."""
        self.speed_m_s = float(speed_m_s)


class CameraController(TransformController):
    def __init__(self, obj, camera=None):
        super().__init__(obj)
        self.camera = camera

    def set_intrinsics(self, focal_length=None, sensor_width=None,
                       sensor_height=None, resolution_x=None, resolution_y=None,
                       clip_start=None, clip_end=None, depth_of_field=None):
        if self.camera is None or self.camera.type != "CAMERA":
            raise ValueError("Virtual_Camera object is missing or is not a camera")
        data = self.camera.data
        if focal_length is not None:
            data.lens = float(focal_length)
        if sensor_width is not None:
            data.sensor_width = float(sensor_width)
        if sensor_height is not None:
            data.sensor_height = float(sensor_height)
        if clip_start is not None:
            data.clip_start = float(clip_start)
        if clip_end is not None:
            data.clip_end = float(clip_end)
        if depth_of_field is not None:
            data.dof.use_dof = bool(depth_of_field)
        data.sensor_fit = "HORIZONTAL"
        scene = bpy.context.scene
        if resolution_x is not None:
            scene.render.resolution_x = int(resolution_x)
        if resolution_y is not None:
            scene.render.resolution_y = int(resolution_y)


class LightingController(TransformController):
    def __init__(self, obj, lights):
        super().__init__(obj)
        self.lights = list(lights)

    def set_energy(self, energy, light_name=None):
        energy = float(energy)
        targets = self.lights
        if light_name:
            targets = [obj for obj in self.lights if obj.name == light_name]
            if not targets:
                raise ValueError(f"Light not found: {light_name}")
        for obj in targets:
            if obj.type == "LIGHT":
                obj.data.energy = energy


class SceneController:
    """High-level facade for the complete virtual installation."""

    def __init__(self, build_hierarchy=True):
        if build_hierarchy:
            self.build_hierarchy()

        self.root = _find_object("Scene_Controller")
        self.conveyor = ConveyorController(_find_object("Conveyor_Controller"))
        self.camera = CameraController(
            _find_object("Camera_Controller"), _find_object("Virtual_Camera")
        )
        lights = [
            obj for obj in bpy.data.objects
            if obj.type == "LIGHT" and obj.name in {"Main_Area_Light", "Fill_Light"}
        ]
        self.lighting = LightingController(
            _find_object("Lighting_Controller"), lights
        )

    def build_hierarchy(self):
        """Create/reuse root and component empties, preserving world transforms."""
        root = _ensure_empty("Scene_Controller")
        conveyor = _ensure_empty("Conveyor_Controller")
        camera = _ensure_empty("Camera_Controller")
        lighting = _ensure_empty("Lighting_Controller")

        # Reparent component controllers beneath the scene root.
        for child in (conveyor, camera, lighting):
            _parent_keep_world(child, root)

        # Attach existing conveyor parts to its controller only if they are not
        # already descendants. Known controller is preferred; otherwise use
        # the existing CONVEYOR collection as a source.
        conveyor_collection = bpy.data.collections.get("CONVEYOR")
        if conveyor_collection:
            for obj in list(conveyor_collection.all_objects):
                if obj not in (conveyor, root) and obj.parent is None:
                    _parent_keep_world(obj, conveyor)

        camera_obj = _find_object("Virtual_Camera")
        if camera_obj:
            _parent_keep_world(camera_obj, camera)

        for name in ("Main_Area_Light", "Fill_Light"):
            light = _find_object(name)
            if light:
                _parent_keep_world(light, lighting)

        # The component empties are the only direct children of Scene_Controller.
        return root

    def move(self, x=0.0, y=0.0, z=0.0):
        TransformController(self.root).move(x, y, z)

    def rotate(self, x=0.0, y=0.0, z=0.0):
        TransformController(self.root).rotate(x, y, z)

    def reset_root(self):
        self.root.location = (0.0, 0.0, 0.0)
        self.root.rotation_euler = (0.0, 0.0, 0.0)
        self.root.scale = (1.0, 1.0, 1.0)

    def update(self):
        bpy.context.view_layer.update()
