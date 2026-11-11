"""Сгенерировать PNG-панели ArUco для ленты конвейера (обычный Python + OpenCV).

Запуск:  python main.py generate-aruco

Каждая панель — сетка 2x2 маркеров DICT_4X4_50 (маркер 50 мм, зазор 10 мм)
с БЕЛОЙ рамкой 10 мм вокруг. Рамка нужна, потому что лента тёмная: без неё
чёрная граница внешних маркеров сливается с лентой и детектор их не находит.

Физические размеры (должны совпадать с blender/scripts/aruco_panels.py):
    сетка 110 мм + рамка 2 x 10 мм = панель 130 мм, 12 px/мм -> 1560 px.
"""
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "blender" / "assets" / "aruco"
OUT.mkdir(parents=True, exist_ok=True)

MARKER_M = 0.050
GAP_M = 0.010
MARGIN_M = 0.010
PX_PER_MM = 12
GRID_M = 2 * MARKER_M + GAP_M                       # 0.110
PANEL_M = GRID_M + 2 * MARGIN_M                     # 0.130
PANEL_PX = round(PANEL_M * 1000 * PX_PER_MM)        # 1560
MARGIN_PX = round(MARGIN_M * 1000 * PX_PER_MM)      # 120

# Роль панели -> ID маркеров (положение на ленте задаёт aruco_panels.py)
BOARDS = {
    "front_left":  [0, 1, 2, 3],
    "front_right": [4, 5, 6, 7],
    "rear_left":   [8, 9, 10, 11],
    "rear_right":  [12, 13, 14, 15],
}

dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

# Старые панели (front/center/rear) больше не используются.
for old in OUT.glob("board_*.png"):
    old.unlink()

for name, ids in BOARDS.items():
    try:
        board = cv2.aruco.GridBoard(
            (2, 2), MARKER_M, GAP_M, dictionary,
            ids=np.asarray(ids, dtype=np.int32)
        )
    except (AttributeError, TypeError):
        board = cv2.aruco.GridBoard_create(
            2, 2, MARKER_M, GAP_M, dictionary,
            np.asarray(ids, dtype=np.int32)
        )

    image = board.generateImage(
        (PANEL_PX, PANEL_PX), marginSize=MARGIN_PX, borderBits=1
    )
    path = OUT / f"board_{name}.png"
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise RuntimeError("OpenCV could not encode the image")
    encoded.tofile(path)
    print(f"Saved {path}; IDs={ids}")
