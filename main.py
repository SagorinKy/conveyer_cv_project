"""Единая точка входа проекта.

  python main.py generate-aruco   # 0. PNG-панели ArUco (обычный Python + OpenCV)
  python main.py scene            # 1. создать сцену conveyor.blend
  python main.py aruco            # 2. добавить ArUco-панели в готовую сцену
  python main.py experiment       # 3. отрендерить кадры + ground truth
  python main.py video            # 4. собрать mp4 из кадров
  python main.py all              # всё по порядку

Путь к Blender: переменная окружения BLENDER_PATH или значение по умолчанию.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "blender" / "scripts"
SCENE = ROOT / "blender" / "scenes" / "conveyor.blend"

DEFAULT_BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
BLENDER = os.environ.get("BLENDER_PATH", DEFAULT_BLENDER)


def run(cmd):
    print(">", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], cwd=ROOT, check=True)


def blender(script, *script_args, open_scene=True):
    cmd = [BLENDER, "--background"]
    if open_scene:
        if not SCENE.exists():
            sys.exit(f"Нет {SCENE}. Сначала: python main.py scene")
        cmd.append(SCENE)
    cmd += ["--python", SCRIPTS / script]
    if script_args:
        cmd += ["--", *script_args]
    run(cmd)


def generate_aruco():
    run([sys.executable, ROOT / "tools" / "generate_aruco_boards.py"])


def scene():
    # create_scene.py сам создаёт сцену с нуля, поэтому .blend не открываем.
    blender("create_scene.py", open_scene=False)


def aruco():
    blender("add_aruco.py")


def experiment(config):
    blender("run_experiment.py", "--config", config)


def video():
    run([sys.executable, ROOT / "tools" / "create_video.py"])


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=[
        "generate-aruco", "scene", "aruco", "experiment", "video", "all"])
    parser.add_argument("--config", default="config/experiment.json",
                        help="конфиг эксперимента (для experiment / all)")
    args = parser.parse_args()

    if args.command == "generate-aruco":
        generate_aruco()
    elif args.command == "scene":
        scene()
    elif args.command == "aruco":
        aruco()
    elif args.command == "experiment":
        experiment(args.config)
    elif args.command == "video":
        video()
    else:
        generate_aruco()
        scene()
        aruco()
        experiment(args.config)
        video()


if __name__ == "__main__":
    main()
