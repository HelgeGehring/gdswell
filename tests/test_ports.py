# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from enum import Enum

import klayout.db as kdb
import pytest

import gdswell as gw


class LayerEnum(gw.Layer, Enum):
    WG = (1, 0)


xs = gw.CrossSection((gw.LayerSection("core", LayerEnum.WG, 0.5),))


@gw.cell
def _cell_ports_fixed_out() -> gw.Cell:
    c = gw.Cell()
    c.add_port(gw.Port(name="out", position=(10.0, 0.0), angle=0, cross_section=xs))
    return c


@gw.cell
def _cell_ports_c2_conn() -> gw.Cell:
    c = gw.Cell()
    c.add_port(gw.Port(name="in", position=(0.0, 0.0), angle=180, cross_section=xs))
    return c


@gw.cell
def _cell_ports_c2_conn_rot() -> gw.Cell:
    c = gw.Cell()
    c.add_port(gw.Port(name="in", position=(5.0, 0.0), angle=90, cross_section=xs))
    return c


@gw.cell
def _cell_ports_sub() -> gw.Cell:
    c = gw.Cell()
    c.add_port(gw.Port(name="p1", position=(1.0, 0.0), angle=0, cross_section=xs))
    return c


@gw.cell
def _cell_ports_meta() -> gw.Cell:
    c = gw.Cell()
    p1 = gw.Port(name="p1", position=(0.0, 0.0), angle=0, cross_section=xs)
    p2 = gw.Port(name="p2", position=(10.0, 5.0), angle=90, cross_section=xs)
    c.add_port(p1)
    c.add_port(p2)
    return c


@gw.cell
def _cell_ports_restoration() -> gw.Cell:
    c = gw.Cell()
    c.add_port(gw.Port(name="p1", position=(1.2, 3.4), angle=90, cross_section=xs))
    return c


@gw.cell
def _cell_ports_empty() -> gw.Cell:
    return gw.Cell()


def test_port_creation() -> None:
    p = gw.Port(name="p1", position=(10.0, 20.0), angle=90, cross_section=xs)
    assert p.name == "p1"
    assert p.position == (10.0, 20.0)
    assert p.angle == 90
    assert p.cross_section == xs


def test_port_transformed() -> None:
    p = gw.Port(name="p1", position=(10.0, 0.0), angle=0, cross_section=xs)
    # Rotate 90 degrees around origin
    trans = kdb.DTrans(1, False, kdb.DVector(5.0, 5.0))
    p_trans = p.transformed(trans)

    # Original position (10, 0) rotated 90 degrees -> (0, 10). Then translated by (5, 5) -> (5, 15)
    assert p_trans.position[0] == pytest.approx(5.0)
    assert p_trans.position[1] == pytest.approx(15.0)
    assert p_trans.angle == pytest.approx(90)
    assert p_trans.cross_section == xs


def test_port_with_cross_section() -> None:
    p = gw.Port(name="p1", position=(10.0, 0.0), angle=0, cross_section=xs)
    xs2 = gw.CrossSection((gw.LayerSection("core2", LayerEnum.WG, 1.0),))
    p2 = p.with_cross_section(xs2)

    assert p2.name == p.name
    assert p2.position == p.position
    assert p2.angle == p.angle
    assert p2.cross_section == xs2
    assert p2 is not p


def test_cell_add_port() -> None:
    with gw.Layout() as layout:
        c = layout.create_cell()
        p = gw.Port(name="p1", position=(0.0, 0.0), angle=180, cross_section=xs)
        c.add_port(p)

        assert c["p1"] == p
        with pytest.raises(KeyError):
            c["nonexistent"]


def test_duplicate_port_error() -> None:
    with gw.Layout() as layout:
        c = layout.create_cell()
        p1 = gw.Port(name="p1", position=(0.0, 0.0), angle=0, cross_section=xs)
        p2 = gw.Port(name="p1", position=(10.0, 0.0), angle=180, cross_section=xs)

        c.add_port(p1)
        with pytest.raises(ValueError, match="Port 'p1' already exists"):
            c.add_port(p2)


def test_add_ref_connected() -> None:
    with gw.Layout():
        # Parent cell
        top = gw.Layout.get_active().create_cell()

        # Add c1 at origin
        c1 = _cell_ports_fixed_out()
        inst1 = top.add_ref(c1, origin=(0.0, 0.0))

        # Connect c2 to c1's "out" port
        c2 = _cell_ports_c2_conn()
        target_port = inst1["out"]
        inst2 = top.add_ref_connected(c2, port_name="in", target_port=target_port)

        # c2's "in" port should now be at (10, 0)
        assert inst2.dtrans.disp.x == pytest.approx(10.0)
        assert inst2.dtrans.disp.y == pytest.approx(0.0)
        assert inst2.dtrans.angle == 0


def test_add_ref_connected_rotated() -> None:
    with gw.Layout():
        top = gw.Layout.get_active().create_cell()
        c1 = _cell_ports_fixed_out()
        inst1 = top.add_ref(c1, origin=(0.0, 0.0), rotation=90)
        # inst1 transforms (10, 0) -> (0, 10). Angle 0 -> 90.

        # Connect c2's "in" to c1's "out"
        c2 = _cell_ports_c2_conn_rot()
        target_port = inst1["out"]
        inst2 = top.add_ref_connected(c2, port_name="in", target_port=target_port)

        assert inst2.dtrans.angle == 2  # 180 degrees
        assert inst2.dtrans.disp.x == pytest.approx(5.0)
        assert inst2.dtrans.disp.y == pytest.approx(10.0)


def test_port_promotion() -> None:
    with gw.Layout():
        c_parent = gw.Layout.get_active().create_cell()
        c_sub = _cell_ports_sub()
        inst = c_parent.add_ref(c_sub, origin=(10.0, 10.0), rotation=90)

        # Promote port
        # Traditionally we'd call a method, but user said "just use add_port"
        # and "ports of subcells should be promotable"
        promoted_port = inst["p1"].renamed("promoted_p1")
        c_parent.add_port(promoted_port)

        assert c_parent["promoted_p1"].name == "promoted_p1"
        # (1, 0) rotated 90 -> (0, 1). Translated (10, 10) -> (10, 11)
        assert c_parent["promoted_p1"].position[0] == pytest.approx(10.0)
        assert c_parent["promoted_p1"].position[1] == pytest.approx(11.0)
        assert c_parent["promoted_p1"].angle == pytest.approx(90)


def test_port_metadata() -> None:
    import json

    with gw.Layout():
        c = _cell_ports_meta()

        # Verify it's in KLayout meta-info
        ports_json = c.kdb.meta_info("ports").value
        ports_dict = json.loads(ports_json)

        assert "p1" in ports_dict
        assert ports_dict["p1"]["position"] == [0.0, 0.0]
        assert ports_dict["p1"]["angle"] == 0

        assert "p2" in ports_dict
        assert ports_dict["p2"]["position"] == [10.0, 5.0]
        assert ports_dict["p2"]["angle"] == 90


def test_port_restoration() -> None:
    with gw.Layout() as layout:
        c1 = _cell_ports_restoration()

        # New cell wrapper around the same kdb cell
        c2 = gw.Cell._from_kdb_cell(c1.kdb, layout=layout)

        assert "p1" in c2.ports
        assert c2["p1"].position == (1.2, 3.4)
        assert c2["p1"].angle == 90


def test_auto_freeze() -> None:
    with gw.Layout() as layout:
        c1 = _cell_ports_empty()

        c2 = gw.Cell._from_kdb_cell(c1.kdb, layout=layout)
        assert c2.frozen

        # Test that modifications are blocked
        with pytest.raises(RuntimeError, match="frozen"):
            c2.add_port(gw.Port("p2", (0, 0), 0, cross_section=xs))
