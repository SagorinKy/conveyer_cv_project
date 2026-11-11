"""Собрать видео из кадров results/experiment/frames (обычный Python + OpenCV).

Запуск:  python main.py video
FPS берётся из ground_truth.json, поэтому совпадает с экспериментом.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def read_image(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def create_video(experiment_dir):
    frames_dir = experiment_dir / "frames"
    output = experiment_dir / "conveyor_experiment.mp4"

    frames = sorted(frames_dir.glob("frame_*.png"))
    if not frames:
        raise FileNotFoundError(f"Кадры не найдены: {frames_dir}")

    fps = 30
    gt_path = experiment_dir / "ground_truth.json"
    if gt_path.exists():
        with open(gt_path, "r", encoding="utf-8") as f:
            fps = int(json.load(f)["metadata"]["fps"])

    first = read_image(frames[0])
    if first is None:
        raise RuntimeError(f"Не удалось прочитать кадр: {frames[0]}")
    height, width = first.shape[:2]

    writer = cv2.VideoWriter(
        str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )
    if not writer.isOpened():
        raise RuntimeError("Не удалось создать видеофайл (кодек mp4v).")

    try:
        for path in frames:
            image = read_image(path)
            if image is None:
                print("Пропущен повреждённый кадр:", path)
                continue
            writer.write(image)
    finally:
        writer.release()

    print(f"Видео создано: {output} ({len(frames)} кадров, {fps} fps)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="results/experiment")
    args = parser.parse_args()
    create_video((ROOT / args.dir).resolve())
