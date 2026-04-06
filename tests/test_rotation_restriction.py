# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import pytest

from gdswell.cell import Cell
from gdswell.cross_section import CrossSection, LayerSection
from gdswell.layer import Layer
from gdswell.layout import Layout
from gdswell.port import Port


def test_add_ref_rotation_restriction():
    ly = Layout()

    class MyCell(Cell):
        def __init__(self, name):
            super().__init__(layout=ly)
            self._kdb_cell.name = name

    child = MyCell("Child")
    child.freeze()

    parent = MyCell("Parent")

    # Valid rotations
    parent.add_ref(child, rotation=0)
    parent.add_ref(child, rotation=90)
    parent.add_ref(child, rotation=180)
    parent.add_ref(child, rotation=270)
    parent.add_ref(child, rotation=360)  # type: ignore # 360 % 90 == 0

    # Invalid rotations
    with pytest.raises(ValueError, match="Rotation must be a multiple of 90 degrees"):
        parent.add_ref(child, rotation=45)  # type: ignore

    with pytest.raises(ValueError, match="Rotation must be a multiple of 90 degrees"):
        parent.add_ref(child, rotation=0.1)  # type: ignore


def test_add_ref_connected_rotation_restriction():
    ly = Layout()
    xs = CrossSection(layer_sections=(LayerSection(name="core", layer=Layer(1, 0), width=1.0),))

    class MyCell(Cell):
        def __init__(self, name):
            super().__init__(layout=ly)
            self._kdb_cell.name = name

    # Valid port angle
    p0 = Port(name="p0", position=(0, 0), angle=90, cross_section=xs)

    # Invalid port angle
    with pytest.raises(ValueError, match="Port angle must be a multiple of 90 degrees"):
        Port(name="p1", position=(0, 0), angle=45, cross_section=xs)  # type: ignore

    child = MyCell("Child")
    child.add_port(p0)
    child.freeze()

    # This part of the test is no longer needed because we can't create p1

    parent = MyCell("Parent")
    target_p = Port(name="target", position=(10, 10), angle=0, cross_section=xs)

    # Valid connection (both 90 degree multiples)
    child2 = MyCell("Child2")
    p2 = Port(name="p2", position=(0, 0), angle=90, cross_section=xs)
    child2.add_port(p2)
    child2.freeze()

    parent.add_ref_connected(child2, "p2", target_p)  # rot = (0 + 180 - 90) % 360 = 90
