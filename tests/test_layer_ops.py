# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from enum import Enum

import gdswell as gw


class MyLayers(gw.Layer, Enum):
    WG = (1, 0)
    CLADDING = (2, 0)
    MASK = (3, 0)


M1 = gw.Layer(1, 0)
M2 = gw.Layer(2, 0)
M3 = gw.Layer(3, 0)


@gw.cell
def _cell_rect_m1() -> gw.Cell:
    c = gw.Cell()
    c.add_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], M1)
    return c


@gw.cell
def _cell_top_ops() -> gw.Cell:
    c = gw.Cell()
    c.add_ref(_cell_rect_m1())
    return c


@gw.cell
def _cell_mapped_ops(mapping: gw.LayerMapping) -> gw.Cell:
    c = gw.Cell()
    c.add_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], M1)
    return c


def test_layer_boolean_union() -> None:
    with gw.Layout() as ly:
        c = ly.create_cell()

        # Add a square on WG
        c.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], MyLayers.WG)
        # Add a square on CLADDING
        c.add_polygon([(0.5, 0), (1.5, 0), (1.5, 1), (0.5, 1)], MyLayers.CLADDING)

        # Merge WG and CLADDING
        combined = MyLayers.WG + MyLayers.CLADDING
        shapes = combined.get_shapes(c)

        # The result should be a single polygon from 0 to 1.5
        assert shapes.count() == 1
        assert shapes.bbox().left == 0
        assert shapes.bbox().right == 1500  # in dbu (0.001 typical)


def test_layer_boolean_difference() -> None:
    with gw.Layout() as ly:
        c = ly.create_cell()

        # Add a square on WG (0,0) to (2,2)
        c.add_polygon([(0, 0), (2, 0), (2, 2), (0, 2)], MyLayers.WG)
        # Add a square on CLADDING (1,1) to (3,3)
        c.add_polygon([(1, 1), (3, 1), (3, 3), (1, 3)], MyLayers.CLADDING)

        # WG - CLADDING
        diff = MyLayers.WG - MyLayers.CLADDING
        shapes = diff.get_shapes(c)

        # Result should be an L-shape
        assert shapes.count() == 1
        bbox = shapes.bbox()
        assert bbox.left == 0
        assert bbox.bottom == 0
        assert bbox.right == 2000
        assert bbox.top == 2000
        assert shapes.area() == 3000000


def test_layer_size() -> None:
    with gw.Layout() as ly:
        c = ly.create_cell()

        # Add a square on WG (0,0) to (1,1)
        c.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], MyLayers.WG)

        # Size by 0.5 -> Should become (-0.5, -0.5) to (1.5, 1.5)
        sized = MyLayers.WG.size(0.5)
        shapes = sized.get_shapes(c)

        bbox = shapes.bbox()
        assert bbox.left == -500
        assert bbox.bottom == -500
        assert bbox.right == 1500
        assert bbox.top == 1500


def test_complex_expression() -> None:
    with gw.Layout() as ly:
        c = ly.create_cell()

        c.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], MyLayers.WG)
        c.add_polygon([(2, 2), (3, 2), (3, 3), (2, 3)], MyLayers.CLADDING)

        # (WG | CLADDING).size(0.1)
        expr = (MyLayers.WG | MyLayers.CLADDING).size(0.1)
        shapes = expr.get_shapes(c)

        assert shapes.count() == 2
        assert abs(shapes.area() - 2880000) < 1.0


def test_layer_mapping() -> None:
    layout = gw.Layout()

    # Define layers
    M1 = gw.Layer(1, 0)
    M2 = gw.Layer(2, 0)
    M3 = gw.Layer(3, 0)
    M4 = gw.Layer(4, 0)
    M5 = gw.Layer(5, 0)

    # Create a cell with some shapes
    cell = gw.Cell(layout=layout)
    cell.add_polygon([(0, 0), (10, 0), (10, 10), (0, 10)], M1)
    cell.add_polygon([(20, 0), (30, 0), (30, 10), (20, 10)], M2)
    cell.add_polygon([(40, 0), (50, 0), (50, 10), (40, 10)], M4)

    # Define operation
    # (M1 + M2.size(5)).onto(M3) + M4.onto(M5)
    operation = (M1 + M2.size(1)).onto(M3) + M4.onto(M5)

    # In-place application
    operation.apply(cell)

    # Verify M3 has shapes from M1 and M2.size(1)
    # M1 is (0,0) to (10,10)
    # M2 is (20,0) to (30,10) -> size(1) becomes (19,-1) to (31,11)
    m3_region = gw.Layer(3, 0).get_shapes(cell)
    assert m3_region.area() > 0
    # M1 area = 100
    # M2 size(1) area = 12 * 12 = 144
    # Total = 244
    # (Assuming DBU is 0.001)
    dbu = layout.kdb.dbu
    expected_area = (100 + 144) / (dbu * dbu)
    assert m3_region.area() == expected_area

    # Verify M5 has shapes from M4
    m5_region = gw.Layer(5, 0).get_shapes(cell)
    expected_area_m5 = 100 / (dbu * dbu)
    assert m5_region.area() == expected_area_m5


def test_hierarchical_layer_mapping() -> None:
    with gw.Layout() as layout:
        top = _cell_top_ops()

        # M1.onto(M3) should see shapes in sub_cell
        operation = M1.onto(M3)
        # operation(top) creates a new cell referencing top
        new_top = operation(top)

        # new_top should be different from top and contain a reference
        assert new_top is not top
        assert new_top.name != top.name

        m3_region = M3.get_shapes(new_top)
        dbu = layout.kdb.dbu
        expected_area = 100 / (dbu * dbu)
        assert m3_region.area() == expected_area


def test_layer_mapping_cell_caching() -> None:
    # Call with same mapping but different dict order
    op1 = M1.onto(M2) + M1.onto(M3)
    op2 = M1.onto(M3) + M1.onto(M2)

    c1 = _cell_mapped_ops(op1)
    c2 = _cell_mapped_ops(op2)

    # Should use cache and have same name
    assert c1.name == c2.name
    assert c1 is c2


def test_new_cell_from_operation() -> None:
    with gw.Layout():
        cell = _cell_rect_m1()

        operation = M1.onto(M2)
        new_cell = operation(cell)

        # Check that new_cell is a different cell and has the derived shapes
        assert new_cell is not cell
        assert M2.get_shapes(new_cell).area() > 0
        # Original cell should be unchanged
        assert M2.get_shapes(cell).area() == 0


if __name__ == "__main__":
    test_layer_mapping()
