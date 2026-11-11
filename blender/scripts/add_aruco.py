"""КОМАНДА 2: добавить ArUco-панели в уже созданную сцену conveyor.blend.

Запуск (из корня проекта):  python main.py aruco
Или напрямую:
  blender --background blender/scenes/conveyor.blend --python blender/scripts/add_aruco.py

Скрипт можно запускать повторно: старые панели заменяются новыми.
"""
import sys
from pathlib import Path

import bpy

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from scene_controller import SceneController
from aruco_panels import create_tracking_boards

ASSETS_DIR = PROJECT_ROOT / "blender" / "assets" / "aruco"
SCENE_PATH = PROJECT_ROOT / "blender" / "scenes" / "conveyor.blend"
PREVIEW_PATH = PROJECT_ROOT / "results" / "images" / "conveyor_aruco_preview.png"


def main():
    # Если Blender запущен без .blend в аргументах — открываем сцену сами.
    if not bpy.data.filepath:
        if not SCENE_PATH.exists():
            raise FileNotFoundError(
                f"Нет {SCENE_PATH}; сначала: python main.py scene"
            )
        bpy.ops.wm.open_mainfile(filepath=str(SCENE_PATH))

    controller = SceneController(build_hierarchy=True)
    boards = create_tracking_boards(controller.conveyor.object, ASSETS_DIR)

    for role, obj in boards.items():
        print(f"ArUco board [{role}]: {obj.name}")

    bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath or str(SCENE_PATH))
    print("Scene saved:", bpy.data.filepath)

    # Контрольный кадр, чтобы сразу увидеть результат.
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(PREVIEW_PATH)
    bpy.ops.render.render(write_still=True)
    print("Preview:", PREVIEW_PATH)


if __name__ == "__main__":
    main()
