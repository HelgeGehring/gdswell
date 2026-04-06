# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import pytest

import gdswell as gw
from gdswell.components.straight import straight


@pytest.fixture(autouse=True)
def isolated_layout():
    with gw.Layout() as ly:
        yield ly


# def test_manual_freeze_validation_error():
#     xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))

#     c = gw.Cell()
#     c.kdb.name = "my_cell"  # Required for freeze
#     s1 = c.add_ref(straight(xs, length=10.0), origin=(0, 0))
#     c.add_ref_connected(straight(xs, length=10.0), "0", s1["1"])

#     # Double exposure
#     c.add_port(s1["1"].renamed("illegal_exposure"))

#     with pytest.raises(RuntimeError, match="is already connected"):
#         c.freeze()


def test_manual_freeze_success():
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))

    c = gw.Cell()
    c.kdb.name = "good_cell"
    c.add_ref(straight(xs, length=10.0), origin=(0, 0))

    # Should not raise
    c.freeze()
    assert c.frozen
