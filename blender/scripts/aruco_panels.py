"""Размещение ArUco-панелей на конвейере (Blender Python).

Публичный интерфейс:
    create_tracking_boards(conveyor_root, assets_dir) -> {role: object}
    find_tracking_boards()                            -> {role: object}
    remove_tracking_boards()
"""
from pathlib import Path
import math
import bpy
from mathutils import Vector

# Панель = сетка 2x2 маркеров (50 мм, зазор 10 мм) + белая рамка 10 мм.
# Должно совпадать с tools/generate_aruco_boards.py.
BOARD_SIZE = 0.130

# Панели стоят на бортах конвейера лицом к камере (нормаль -Y):
#   front_* - на ВНЕШНЕЙ грани ближнего борта (Side_Rail_-1);
#   rear_*  - на ВНУТРЕННЕЙ грани дальнего борта (Side_Rail_1): её камера
#             видит выше ленты, поэтому борта приподняты (rail_top_above_belt).
# x - положение вдоль борта от его центра, м. Две плоскости на разной глубине
# (разница ~0.86 м) дают точную оценку наклона и расстояния.
BOARDS = {
    "front_left":  {"rail": "Side_Rail_-1", "x": -0.70},
    "front_right": {"rail": "Side_Rail_-1", "x":  0.70},
    "rear_left":   {"rail": "Side_Rail_1",  "x": -0.70},
    "rear_right":  {"rail": "Side_Rail_1",  "x":  0.70},
}
SURFACE_OFFSET = 0.002   # зазор над поверхностью против z-fighting
BELT_MESH_NAME = "Conveyor_Belt"   # нужна только для высоты ленты


# --------------------------------------------------------------------------
# Поиск / удаление уже существующих панелей
# --------------------------------------------------------------------------
def _is_board(obj):
    return bool(obj.get("tracking_board"))


def find_tracking_boards():
    """Найти панели, которые уже лежат в открытой сцене (по custom property)."""
    found = {o["board_role"]: o for o in bpy.data.objects if _is_board(o)}
    return {role: found[role] for role in BOARDS if role in found}


def remove_tracking_boards():
    """Удалить панели вместе с их mesh / материалами / картинками."""
    for obj in [o for o in bpy.data.objects if _is_board(o)]:
        mesh = obj.data
        materials = [m for m in (mesh.materials if mesh else []) if m]
        images = [
            n.image for m in materials if m.node_tree
            for n in m.node_tree.nodes
            if n.type == "TEX_IMAGE" and n.image
        ]
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        for m in materials:
            if m.users == 0:
                bpy.data.materials.remove(m)
        for img in images:
            if img.users == 0:
                bpy.data.images.remove(img)


# --------------------------------------------------------------------------
# Геометрия
# --------------------------------------------------------------------------
def mesh_bounds_in_frame(target, frame):
    """Габариты target (и его mesh-потомков, кроме панелей) в локальных
    координатах объекта frame."""
    bpy.context.view_layer.update()
    inv = frame.matrix_world.inverted()
    meshes = ([target] if target.type == "MESH" else [])
    meshes += [
        o for o in target.children_recursive
        if o.type == "MESH" and not _is_board(o)
    ]
    points = [
        inv @ (obj.matrix_world @ Vector(corner))
        for obj in meshes for corner in obj.bound_box
    ]
    if not points:
        raise RuntimeError(f"Не найдена mesh-геометрия у {target.name}")
    return (
        min(p.x for p in points), max(p.x for p in points),
        min(p.y for p in points), max(p.y for p in points),
        min(p.z for p in points), max(p.z for p in points),
    )


def make_emission_material(name, image_path):
    image = bpy.data.images.load(str(image_path))
    image.pack()  # картинка хранится внутри .blend: сцену можно переносить
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.interpolation = "Closest"
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 1.0
    output = nodes.new("ShaderNodeOutputMaterial")
    links.new(tex.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return mat


def create_plane(name, image_path, parent, local_position):
    h = BOARD_SIZE / 2
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(
        [(-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0)],
        [], [(0, 1, 2, 3)]
    )
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    coords = [(0, 0), (1, 0), (1, 1), (0, 1)]
    for loop in mesh.loops:
        uv.data[loop.index].uv = coords[loop.vertex_index]

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(make_emission_material(name + "_Material", image_path))
    obj.parent = parent
    obj.location = local_position
    # Вертикальная панель: нормаль -Y (к камере), верх картинки - вверх (+Z).
    obj.rotation_euler = (math.radians(90), 0.0, 0.0)
    obj["tracking_board"] = True
    obj["board_size_m"] = BOARD_SIZE
    return obj


def create_tracking_boards(conveyor_root, assets_dir):
    """Создать (или пересоздать) панели на бортах. Повторный вызов безопасен."""
    assets_dir = Path(assets_dir)

    images = {}
    for role in BOARDS:
        image = assets_dir / f"board_{role}.png"
        if not image.exists():
            raise FileNotFoundError(
                f"Нет {image}; сначала: python main.py generate-aruco"
            )
        images[role] = image

    rails = {}
    for role, spec in BOARDS.items():
        rail = bpy.data.objects.get(spec["rail"])
        if rail is None:
            raise RuntimeError(
                f"В сцене нет {spec['rail']}; пересоздай сцену: python main.py scene"
            )
        rails[role] = rail
    belt = bpy.data.objects.get(BELT_MESH_NAME)
    if belt is None:
        raise RuntimeError(f"В сцене нет {BELT_MESH_NAME}; пересоздай сцену")

    # Старые панели убираем до расчёта габаритов.
    remove_tracking_boards()

    belt_top = mesh_bounds_in_frame(belt, conveyor_root)[5]
    half = BOARD_SIZE / 2
    result = {}

    for role, spec in BOARDS.items():
        rail = rails[role]
        xmin, xmax, ymin, ymax, zmin, zmax = mesh_bounds_in_frame(rail, conveyor_root)

        # Панель занимает полосу между верхом ленты и верхом борта,
        # чтобы одинаково помещаться на ближнем и на дальнем борту.
        if zmax - belt_top < BOARD_SIZE:
            raise RuntimeError(
                f"Борт выступает над лентой всего на {zmax - belt_top:.3f} м, "
                f"а панель {BOARD_SIZE:.3f} м. Увеличь rail_top_above_belt "
                f"в config/scene.json (рекомендуется 0.17) и пересоздай сцену."
            )
        z = (belt_top + zmax) / 2
        x = (xmin + xmax) / 2 + spec["x"]
        if not (xmin + half <= x <= xmax - half):
            raise RuntimeError(f"Панель {role} (x={x:.3f}) не помещается на борт")

        # -Y грань борта: у ближнего - внешняя, у дальнего - внутренняя.
        y = ymin - SURFACE_OFFSET

        world_point = conveyor_root.matrix_world @ Vector((x, y, z))
        parent_point = rail.matrix_world.inverted() @ world_point
        obj = create_plane(f"ArUco_Board_{role}", images[role], rail, parent_point)
        obj["board_role"] = role
        result[role] = obj
        print(f"  {role}: rail={rail.name} x={x:.3f} y={y:.3f} z={z:.3f}")

    bpy.context.view_layer.update()
    print(f"{len(result)} boards of {BOARD_SIZE:.3f} m placed; belt top Z={belt_top:.3f}")
    return result
