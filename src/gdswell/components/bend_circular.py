# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

import numpy as np

from gdswell.cell import Cell
from gdswell.components.generic_path import PathEvaluator, _populate_path, add_ports
from gdswell.cross_section import CrossSectionCallable
from gdswell.decorator import cell


class CircularPathEvaluator(PathEvaluator):
    """Optimized NumPy-based path evaluator for circular bends."""

    def __init__(self, radius: float, angle: float):
        self.radius = float(radius)
        self.angle = float(angle)
        self.angle_rad = np.deg2rad(abs(self.angle))

    @property
    def length(self) -> float:
        return self.radius * self.angle_rad

    def evaluate_pos(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x = self.radius * np.sin(self.angle_rad * s)
        y = np.sign(self.angle) * self.radius * (1 - np.cos(self.angle_rad * s))
        return x, y

    def evaluate_deriv(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        dx = self.radius * self.angle_rad * np.cos(self.angle_rad * s)
        dy = np.sign(self.angle) * self.radius * self.angle_rad * np.sin(self.angle_rad * s)
        return dx, dy

    def evaluate_speed(self, s: np.ndarray) -> np.ndarray:
        return np.full_like(s, self.radius * self.angle_rad)

    def evaluate_theta(self, s: np.ndarray) -> np.ndarray:
        dx, dy = self.evaluate_deriv(s)
        return np.arctan2(dy, dx)


@cell
def bend_circular(
    cross_section: CrossSectionCallable, radius: float, angle: float, npoints_per_360: int = 36
) -> Cell:
    """
    Create a circular bend with the given cross_section, radius, and angle.

    Args:
        cross_section: The cross-section to use.
        radius: The radius of the bend.
        angle: The angle of the bend in degrees.
        npoints_per_360: Number of points for a full 360-degree turn.
    """
    cross_section = cross_section()

    # Pre-clip cross-section to avoid self-intersection
    if angle > 0:
        clipped_xs = cross_section.clip(max_val=radius)
    else:
        clipped_xs = cross_section.clip(min_val=-radius)

    npoints = max(2, int(abs(angle) * npoints_per_360 / 360))
    path = CircularPathEvaluator(radius, angle)
    c = Cell()
    _populate_path(c=c, cross_section=clipped_xs, path=path, npoints=npoints)
    add_ports(c=c, path=path, cross_section=cross_section)

    return c
