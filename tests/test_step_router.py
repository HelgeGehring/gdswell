# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import pytest

import gdswell as gw
from gdswell.components.bend_circular import bend_circular
from gdswell.components.straight import straight


def test_step_router_valid() -> None:
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))

    p1 = gw.Port("0", (0, 0), 0, xs)  # Facing +x
    p2 = gw.Port("1", (10, 10), 270, xs)  # Facing down (-y) to connect to +y flow

    # Pass component cells directly
    components = [
        straight(xs, 5),
        bend_circular(xs, 5, 90),
        straight(xs, 5),
    ]

    c = gw.Cell()
    inst = gw.route_step_by_step(c, p1, p2, components)
    assert isinstance(inst, gw.Instance)
    # The result now contains a single instance of the chained cell
    assert len(list(c.kdb.each_inst())) == 1
    assert not c.kdb.bbox().empty()


def test_step_router_invalid() -> None:
    gw.config.async_cells = False
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))

    p1 = gw.Port("0", (0, 0), 0, xs)
    p2 = gw.Port("1", (10, 10), 270, xs)

    # This route ends at (5, 0), which is NOT (10, 10)
    components = [
        straight(xs, 5),
    ]

    c = gw.Cell()
    with pytest.raises(RuntimeError) as excinfo:
        gw.route_step_by_step(c, p1, p2, components)

    assert "Route failed" in str(excinfo.value)


def test_chain_components() -> None:
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))

    components = [
        straight(xs, 5),
        straight(xs, 5),
    ]

    c = gw.chain_components(components)
    assert len(list(c.kdb.each_inst())) == 2
    assert "0" in c.ports
    assert "1" in c.ports
    # First component was at (0,0), its 0 is (0,0) facing 180
    assert c["0"].position[0] == pytest.approx(0.0)
    assert c["0"].angle == pytest.approx(180.0)
    # Final port should be at (10, 0) facing 0
    assert c["1"].position[0] == pytest.approx(10.0)
    assert c["1"].position[1] == pytest.approx(0.0)
    assert c["1"].angle == pytest.approx(0.0)
