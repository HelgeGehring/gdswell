# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import gdswell as gw
from gdswell.components.straight import straight

xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))


@gw.cell
def _cell_simple_circuit() -> gw.Cell:
    c = gw.Cell()
    s1 = c.add_ref(straight(xs, length=10.0))
    s2 = c.add_ref_connected(straight(xs, length=20.0), "0", s1["1"])

    c.add_port(s1["0"].renamed("in"))
    c.add_port(s2["1"].renamed("out"))
    return c


@gw.cell
def _cell_manual_circuit() -> gw.Cell:
    c = gw.Cell()
    c.add_ref(straight(xs, length=10.0), origin=(0, 0))
    # Place s2 such that its o1 is exactly at s1's o2 (10, 0)
    c.add_ref(straight(xs, length=20.0), origin=(10, 0))
    return c


def test_netlist_extraction() -> None:
    circuit = _cell_simple_circuit()
    from gdswell.netlist import extract_netlist

    netlist = extract_netlist(circuit)

    keys = list(netlist.instances.keys())
    assert len(keys) == 2
    instA, instB = keys[0], keys[1]

    assert len(netlist.connections) == 1
    conn = netlist.connections[0]

    valid_pair = (
        conn.endpoint1.inst == instA
        and conn.endpoint1.port == "1"
        and conn.endpoint2.inst == instB
        and conn.endpoint2.port == "0"
    ) or (
        conn.endpoint2.inst == instA
        and conn.endpoint2.port == "1"
        and conn.endpoint1.inst == instB
        and conn.endpoint1.port == "0"
    )
    assert valid_pair, f"Invalid connection found: {conn}"

    assert len(netlist.exposed_ports) == 2
    assert "in" in netlist.exposed_ports
    assert netlist.exposed_ports["in"].inst in keys
    assert netlist.exposed_ports["in"].port == "0"

    assert "out" in netlist.exposed_ports
    assert netlist.exposed_ports["out"].inst in keys
    assert netlist.exposed_ports["out"].port == "1"


def test_netlist_manual_placement() -> None:
    circuit = _cell_manual_circuit()
    from gdswell.netlist import extract_netlist

    netlist = extract_netlist(circuit)

    keys = list(netlist.instances.keys())
    assert len(keys) == 2
    instA, instB = keys[0], keys[1]

    assert len(netlist.connections) == 1
    conn = netlist.connections[0]

    valid_pair = (
        conn.endpoint1.inst == instA
        and conn.endpoint1.port == "1"
        and conn.endpoint2.inst == instB
        and conn.endpoint2.port == "0"
    ) or (
        conn.endpoint2.inst == instA
        and conn.endpoint2.port == "1"
        and conn.endpoint1.inst == instB
        and conn.endpoint1.port == "0"
    )
    assert valid_pair, f"Manual connection not detected: {conn}"
