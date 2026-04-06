# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import pytest

import gdswell as gw
from gdswell.components.straight import straight
from gdswell.netlist import extract_netlist

xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))


@gw.cell
def _cell_double_conn() -> gw.Cell:
    c = gw.Cell()
    c.add_ref(straight(xs, length=10.0), origin=(0, 0))
    c.add_ref(straight(xs, length=10.0), origin=(10, 0))
    # This one also connects to o2 of the first instance (at 10,0)
    c.add_ref(straight(xs, length=10.0), origin=(10, 0), rotation=180)
    return c


@gw.cell
def _cell_conn_and_exp() -> gw.Cell:
    c = gw.Cell()
    s1 = c.add_ref(straight(xs, length=10.0), origin=(0, 0))
    c.add_ref_connected(straight(xs, length=10.0), "0", s1["1"])
    # Expose a port that is already connected internally
    c.add_port(s1["1"].renamed("illegal_exposure"))
    return c


@gw.cell
def _cell_double_exp() -> gw.Cell:
    c = gw.Cell()
    s1 = c.add_ref(straight(xs, length=10.0), origin=(0, 0))
    c.add_port(s1["0"].renamed("exp1"))
    c.add_port(s1["0"].renamed("exp2"))  # Same sub-port exposed twice
    return c


@pytest.fixture(autouse=True)
def isolated_layout():
    """Ensure each test runs with a fresh active layout."""
    with gw.Layout() as ly:
        yield ly


def test_netlist_validation_double_connection():
    circuit = _cell_double_conn()
    with pytest.raises(RuntimeError, match="is already connected"):
        extract_netlist(circuit)


def test_netlist_validation_connected_and_exposed():
    circuit = _cell_conn_and_exp()
    with pytest.raises(RuntimeError, match="is already connected"):
        extract_netlist(circuit)


def test_test_netlist_validation_double_exposure():
    circuit = _cell_double_exp()
    with pytest.raises(RuntimeError, match="is already exposed"):
        extract_netlist(circuit)
