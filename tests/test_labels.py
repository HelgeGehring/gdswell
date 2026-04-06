# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from enum import Enum

import klayout.db as kdb
import pytest

import gdswell as gw


class Pdk(gw.Layer, Enum):
    WG = (1, 0)
    LABEL = (10, 0)


@gw.cell
def frozen_label_cell() -> gw.Cell:
    return gw.Cell()


def test_add_label() -> None:
    layout = gw.Layout()
    cell = layout.create_cell()

    text = "Hello GDS"
    pos = (10.0, 20.0)
    layer = Pdk.LABEL

    shape = cell.add_label(text, pos, layer, rotation=90)

    assert isinstance(shape, kdb.Shape)
    assert shape.is_text()

    # Check underlying KLayout object
    kdb_text = shape.dtext
    assert kdb_text.string == text

    # KLayout DTrans.disp is a DVector, and angle is the rotation index (0..3)
    assert kdb_text.trans.disp.x == pos[0]
    assert kdb_text.trans.disp.y == pos[1]
    assert kdb_text.trans.angle * 90 == 90.0


def test_label_persistence(tmp_path) -> None:
    gds_path = tmp_path / "test_labels.gds"

    with gw.Layout() as layout:
        cell = layout.create_cell()
        cell_name = cell.name
        cell.add_label("PersistMe", (5.0, 5.0), Pdk.LABEL, rotation=180)
        layout.write(str(gds_path))

    # Read back
    layout2 = gw.Layout()
    layout2.kdb.read(str(gds_path))

    # Find the cell and check for the label
    cell2 = layout2.kdb.cell(cell_name)
    layer_index = layout2.kdb.layer(Pdk.LABEL.layer, Pdk.LABEL.datatype)

    shapes = list(cell2.each_shape(layer_index))
    assert len(shapes) == 1
    shape = shapes[0]
    assert shape.is_text()
    assert shape.dtext.string == "PersistMe"
    assert shape.dtext.trans.disp.x == 5.0
    assert shape.dtext.trans.disp.y == 5.0
    assert shape.dtext.trans.angle * 90 == 180.0


def test_frozen_enforcement() -> None:
    with gw.Layout():
        c = frozen_label_cell()
        with pytest.raises(RuntimeError, match="frozen"):
            c.add_label("LateLabel", (0, 0), Pdk.LABEL)
