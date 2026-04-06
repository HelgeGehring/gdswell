# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import numpy as np

from gdswell.cell import Cell
from gdswell.components.bend_circular import bend_circular
from gdswell.components.bend_s import bend_s
from gdswell.components.coupler import coupler
from gdswell.components.straight import straight
from gdswell.cross_section import CrossSection
from gdswell.decorator import cell
from gdswell.routing import chain_components


def test_component_lengths():
    xs = CrossSection()

    s = straight(xs, length=100.0)
    assert s.info["length"] == 100.0

    b = bend_circular(xs, radius=10.0, angle=90.0)
    assert np.isclose(b.info["length"], 10.0 * np.pi / 2)

    s_bend = bend_s(xs, width=50.0, height=20.0)
    assert "length" in s_bend.info
    assert s_bend.info["length"] > 50.0

    # sp = spiral(xs, r0=10.0, dr=5.0, turns=2.0) # Spiral often has non-Manhattan ports
    # assert "length" in sp.info

    c = coupler(xs, length=50.0, gap=10.0)
    assert c.info["length"] == 50.0


def test_chain_components_length():
    xs = CrossSection()

    s1 = straight(xs, length=50.0)
    s2 = straight(xs, length=30.0)
    b1 = bend_circular(xs, radius=10.0, angle=90.0)

    chain = chain_components([s1, b1, s2])

    expected_length = 50.0 + (10.0 * np.pi / 2) + 30.0
    assert np.isclose(chain.info["length"], expected_length)


@cell
def missing_length_cell():
    from gdswell.cross_section import CrossSection
    from gdswell.port import Port

    c = Cell()
    c.add_port(Port("0", (0, 0), 180, CrossSection()))
    c.add_port(Port("1", (10, 0), 0, CrossSection()))
    return c
