# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import pytest

from gdswell.cell import Cell
from gdswell.components.straight import straight
from gdswell.cross_section import CrossSection, LayerSection
from gdswell.decorator import cell
from gdswell.layer import Layer
from gdswell.netlist import extract_netlist


# Helpers don't need @cell if they just return another @cell-generated component
def zero_length_adapter(xs1: CrossSection, xs2: CrossSection) -> Cell:
    return straight(xs1.transition(xs2), length=0.0, npoints=2)


l1 = Layer(1, 0)
xs1 = CrossSection(layer_sections=(LayerSection("core", l1, width=1.0),))
xs2 = CrossSection(layer_sections=(LayerSection("core", l1, width=2.0),))


@cell
def _cell_zero_length_circuit():
    c = Cell()
    s1 = straight(xs1, length=10)
    adapter = zero_length_adapter(xs1, xs2)
    s2 = straight(xs2, length=10)

    inst1 = c.add_ref(s1, origin=(0, 0))
    inst_a = c.add_ref_connected(adapter, "0", inst1["1"])
    inst2 = c.add_ref_connected(s2, "0", inst_a["1"])

    c.add_port(inst1["0"].renamed("0"))
    c.add_port(inst2["1"].renamed("1"))
    return c


def tapered_transition(xs1: CrossSection, xs2: CrossSection, length: float) -> Cell:
    return straight(xs1.transition(xs2), length=length, npoints=10)


def test_zero_length_straight_no_geometry():
    adapter = zero_length_adapter(xs1, xs2)

    # Check that it has no shapes on l1
    shape_count = sum(1 for _ in adapter.kdb.each_shape(adapter.layout.layer(l1)))
    assert shape_count == 0, f"Zero-length straight should have 0 shapes, found {shape_count}"

    # Check ports
    assert adapter.ports["0"].cross_section == xs1
    assert adapter.ports["1"].cross_section == xs2
    assert adapter.ports["0"].position == (0.0, 0.0)
    assert adapter.ports["1"].position == (0.0, 0.0)


def test_zero_length_straight_netlist():
    c = _cell_zero_length_circuit()
    netlist = extract_netlist(c)

    # Verify connections: s1 -> adapter -> s2
    assert len(netlist.connections) == 2

    # Check that exposed ports are correct
    assert "0" in netlist.exposed_ports
    assert "1" in netlist.exposed_ports


def test_tapered_straight_has_geometry():
    taper = tapered_transition(xs1, xs2, length=10.0)

    # Check that it HAS shapes
    shape_count = sum(1 for _ in taper.kdb.each_shape(taper.layout.layer(l1)))
    assert shape_count > 0, "Tapered straight should have geometry"

    # Check ports are at different positions
    assert taper.ports["0"].position == (0.0, 0.0)
    assert taper.ports["1"].position == (10.0, 0.0)


if __name__ == "__main__":
    pytest.main([__file__])
