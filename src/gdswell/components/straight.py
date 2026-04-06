# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import numpy as np

from gdswell.cell import Cell
from gdswell.components.generic_path import PathEvaluator, _populate_path, add_ports
from gdswell.cross_section import CrossSectionCallable
from gdswell.decorator import cell


class StraightPathEvaluator(PathEvaluator):
    """Optimized NumPy-based path evaluator for straight waveguides."""

    def __init__(self, length: float):
        self._length = float(length)

    @property
    def length(self) -> float:
        return self._length

    def evaluate_pos(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return self._length * s, np.zeros_like(s)

    def evaluate_deriv(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return np.full_like(s, self._length), np.zeros_like(s)

    def evaluate_speed(self, s: np.ndarray) -> np.ndarray:
        return np.full_like(s, self._length)

    def evaluate_theta(self, s: np.ndarray) -> np.ndarray:
        return np.zeros_like(s)


@cell
def straight(cross_section: CrossSectionCallable, length: float, npoints: int = 2) -> Cell:
    """
    Create a straight waveguide with the given cross_section and length.
    """
    path = StraightPathEvaluator(length)
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
