# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from enum import Enum

import pytest

import gdswell as gw


class MyLayers(gw.Layer, Enum):
    WG = (1, 0)
    CLAD = (2, 0)


ls1 = gw.LayerSection("core", MyLayers.WG, 0.5)
xs1 = gw.CrossSection((ls1,))

ls2 = gw.LayerSection("core", MyLayers.WG, 0.5)
xs2 = gw.CrossSection((ls2,))

ls3 = gw.LayerSection("core", MyLayers.WG, 0.6)
xs3 = gw.CrossSection((ls3,))


@gw.cell
def matching_cell1() -> gw.Cell:
    c = gw.Cell()
    c.add_port(gw.Port("p1", (0, 0), 0, cross_section=xs1))
    return c


@gw.cell
def matching_cell2() -> gw.Cell:
    c = gw.Cell()
    c.add_port(gw.Port("p2", (0, 0), 180, cross_section=xs2))
    return c


@gw.cell
def matching_cell3() -> gw.Cell:
    c = gw.Cell()
    c.add_port(gw.Port("p3", (0, 0), 180, cross_section=xs3))
    return c


@gw.cell
def mismatch_cell1() -> gw.Cell:
    c = gw.Cell()
    c.add_port(gw.Port("p1", (0, 0), 0, cross_section=xs1))
    return c


@gw.cell
def mismatch_cell2() -> gw.Cell:
    c = gw.Cell()
    c.add_port(gw.Port("p2", (0, 0), 180, cross_section=xs3))
    return c


def test_cross_section_matching() -> None:
    with gw.Layout():
        c1 = matching_cell1()
        c2 = matching_cell2()
        c3 = matching_cell3()

        top = gw.Layout.get_active().create_cell()
        inst1 = top.add_ref(c1)

        # This should pass (matching XS)
        top.add_ref_connected(c2, "p2", inst1["p1"])

        # This should fail (mismatching XS)
        with pytest.raises(ValueError, match="Cross-section mismatch"):
            top.add_ref_connected(c3, "p3", inst1["p1"])

        # This should pass with ignore_xs_mismatch=True
        top.add_ref_connected(c3, "p3", inst1["p1"], ignore_xs_mismatch=True)


def test_cross_section_matching_one_none() -> None:
    with gw.Layout():
        c1 = mismatch_cell1()
        c2 = mismatch_cell2()

        top = gw.Layout.get_active().create_cell()
        inst1 = top.add_ref(c1)

        # XS mismatch
        with pytest.raises(ValueError, match="Cross-section mismatch"):
            top.add_ref_connected(c2, "p2", inst1["p1"])
