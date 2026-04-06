# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from enum import Enum

import pytest

import gdswell as gw


class MyLayers(gw.Layer, Enum):
    WG = (1, 0)
    CLADDING = (2, 0)
    BBOX = (10, 0)


@gw.cell
def _cell_sub_bbox():
    c = gw.Cell()
    c.add_polygon([(10, 10), (20, 10), (20, 20), (10, 20)], layer=MyLayers.WG)
    return c


@pytest.fixture
def layout():
    return gw.Layout()


def test_single_layer_bbox(layout):
    c = gw.Cell(layout=layout)
    # Rectangle from (0,0) to (10, 20)
    c.add_polygon([(0, 0), (10, 0), (10, 20), (0, 20)], layer=MyLayers.WG)

    # Bbox operation
    mapping = MyLayers.WG.bbox().onto(MyLayers.BBOX)
    mapping.apply(c)

    bbox = c.bbox(MyLayers.BBOX)
    assert bbox.left == 0.0
    assert bbox.bottom == 0.0
    assert bbox.right == 10.0
    assert bbox.top == 20.0
    assert c.is_empty(MyLayers.BBOX) is False


def test_all_layers_bbox(layout):
    c = gw.Cell(layout=layout)
    c.add_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], layer=MyLayers.WG)
    c.add_polygon([(20, 20), (30, 20), (30, 30), (20, 30)], layer=MyLayers.CLADDING)

    # AllLayers().bbox()
    from gdswell.layer import AllLayers

    mapping = AllLayers().bbox().onto(MyLayers.BBOX)
    mapping.apply(c)

    bbox = c.bbox(MyLayers.BBOX)
    assert bbox.left == -0.0  # 0.0
    assert bbox.bottom == -0.0
    assert bbox.right == 30.0
    assert bbox.top == 30.0


def test_composite_layer_bbox(layout):
    c = gw.Cell(layout=layout)
    c.add_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], layer=MyLayers.WG)
    c.add_polygon([(20, 20), (30, 20), (30, 30), (20, 30)], layer=MyLayers.CLADDING)
    c.add_polygon(
        [(100, 100), (110, 100), (110, 110), (100, 110)], layer=gw.Layer(5, 0)
    )  # Another layer

    # Only WG and CLADDING
    mapping = (MyLayers.WG | MyLayers.CLADDING).bbox().onto(MyLayers.BBOX)
    mapping.apply(c)

    bbox = c.bbox(MyLayers.BBOX)
    assert bbox.left == 0.0
    assert bbox.right == 30.0
    assert bbox.top == 30.0


def test_hierarchical_bbox(layout):
    c = gw.Cell(layout=layout)
    c.add_ref(_cell_sub_bbox(), origin=(100, 100))  # Subcell at (110, 110) to (120, 120)

    from gdswell.layer import AllLayers

    mapping = AllLayers().bbox().onto(MyLayers.BBOX)
    mapping.apply(c)

    bbox = c.bbox(MyLayers.BBOX)
    assert bbox.left == 110.0
    assert bbox.bottom == 110.0
    assert bbox.right == 120.0
    assert bbox.top == 120.0


def test_sized_bbox(layout):
    c = gw.Cell(layout=layout)
    c.add_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], layer=MyLayers.WG)

    # Bbox sized by 5.0 -> (-5, -5) to (15, 15)
    mapping = MyLayers.WG.bbox().size(5.0).onto(MyLayers.BBOX)
    mapping.apply(c)

    bbox = c.bbox(MyLayers.BBOX)
    assert bbox.left == -5.0
    assert bbox.bottom == -5.0
    assert bbox.right == 15.0
    assert bbox.top == 15.0
