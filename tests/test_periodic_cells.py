# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from enum import Enum

import pytest

import gdswell as gw
from gdswell.components.generic_path import generic_path
from gdswell.components.straight import straight

# Disable async and cache for deterministic testing
gw.config.async_cells = False
gw.config.use_disk_cache = False


class MyLayers(gw.Layer, Enum):
    WG = (1, 0)
    CLADDING = (2, 0)


@gw.cell
def sample_cell() -> gw.Cell:
    c = gw.Cell()
    c.add_polygon([(0, 0), (1, 0), (1, 1), (0, 1)], MyLayers.WG)
    return c


def test_component_section_initialization():
    cell = sample_cell()
    cs = gw.CellSection(name="dots", cell=cell, periodicity=5.0, x_offset_initial=1.0, y_offset=2.0)
    assert cs.name == "dots"
    assert cs.cell == cell
    assert float(cs.periodicity) == 5.0
    assert float(cs.x_offset_initial) == 1.0
    assert float(cs.y_offset) == 2.0


def test_straight_periodic_component():
    cell = sample_cell()
    # periodicity 5, length 11 -> placements at 0, 5, 10 (3 total)
    cs = gw.CellSection(name="dots", cell=cell, periodicity=5.0)
    xs = gw.CrossSection(cell_sections=(cs,))

    c = straight(cross_section=xs, length=11.0)

    # Check number of instances
    assert len(c.instances) == 3

    # Check positions - use dtrans.disp for microns
    positions = sorted([inst.dtrans.disp for inst in c.instances], key=lambda d: d.x)
    assert positions[0].x == pytest.approx(0.0)
    assert positions[1].x == pytest.approx(5.0)
    assert positions[2].x == pytest.approx(10.0)


def test_periodic_x_y_offset():
    cell = sample_cell()
    # x_offset_initial 2, periodicity 5, length 10 -> placements at 2, 7 (2 total)
    # y_offset 3
    cs = gw.CellSection(name="dots", cell=cell, periodicity=5.0, x_offset_initial=2.0, y_offset=3.0)
    xs = gw.CrossSection(cell_sections=(cs,))

    c = straight(cross_section=xs, length=10.0)

    assert len(c.instances) == 2
    positions = sorted([inst.dtrans.disp for inst in c.instances], key=lambda d: d.x)

    assert positions[0].x == pytest.approx(2.0)
    assert positions[0].y == pytest.approx(3.0)
    assert positions[1].x == pytest.approx(7.0)
    assert positions[1].y == pytest.approx(3.0)


def test_mixed_sections():
    cell = sample_cell()
    ls = gw.LayerSection(name="core", layer=MyLayers.WG, width=2.0)
    cs = gw.CellSection(name="dots", cell=cell, periodicity=10.0, y_offset=5.0)
    xs = gw.CrossSection(layer_sections=(ls,), cell_sections=(cs,))

    c = straight(cross_section=xs, length=25.0)

    # Check polygons exist on WG layer
    assert not c.is_empty(MyLayers.WG)
    # Instances for CellSection (at 0, 10, 20)
    assert len(c.instances) == 3

    # Check y-offset of instances
    for inst in c.instances:
        assert inst.dtrans.disp.y == pytest.approx(5.0)


def test_periodic_on_generic_path_manhattan():
    cell = sample_cell()
    # Length 20. periodicity 8 -> placements at 0, 8, 16
    cs = gw.CellSection(name="dots", cell=cell, periodicity=8.0)
    xs = gw.CrossSection(cell_sections=(cs,))

    # Straight path along Y
    c = generic_path(cross_section=xs, x_expr=0 * gw.S, y_expr=20 * gw.S, npoints=100)

    assert len(c.instances) == 3
    positions = sorted([inst.dtrans.disp for inst in c.instances], key=lambda d: d.y)
    assert positions[0].y == pytest.approx(0.0)
    assert positions[1].y == pytest.approx(8.0)
    assert positions[2].y == pytest.approx(16.0)

    # Check rotation (along Y means 90 degrees)
    for inst in c.instances:
        assert inst.dtrans.angle == 1


def test_x_offset_final():
    cell = sample_cell()
    # length 10, periodicity 3.
    # placements at: 0, 3, 6, 9
    # with x_offset_final = 2.0 -> valid range [0, 8.0]
    # expected placements: 0, 3, 6
    cs = gw.CellSection(name="dots", cell=cell, periodicity=3.0, x_offset_final=2.0)
    xs = gw.CrossSection(cell_sections=(cs,))
    c = straight(cross_section=xs, length=10.0)

    assert len(c.instances) == 3
    positions = sorted([inst.dtrans.disp.x for inst in c.instances])
    assert positions[0] == pytest.approx(0.0)
    assert positions[1] == pytest.approx(3.0)
    assert positions[2] == pytest.approx(6.0)


def test_cross_section_equality_ignores_cells():
    ls = gw.LayerSection(name="core", layer=MyLayers.WG, width=2.0)
    cell = sample_cell()
    cs = gw.CellSection(name="dots", cell=cell, periodicity=10.0)

    xs1 = gw.CrossSection(layer_sections=(ls,))
    xs2 = gw.CrossSection(layer_sections=(ls,), cell_sections=(cs,))

    # These should be equal because they have the same LayerSections
    assert xs1 == xs2

    # However, different LayerSections should NOT be equal
    ls2 = gw.LayerSection(name="core", layer=MyLayers.WG, width=3.0)
    xs3 = gw.CrossSection(layer_sections=(ls2,))
    assert xs1 != xs3


def test_cell_section_serialization():
    cell = sample_cell()
    cs = gw.CellSection(
        name="dots",
        cell=cell,
        periodicity=5.0,
        x_offset_initial=1.0,
        x_offset_final=2.0,
        y_offset=0.5,
    )

    # Serialize
    data = cs.to_dict()
    assert data["type"] == "CellSection"
    assert data["cell"] == cell.name
    assert data["periodicity"] == 5.0

    # Deserialize (requires layout)
    layout = cell.layout
    cs_restored = gw.CellSection.from_dict(data, layout=layout)

    assert cs_restored.name == cs.name
    assert cs_restored.cell == cs.cell
    assert float(cs_restored.periodicity) == float(cs.periodicity)
    assert float(cs_restored.x_offset_initial) == float(cs.x_offset_initial)
    assert float(cs_restored.x_offset_final) == float(cs.x_offset_final)
    assert float(cs_restored.y_offset) == float(cs.y_offset)


def test_cross_section_serialization():
    cell = sample_cell()
    ls = gw.LayerSection(name="core", layer=MyLayers.WG, width=2.0)
    cs = gw.CellSection(name="dots", cell=cell, periodicity=10.0)
    xs = gw.CrossSection(layer_sections=(ls,), cell_sections=(cs,))

    # Serialize
    data = xs.to_dict()
    assert len(data["layer_sections"]) == 1
    assert len(data["cell_sections"]) == 1

    # Deserialize
    layout = cell.layout
    xs_restored = gw.CrossSection.from_dict(data, layout=layout)

    assert len(xs_restored.layer_sections) == 1
    assert len(xs_restored.cell_sections) == 1
    assert isinstance(xs_restored.cell_sections[0], gw.CellSection)
    assert xs_restored.cell_sections[0].cell == cell
    assert xs_restored.cell_sections[0].name == "dots"
    assert xs_restored.cell_sections[0].name == "dots"


def test_transition_with_cell_sections_raises_error():
    cell = sample_cell()
    ls = gw.LayerSection(name="core", layer=MyLayers.WG, width=2.0)
    cs = gw.CellSection(name="dots", cell=cell, periodicity=10.0)
    xs1 = gw.CrossSection(layer_sections=(ls,), cell_sections=(cs,))
    xs2 = gw.CrossSection(layer_sections=(ls,))

    with pytest.raises(ValueError, match="CrossSection transition is not supported"):
        xs1.transition(xs2)

    with pytest.raises(ValueError, match="CrossSection transition is not supported"):
        xs2.transition(xs1)
