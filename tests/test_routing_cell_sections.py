# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from enum import Enum

import gdswell as gw
from gdswell.routing import route_manhattan


class MyLayers(gw.Layer, Enum):
    WG = (1, 0)
    MARKER = (2, 0)


@gw.cell
def marker_factory():
    c = gw.Cell()
    c.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], layer=MyLayers.MARKER)
    return c


@gw.cell
def top_cell(with_cell_sections_in_bend: bool):
    marker = marker_factory()

    # 2. Define a cross-section with a cell section
    xs = gw.CrossSection(
        layer_sections=(gw.LayerSection("core", MyLayers.WG, 0.5),),
        cell_sections=(gw.CellSection("marker_sec", marker, periodicity=2.0),),
    )

    c = gw.Cell()
    p1 = gw.Port("p1", (0, 0), 0, xs)
    p2 = gw.Port("p2", (20, 20), 180, xs)

    route_manhattan(c, p1, p2, radius=5.0, with_cell_sections_in_bend=with_cell_sections_in_bend)
    return c


def test_route_manhattan_with_cell_sections_in_bend():
    print("Checking route with with_cell_sections_in_bend=True...")
    c1 = top_cell(with_cell_sections_in_bend=True)

    # Find the route cell reference
    route_inst = c1.instances[0]
    route_cell = route_inst.cell

    # Check bends in c1
    bends1 = [ref for ref in route_cell.instances if "bend" in ref.cell.name]
    assert len(bends1) > 0
    for bend in bends1:
        has_marker = any("marker" in ref.cell.name for ref in bend.cell.instances)
        assert has_marker, f"Bend {bend.cell.name} should have marker but doesn't"

    print("Checking route with with_cell_sections_in_bend=False...")
    c2 = top_cell(with_cell_sections_in_bend=False)
    route_inst2 = c2.instances[0]
    route_cell2 = route_inst2.cell

    # Check bends in c2
    bends2 = [ref for ref in route_cell2.instances if "bend" in ref.cell.name]
    assert len(bends2) > 0
    for bend in bends2:
        has_marker = any("marker" in ref.cell.name for ref in bend.cell.instances)
        assert not has_marker, f"Bend {bend.cell.name} should NOT have marker but does"

    print("Verification successful!")


if __name__ == "__main__":
    test_route_manhattan_with_cell_sections_in_bend()
