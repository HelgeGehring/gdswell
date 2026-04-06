# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import numpy as np

from gdswell.cell import Cell
from gdswell.components.generic_path import PathEvaluator, _populate_path, add_ports
from gdswell.cross_section import CrossSectionCallable
from gdswell.decorator import cell


class SpiralPathEvaluator(PathEvaluator):
    """Optimized NumPy-based path evaluator for Archimedean spirals."""

    def __init__(self, r0: float, dr: float, turns: float):
        self.r0 = float(r0)
        self.dr = float(dr)
        self.turns = float(turns)

    @property
    def length(self) -> float:
        """Physical length by numerical integration of speed."""
        s_vals = np.linspace(0, 1.0, 1001)
        speed_vals = self.evaluate_speed(s_vals)
        return float(np.trapezoid(speed_vals, s_vals))

    def evaluate_pos(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        r = self.r0 + self.dr * s
        theta = 2 * np.pi * self.turns * s
        x = r * np.cos(theta)
        y = r * np.sin(theta)
        return x, y

    def evaluate_deriv(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        r = self.r0 + self.dr * s
        theta = 2 * np.pi * self.turns * s
        dtheta_ds = 2 * np.pi * self.turns
        dr_ds = self.dr

        dx = dr_ds * np.cos(theta) - r * dtheta_ds * np.sin(theta)
        dy = dr_ds * np.sin(theta) + r * dtheta_ds * np.cos(theta)
        return dx, dy

    def evaluate_speed(self, s: np.ndarray) -> np.ndarray:
        dx, dy = self.evaluate_deriv(s)
        return np.sqrt(dx**2 + dy**2)

    def evaluate_theta(self, s: np.ndarray) -> np.ndarray:
        dx, dy = self.evaluate_deriv(s)
        return np.arctan2(dy, dx)


@cell
def spiral(
    cross_section: CrossSectionCallable,
    r0: float,
    dr: float,
    turns: float,
    npoints_per_360: int = 36,
) -> Cell:
    """
    Create an Archimedean spiral waveguide.

    Args:
        cross_section: The cross-section to use.
        r0: Initial radius.
        dr: Change in radius per turn.
        turns: Number of turns.
        npoints_per_360: Number of points for a full 360-degree turn.
    """
    npoints = max(2, int(abs(turns) * npoints_per_360))
    path = SpiralPathEvaluator(r0, dr, turns)
    c = Cell()
    xs = cross_section()
    _populate_path(
        c=c,
        cross_section=xs,
        path=path,
        npoints=npoints,
    )
    add_ports(c=c, path=path, cross_section=xs)
    return c
