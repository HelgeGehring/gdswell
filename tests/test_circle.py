# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import gdswell as gw
from gdswell.components.circle import circle


def test_circle() -> None:
    with gw.Layout() as ly:
        layer = gw.Layer(1, 0)
        radius = 10.0
        c = circle(layer, radius=radius, npoints=64)

        # Verify geometry
        layer_index = ly.layer(layer)
        shapes = c.kdb.shapes(layer_index)
        assert shapes.size() == 1

        # Bbox should be [-radius, -radius, radius, radius]
        bbox = c.kdb.dbbox(layer_index)
        assert bbox.left == -radius
        assert bbox.bottom == -radius
        assert bbox.right == radius
        assert bbox.top == radius
