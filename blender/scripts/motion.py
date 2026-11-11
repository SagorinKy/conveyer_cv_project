"""Deterministic motion and vibration utilities for Blender experiments.

This module uses only the Python standard library, so it works with Blender's
bundled Python and does not require NumPy.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence


def _vec3(value, default=(0.0, 0.0, 0.0)):
    if value is None:
        return tuple(default)
    if len(value) != 3:
        raise ValueError("Expected a 3-element vector")
    return tuple(float(x) for x in value)


@dataclass
class Vibration:
    enabled: bool = False
    mode: str = "combined"  # harmonic | gaussian | combined
    frequency_hz: float = 10.0
    amplitude: tuple = (0.0, 0.0, 0.0)  # peak displacement, metres or radians
    sigma: tuple = (0.0, 0.0, 0.0)      # Gaussian standard deviation
    phase_rad: tuple = (0.0, 0.0, 0.0)
    seed: int = 42

    @classmethod
    def from_dict(cls, data):
        return cls(
            enabled=bool(data.get("enabled", False)),
            mode=str(data.get("mode", "combined")).lower(),
            frequency_hz=float(data.get("frequency_hz", data.get("frequency", 10.0))),
            amplitude=_vec3(data.get("amplitude", (0, 0, 0))),
            sigma=_vec3(data.get("sigma", (0, 0, 0))),
            phase_rad=_vec3(data.get("phase_rad", (0, 0, 0))),
            seed=int(data.get("seed", 42)),
        )

    def offset(self, time_s: float, frame_index: int):
        """Return deterministic XYZ offset for this exact frame."""
        if not self.enabled:
            return (0.0, 0.0, 0.0)
        if self.mode not in {"harmonic", "gaussian", "combined"}:
            raise ValueError(f"Unknown vibration mode: {self.mode}")

        harmonic = [0.0, 0.0, 0.0]
        noise = [0.0, 0.0, 0.0]

        if self.mode in {"harmonic", "combined"}:
            for axis in range(3):
                harmonic[axis] = self.amplitude[axis] * math.sin(
                    2.0 * math.pi * self.frequency_hz * time_s + self.phase_rad[axis]
                )

        if self.mode in {"gaussian", "combined"}:
            # A separate deterministic stream per frame; rendering frames in a
            # different order produces exactly the same noise for each frame.
            for axis in range(3):
                rng = random.Random(
                    self.seed + frame_index * 1000003 + axis * 9176
                )
                noise[axis] = rng.gauss(0.0, self.sigma[axis])

        return tuple(harmonic[i] + noise[i] for i in range(3))


def vector3(value):
    return _vec3(value)
