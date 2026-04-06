# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import json
from enum import Enum

import klayout.db as kdb
import pytest

import gdswell as gw


class Pdk(gw.Layer, Enum):
    WG = (1, 0)
    CLADDING = (2, 0)


@gw.cell
def my_cell() -> gw.Cell:
    return gw.Cell()


@gw.cell
def child_cell() -> gw.Cell:
    return gw.Cell()


@gw.cell
def info_cell() -> gw.Cell:
    c = gw.Cell()
    c.add_info("author", "Antigravity")
    c.add_info("version", 1)
    c.add_info("tags", ["test", "metadata"])
    return c


@gw.cell
def bad_info_cell() -> gw.Cell:
    c = gw.Cell()
    # Add a non-serializable object
    c.add_info("callback", lambda x: x)
    return c


@gw.cell
def project_cell() -> gw.Cell:
    c = gw.Cell()
    c.add_info("project", "gdswell")
    return c


def test_layout_creation() -> None:
    layout = gw.Layout()
    assert isinstance(layout.kdb, kdb.Layout)


def test_cell_creation() -> None:
    layout = gw.Layout()
    cell = layout.create_cell()

    assert isinstance(cell, gw.Cell)
    assert cell.name.startswith("UnnamedCell_")
    assert cell.layout is layout
    assert isinstance(cell.kdb, kdb.Cell)


def test_find_cell() -> None:
    with gw.Layout() as layout:
        c = my_cell()
        found_cell = layout.cell(c.name)
        assert found_cell is c

    with pytest.raises(KeyError, match="not found"):
        gw.Layout.get_default().cell("does_not_exist")


def test_add_polygon() -> None:
    layout = gw.Layout()
    cell = layout.create_cell()
    layer = Pdk.WG

    poly_pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]
    shape = cell.add_polygon(poly_pts, layer)

    assert isinstance(shape, kdb.Shape)
    assert shape.is_polygon()

    # Check that it was actually added to the cell
    layer_index = layout.layer(layer)
    shapes_on_layer = cell.kdb.shapes(layer_index)
    assert shapes_on_layer.size() == 1


def test_add_ref() -> None:
    with gw.Layout() as layout:
        parent_cell = layout.create_cell()
        child = child_cell()

        inst = parent_cell.add_ref(child, origin=(10.0, 5.0), rotation=90)

        assert isinstance(inst, gw.Instance)
        assert inst.kdb.cell_index == child.kdb.cell_index()

        # Check that it was actually added
        assert parent_cell.kdb.child_instances() == 1

        # Check transformation
        dtrans = inst.dtrans
        assert dtrans.disp.x == 10.0
        assert dtrans.disp.y == 5.0
        assert dtrans.angle == 1


def test_implicit_layout() -> None:
    # Make sure default is created
    cell1 = gw.Cell()
    assert cell1.layout is gw.Layout.get_default()
    assert cell1.name.startswith("UnnamedCell_")


def test_context_layout() -> None:
    with gw.Layout(name="context_layout") as layout:
        cell2 = gw.Cell()
        assert cell2.layout is layout
        assert cell2.layout.name == "context_layout"

    # Exited context, back to default
    cell3 = gw.Cell()
    assert cell3.layout is not layout
    assert cell3.layout is gw.Layout.get_default()


def test_cell_layout_cross_layout_copy() -> None:
    layout1 = gw.Layout(name="layout1")
    layout2 = gw.Layout(name="layout2")

    # Create cell natively in layout1 and add something
    kdb_cell1 = layout1.kdb.create_cell("cell1")
    kdb_cell1.shapes(layout1.layer(Pdk.WG)).insert(kdb.DBox(0, 0, 10, 10))

    # Wrap it using layout2, should copy it over
    cell2 = gw.Cell._from_kdb_cell(kdb_cell1, layout=layout2)

    assert cell2.name == "cell1"
    assert cell2.layout is layout2
    assert cell2.kdb.layout() == layout2.kdb
    assert cell2.kdb.shapes(layout2.layer(Pdk.WG)).size() == 1


def test_cell_identity() -> None:
    with gw.Layout() as layout:
        # Calling the decorator twice with same args (none) should return same object
        c1 = my_cell()
        c2 = my_cell()

        assert c1 is c2
        assert layout.cell(c1.name) is c1


def test_cell_info() -> None:
    with gw.Layout():
        c = info_cell()
        assert c.info["author"] == "Antigravity"

        # Verify it's in KLayout meta-info
        info_json = c.kdb.meta_info("cell_info").value
        info_dict = json.loads(info_json)
        assert info_dict["author"] == "Antigravity"
        assert info_dict["version"] == 1
        assert info_dict["tags"] == ["test", "metadata"]


def test_cell_info_serialization_error() -> None:
    with gw.Layout():
        # Force synchronous execution for this test
        gw.config.async_cells = False
        try:
            with pytest.raises(TypeError, match="not JSON serializable"):
                bad_info_cell()
        finally:
            gw.config.async_cells = True


def test_cell_info_restoration() -> None:
    with gw.Layout() as layout:
        c1 = project_cell()

        # New cell wrapper around the same kdb cell
        c2 = gw.Cell._from_kdb_cell(c1.kdb, layout=layout)

        assert c2.info["project"] == "gdswell"


def test_malformed_metadata_error() -> None:
    layout = gw.Layout("test_error")
    # Manually create kdb cells without wrappers
    kdb_cell1 = layout.kdb.create_cell("bad_info")
    kdb_cell1.add_meta_info(kdb.LayoutMetaInfo("cell_info", "{not_json}", None, True))

    with pytest.raises(json.JSONDecodeError):
        gw.Cell._from_kdb_cell(kdb_cell1, layout=layout)

    kdb_cell2 = layout.kdb.create_cell("bad_ports")
    kdb_cell2.add_meta_info(kdb.LayoutMetaInfo("ports", "[1, 2, 3]", None, True))

    # Now it raises ValueError("ports must be a dictionary") directly
    with pytest.raises(ValueError, match="ports must be a dictionary"):
        gw.Cell._from_kdb_cell(kdb_cell2, layout=layout)
