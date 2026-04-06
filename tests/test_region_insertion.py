# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import klayout.db as kdb

import gdswell as gw


def test_region_insertion() -> None:
    with gw.Layout() as ly:
        c = ly.create_cell()
        layer1 = gw.Layer(1, 0)
        layer2 = gw.Layer(2, 0)
        target = gw.Layer(3, 0)

        # Add two overlapping rectangles directly
        c.add_polygon([(0, 0), (2, 0), (2, 2), (0, 2)], layer1)
        c.add_polygon([(1, 1), (3, 1), (3, 3), (1, 3)], layer2)

        # Perform boolean via smart layers
        diff = layer1 - layer2
        region = diff.get_shapes(c)

        # Bake it into the target layer
        c.add_region(region, target)

        # Verify
        layer_index = ly.layer(target)
        shapes = c.kdb.shapes(layer_index)
        assert shapes.size() == 1
        assert kdb.Region(shapes).area() == 3000000
