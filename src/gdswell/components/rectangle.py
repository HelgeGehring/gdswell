# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

from gdswell.cell import Cell
from gdswell.decorator import cell
from gdswell.layer import Layer


@cell
def rectangle(layer: Layer, width: float, height: float) -> Cell:
    """
    Create a simple rectangle.

    Args:
        layer: The layer to place the rectangle on.
        width: The width of the rectangle.
        height: The height of the rectangle.
    """
    c = Cell()
    pts = [(0, 0), (width, 0), (width, height), (0, height)]
    c.add_polygon(pts, layer=layer)
    return c
