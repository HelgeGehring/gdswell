# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from typing import Any

import gdswell as gw
from gdswell.components.straight import straight
from gdswell.cross_section import CrossSection, LayerSection
from gdswell.layer import Layer
from gdswell.netlist import Endpoint, Netlist, hierarchical_extract

# Define a simple cross-section for the test
layer = Layer(1, 0)
ls = LayerSection(name="core", layer=layer, width=0.5)
xs = CrossSection(layer_sections=(ls,))


@gw.cell
def composite_cell() -> gw.Cell:
    c = gw.Cell()
    # Instantiate two straights in a chain
    s1 = c.add_ref(straight(cross_section=xs, length=10.0))
    s2 = c.add_ref(straight(cross_section=xs, length=20.0), origin=(10.0, 0))

    # Expose ports
    c.add_port(s1["0"].renamed("p1"))
    c.add_port(s2["1"].renamed("p2"))
    return c


def process_straight(cell: gw.Cell, sub_results: dict[str, Any], netlist: Netlist) -> Any:
    return {("0", "1"): cell.info["length"]}


def process_composite_recursive(
    cell: gw.Cell, sub_results: dict[str, Any], netlist: Netlist
) -> Any:
    """Recursive processor with loop detection."""
    conns = {c.endpoint1: c.endpoint2 for c in netlist.connections}
    conns.update({c.endpoint2: c.endpoint1 for c in netlist.connections})

    def find_dist(curr: Endpoint, target: Endpoint, visited: set[Endpoint]) -> float | None:
        if curr == target:
            return 0.0
        if curr in visited:
            return None

        visited.add(curr)
        # Try internal paths in this instance
        for (s, d), length in sub_results.get(curr.inst, {}).items():
            for src, dst in [(s, d), (d, s)]:
                if src == curr.port:
                    nxt = Endpoint(curr.inst, dst)
                    if (d_val := find_dist(nxt, target, visited)) is not None:
                        return length + d_val

        # Try netlist connections
        if nxt := conns.get(curr):
            if (d_val := find_dist(nxt, target, visited)) is not None:
                return d_val

        return None

    eps = netlist.exposed_ports
    names = list(eps.keys())
    return {
        (names[i], names[j]): d
        for i in range(len(names))
        for j in range(i + 1, len(names))
        if (d := find_dist(eps[names[i]], eps[names[j]], set())) is not None
    }


def test_hierarchical_length_recursive():
    with gw.Layout():
        top = composite_cell()

        mapping = {"straight": process_straight, "composite_cell": process_composite_recursive}

        result = hierarchical_extract(top, mapping)
        # Expected: 10.0 + 20.0 = 30.0
        assert result[("p1", "p2")] == 30.0


if __name__ == "__main__":
    test_hierarchical_length_recursive()
    print("Test passed!")
