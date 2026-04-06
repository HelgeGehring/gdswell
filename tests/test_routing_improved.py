# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import functools
from enum import Enum

import gdswell as gw
from gdswell.components.bend_circular import bend_circular
from gdswell.components.straight import straight
from gdswell.routing import (
    _get_route_l_components_raw,
    _get_route_u_components_raw,
    _get_route_z_components_raw,
)


class MyLayers(gw.Layer, Enum):
    WG = (1, 0)


DEFAULT_XS = gw.CrossSection((gw.LayerSection("core", MyLayers.WG, 0.5),))


def test_z_route_default_behavior():
    p1 = gw.Port("p1", (0, 0), 0, DEFAULT_XS)
    p2 = gw.Port("p2", (100, 50), 180, DEFAULT_XS)
    radius = 10.0

    # New behavior: bend as early as possible (l1 = 0)
    # Expected: [bend(10, 90), straight(30), bend(10, -90), straight(80)]

    dx, dy = p2.position[0] - p1.position[0], p2.position[1] - p1.position[1]
    bend = functools.partial(bend_circular, DEFAULT_XS)
    straight_f = functools.partial(straight, DEFAULT_XS)
    comps = _get_route_z_components_raw(dx, dy, radius, bend, straight_f)

    print("\nZ-route default behavior:")
    resolved_comps = []
    for i, c in enumerate(comps):
        if callable(c) and not isinstance(c, gw.Cell):
            c = c()
        resolved_comps.append(c)
        print(f"  {i}: {c.name}")

    # First component should be a bend
    assert "bend" in resolved_comps[0].name
    # Total distance covered in X should be 100
    # Bend covers radius (10) in X each.
    # bend(90) covers radius in X.
    # bend(-90) covers radius in X.
    # Total X = 10 + 0 (straight) + 10 + 80 = 100.
    assert len(resolved_comps) == 4
    assert "straight" in resolved_comps[3].name


def test_z_route_start_straight_length():
    p1 = gw.Port("p1", (0, 0), 0, DEFAULT_XS)
    p2 = gw.Port("p2", (100, 50), 180, DEFAULT_XS)
    radius = 10.0
    start_straight_length = 20.0

    # Expected: [straight(20), bend(10, 90), straight(30), bend(10, -90), straight(60)]

    # Calculate remaining dx, dy AFTER the start straight
    dx, dy = (
        p2.position[0] - (p1.position[0] + start_straight_length),
        p2.position[1] - p1.position[1],
    )
    bend = functools.partial(bend_circular, DEFAULT_XS)
    straight_f = functools.partial(straight, DEFAULT_XS)
    comps_raw = _get_route_z_components_raw(
        dx,
        dy,
        radius,
        bend,
        straight_f,
    )
    comps = [functools.partial(straight_f, start_straight_length)] + comps_raw

    print("\nZ-route with start_straight_length=20:")
    resolved_comps = []
    for i, c in enumerate(comps):
        if callable(c) and not isinstance(c, gw.Cell):
            c = c()
        resolved_comps.append(c)
        print(f"  {i}: {c.name}")

    assert "straight" in resolved_comps[0].name
    assert "bend" in resolved_comps[1].name
    assert len(resolved_comps) == 5


def test_l_route_default_behavior():
    p1 = gw.Port("p1", (0, 0), 0, DEFAULT_XS)
    p2 = gw.Port(
        "p2", (50, 50), 270, DEFAULT_XS
    )  # Faces DOWN, we must arrive from BOTTOM (angle 90)
    radius = 10.0

    # Expected: [straight(40), bend(10, 90), straight(40)]
    dx, dy = p2.position[0] - p1.position[0], p2.position[1] - p1.position[1]
    bend = functools.partial(bend_circular, DEFAULT_XS)
    straight_f = functools.partial(straight, DEFAULT_XS)
    comps = _get_route_l_components_raw(dx, dy, radius, bend, straight_f)

    print("\nL-route default behavior:")
    resolved_comps = []
    for i, c in enumerate(comps):
        if callable(c) and not isinstance(c, gw.Cell):
            c = c()
        resolved_comps.append(c)
        print(f"  {i}: {c.name}")

    assert "straight" in resolved_comps[0].name
    assert "bend" in resolved_comps[1].name
    assert "straight" in resolved_comps[2].name


def test_u_route_default_behavior():
    p1 = gw.Port("p1", (0, 0), 0, DEFAULT_XS)
    p2 = gw.Port("p2", (50, 50), 0, DEFAULT_XS)  # Target flow 180 (opposite of 0)
    # Wait, p2 face 0, so we must face 180.
    # U-route from 0: bend(90)->90, bend(90)->180.
    radius = 10.0

    dx, dy = p2.position[0] - p1.position[0], p2.position[1] - p1.position[1]
    bend = functools.partial(bend_circular, DEFAULT_XS)
    straight_f = functools.partial(straight, DEFAULT_XS)
    comps = _get_route_u_components_raw(dx, dy, radius, bend, straight_f)

    print("\nU-route default behavior:")
    resolved_comps = []
    for i, c in enumerate(comps):
        if callable(c) and not isinstance(c, gw.Cell):
            c = c()
        resolved_comps.append(c)
        print(f"  {i}: {c.name}")

    assert len(resolved_comps) >= 4  # straight, bend, straight, bend (and maybe straight)


if __name__ == "__main__":
    test_z_route_default_behavior()
    test_z_route_start_straight_length()
    test_l_route_default_behavior()
    test_u_route_default_behavior()
    print("\nAll tests passed!")
