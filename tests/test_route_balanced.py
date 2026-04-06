# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import gdswell as gw
from gdswell.routing import _get_route_z_components_raw


def test_route_z_balanced() -> None:
    c = gw.Cell()
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))

    # Port 1 at (0,0) facing 0 (+x)
    # Port 2 at (20, 10) facing 180 (-x)
    # dx = 20, dy = 10, radius = 4
    # Wide Z: dx >= 2*radius (8) and dy >= 2*radius (8)

    p1 = gw.Port("1", (0, 0), 0, xs)
    p2 = gw.Port("2", (20, 10), 180, xs)

    # 1. Greedy (Default)
    gw.route_z(c, p1, p2, radius=4, balanced=False)

    # Inspect components of the route cell
    # In route_step_by_step, it uses chain_components which adds refs in order.
    # We can check the sequence of components.
    # _get_route_z_components_raw for greedy:
    # [bend(4, 90), straight(10-8=2), bend(4, -90), straight(20-8=12)]

    # Actually, let's just use the raw component generator for easier inspection
    def dummy_bend(r, a):
        return f"bend({r},{a})"

    def dummy_straight(length):
        return f"straight({length})"

    comps_greedy = _get_route_z_components_raw(
        20, 10, 4, dummy_bend, dummy_straight, balanced=False
    )
    # Results are partials, let's call them
    names_greedy = [p() for p in comps_greedy]
    assert names_greedy == ["bend(4,90)", "straight(2)", "bend(4,-90)", "straight(12)"]

    # 2. Balanced
    comps_balanced = _get_route_z_components_raw(
        20, 10, 4, dummy_bend, dummy_straight, balanced=True
    )
    names_balanced = [p() for p in comps_balanced]
    # (dx - 2*radius)/2 = (20 - 8)/2 = 6
    assert names_balanced == [
        "straight(6.0)",
        "bend(4,90)",
        "straight(2)",
        "bend(4,-90)",
        "straight(6.0)",
    ]


def test_route_manhattan_balanced_dispatch() -> None:
    c = gw.Cell()
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))
    p1 = gw.Port("1", (0, 0), 0, xs)
    p2 = gw.Port("2", (20, 10), 180, xs)

    # Verify it doesn't crash and connects correctly
    inst = gw.route_manhattan(c, p1, p2, radius=4, balanced=True)
    assert inst["0"].connects_to(p1)
    assert inst["1"].connects_to(p2)


if __name__ == "__main__":
    test_route_z_balanced()
    test_route_manhattan_balanced_dispatch()
    print("Tests passed!")
