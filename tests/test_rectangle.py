# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import gdswell as gw
from gdswell.components.rectangle import rectangle


def test_rectangle() -> None:
    with gw.Layout() as ly:
        layer = gw.Layer(1, 0)
        c = rectangle(layer, width=10.0, height=5.0)

        # Verify geometry
        layer_index = ly.layer(layer)
        shapes = c.kdb.shapes(layer_index)
        assert shapes.size() == 1
        bbox = c.kdb.bbox(layer_index)
        assert bbox.left == 0
        assert bbox.bottom == 0
        assert bbox.right == 10000  # in dbu
        assert bbox.top == 5000  # in dbu
