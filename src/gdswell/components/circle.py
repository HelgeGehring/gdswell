# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

import numpy as np

from gdswell.cell import Cell
from gdswell.decorator import cell
from gdswell.layer import Layer


@cell
def circle(layer: Layer, radius: float, npoints: int = 64) -> Cell:
    """
    Create a simple circle.

    Args:
        layer: The layer to place the circle on.
        radius: The radius of the circle.
        npoints: The number of points to approximate the circle.
    """
    c = Cell()
    theta = np.linspace(0, 2 * np.pi, npoints, endpoint=False)
    pts = [(float(radius * np.cos(t)), float(radius * np.sin(t))) for t in theta]
    c.add_polygon(pts, layer=layer)
    return c
