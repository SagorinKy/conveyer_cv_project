import cv2
import numpy as np
import scipy
import pandas as pd

print("OpenCV:", cv2.__version__)
print("ArUco:", hasattr(cv2, "aruco"))
print("NumPy:", np.__version__)
print("SciPy:", scipy.__version__)
print("Pandas:", pd.__version__)