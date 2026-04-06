# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import numpy as np

from gdswell.cell import Cell
from gdswell.components.generic_path import PathEvaluator, _populate_path, add_ports
from gdswell.cross_section import CrossSectionCallable
from gdswell.decorator import cell


class BendSPathEvaluator(PathEvaluator):
    """Optimized NumPy-based path evaluator for S-bends."""

    def __init__(self, width: float, height: float):
        self.width = float(width)
        self.height = float(height)

    @property
    def length(self) -> float:
        """Physical length by numerical integration of speed."""
        s_vals = np.linspace(0, 1.0, 1001)
        speed_vals = self.evaluate_speed(s_vals)
        return float(np.trapezoid(speed_vals, s_vals))

    def evaluate_pos(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Evaluate (x, y) at s."""
        x = self.width * s
        y = self.height * (s - np.sin(2 * np.pi * s) / (2 * np.pi))
        return x, y

    def evaluate_deriv(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Evaluate (dx/ds, dy/ds) at s."""
        dx = np.full_like(s, self.width)
        dy = self.height * (1 - np.cos(2 * np.pi * s))
        return dx, dy

    def evaluate_speed(self, s: np.ndarray) -> np.ndarray:
        """Evaluate speed sqrt((dx/ds)^2 + (dy/ds)^2) at s."""
        dx, dy = self.evaluate_deriv(s)
        return np.sqrt(dx**2 + dy**2)

    def evaluate_theta(self, s: np.ndarray) -> np.ndarray:
        """Evaluate tangent angle arctan2(dy/ds, dx/ds) at s."""
        dx, dy = self.evaluate_deriv(s)
        return np.arctan2(dy, dx)


@cell
def bend_s(
    cross_section: CrossSectionCallable, width: float, height: float, npoints: int = 36
) -> Cell:
    """
    Create a smooth S-bend connector using a sine-shaped path.

    Args:
        cross_section: The cross-section to use.
        width: The horizontal distance between ports.
        height: The vertical offset between ports.
        npoints: Number of points for discretization of the S-bend path.
    """
    path = BendSPathEvaluator(width, height)
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
