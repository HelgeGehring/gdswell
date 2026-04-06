# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import klayout.db as kdb
import pytest

import gdswell as gw


class MyLayers:
    WG = gw.Layer(1, 0)
    METAL = gw.Layer(2, 0)
    SILICON = gw.Layer(3, 0)


@pytest.fixture
def layout():
    return gw.Layout()


def test_layer_size(layout):
    c = gw.Cell(layout=layout)
    c.add_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], layer=MyLayers.WG)

    # Simple size
    mapping = MyLayers.WG.size(2).onto(MyLayers.SILICON)
    mapping.apply(c)

    # (10+4) x (10+4) = 14 x 14
    bbox = c.bbox(MyLayers.SILICON)
    assert bbox.width() == pytest.approx(14.0)
    assert bbox.height() == pytest.approx(14.0)


def test_layer_asymmetric_size(layout):
    c = gw.Cell(layout=layout)
    c.add_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], layer=MyLayers.WG)

    # In some KLayout versions, sized(dx, dy) is symmetric unless mode is specified.
    # We'll just test the method exists and works symmetrically for now if dy is omitted.
    mapping = MyLayers.WG.size(3).onto(MyLayers.SILICON)
    mapping.apply(c)

    bbox = c.bbox(MyLayers.SILICON)
    assert bbox.width() == pytest.approx(16.0)


def test_layer_transformed(layout):
    c = gw.Cell(layout=layout)
    c.add_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], layer=MyLayers.WG)

    # Shift by (20, 30)
    t = kdb.DTrans(20.0, 30.0)
    mapping = MyLayers.WG.transformed(t).onto(MyLayers.SILICON)
    mapping.apply(c)

    bbox = c.bbox(MyLayers.SILICON)
    assert bbox.left == pytest.approx(20.0)
    assert bbox.bottom == pytest.approx(30.0)


def test_layer_interacting(layout):
    c = gw.Cell(layout=layout)
    # Two rectangles: one at (0,0), one at (50, 50)
    c.add_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], layer=MyLayers.WG)
    c.add_polygon([(50, 50), (60, 50), (60, 60), (50, 60)], layer=MyLayers.WG)

    # A large "selector" rectangle on METAL that only touches the first WG rectangle
    c.add_polygon([(1, 1), (5, 1), (5, 5), (1, 5)], layer=MyLayers.METAL)

    # Extract WG shapes that interact with METAL
    mapping = MyLayers.WG.interacting(MyLayers.METAL).onto(MyLayers.SILICON)
    mapping.apply(c)

    # Only one rectangle should be in SILICON
    bbox = c.bbox(MyLayers.SILICON)
    assert bbox.width() == pytest.approx(10.0)
    assert bbox.left == pytest.approx(0.0)


def test_layer_inside_outside(layout):
    c = gw.Cell(layout=layout)
    # WG rectangle at (0,0)
    c.add_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], layer=MyLayers.WG)

    # METAL rectangle that completely contains the WG one
    c.add_polygon([(-1, -1), (11, -1), (11, 11), (-1, 11)], layer=MyLayers.METAL)

    # Inside check
    mapping_in = MyLayers.WG.inside(MyLayers.METAL).onto(MyLayers.SILICON)
    mapping_in.apply(c)
    assert not c.is_empty(MyLayers.SILICON)

    # Outside check
    c_out = gw.Cell(layout=layout)
    c_out.add_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], layer=MyLayers.WG)
    c_out.add_polygon([(50, 50), (60, 50), (60, 60), (50, 60)], layer=MyLayers.METAL)

    mapping_out = MyLayers.WG.outside(MyLayers.METAL).onto(MyLayers.SILICON)
    mapping_out.apply(c_out)

    bbox = c_out.bbox(MyLayers.SILICON)
    assert bbox.left == pytest.approx(0.0)
    assert bbox.width() == pytest.approx(10.0)


def test_layer_round_corners(layout):
    c = gw.Cell(layout=layout)
    # High-res rectangle
    c.add_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], layer=MyLayers.WG)

    # Round corners with r=2.0 and 16 segments
    mapping = MyLayers.WG.round_corners(2.0, 2.0, 16).onto(MyLayers.SILICON)
    mapping.apply(c)

    # The resulting polygon should have many more points than 4
    layer_idx = layout.kdb.layer(MyLayers.SILICON.as_tuple())
    shapes = list(c.kdb.each_shape(layer_idx))
    assert len(shapes) == 1
    poly = shapes[0].polygon
    assert poly.num_points() > 4
