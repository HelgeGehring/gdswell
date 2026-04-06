# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from enum import Enum

import gdswell as gw


class Pdk(gw.Layer, Enum):
    WG = (1, 0)


@gw.cell
def my_sub_cell() -> gw.Cell:
    c = gw.Cell()
    c.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], Pdk.WG)
    return c


@gw.cell
def top_new_cell() -> gw.Cell:
    c = gw.Cell()
    c.add_ref(my_sub_cell())
    return c


def test_cell_copy_new_subcell() -> None:
    """Verify that Cell copies new sub-cells when they don't exist in target layout."""

    l1 = gw.Layout()
    with l1:
        top1 = top_new_cell()
        sub_name = my_sub_cell().name
        top_name = top1.name

    l2 = gw.Layout()
    with l2:
        top2 = gw.Cell._from_kdb_cell(top1.kdb, layout=l2)

    assert l2.kdb.has_cell(top_name)
    assert l2.kdb.has_cell(sub_name)

    kdb_top2 = top2.kdb
    for inst in kdb_top2.each_inst():
        inst_cell = l2.kdb.cell(inst.cell_index)
        assert inst_cell.name == sub_name
        assert inst_cell.shapes(l2.layer(Pdk.WG)).size() == 1
