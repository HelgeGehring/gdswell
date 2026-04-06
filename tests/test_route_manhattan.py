# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import gdswell as gw


def test_route_manhattan_l() -> None:
    c = gw.Cell()
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))

    p1 = gw.Port("1", (0, 0), 0, xs)  # Facing +x
    p2 = gw.Port("2", (20, 20), 270, xs)  # Facing down, connect from up (+y)

    # L-route: 0 -> 90. dx=20, dy=20, R=5.
    # Segments: straight(15), bend(90), straight(15).
    inst = gw.route_manhattan(c, p1, p2, radius=5)

    assert inst["0"].connects_to(p1)
    assert inst["1"].connects_to(p2)


def test_route_manhattan_z() -> None:
    c = gw.Cell()
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))

    p1 = gw.Port("1", (0, 0), 0, xs)  # Facing +x
    p2 = gw.Port("2", (20, 10), 180, xs)  # Facing left, connect from right (+x)

    # Z-route: Parallel, opposite. dx=20, dy=10, R=4.
    # dx_needed = 2R = 8. dx=20 (ok).
    # dy_needed = 2R = 8. dy=10 (ok).
    inst = gw.route_manhattan(c, p1, p2, radius=4)

    assert inst["0"].connects_to(p1)
    assert inst["1"].connects_to(p2)


def test_route_manhattan_u() -> None:
    c = gw.Cell()
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))

    p1 = gw.Port("1", (0, 0), 0, xs)  # Facing +x
    p2 = gw.Port("2", (10, 20), 0, xs)  # Facing right, connect from left (+x)

    # U-route: Parallel, same direction. dx=10, dy=20, R=5.
    inst = gw.route_manhattan(c, p1, p2, radius=5)

    assert inst["0"].connects_to(p1)
    assert inst["1"].connects_to(p2)


def test_route_manhattan_z_jog() -> None:
    c = gw.Cell()
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))

    # Z-jog: p1=(0,0) facing +x, p2=(30, 2) facing -x. R=5.
    # dx=30 >= 4R=20. dy=2 < 2R=10.
    p1 = gw.Port("1", (0, 0), 0, xs)
    p2 = gw.Port("2", (30, 2), 180, xs)

    inst = gw.route_manhattan(c, p1, p2, radius=5)

    assert inst["0"].connects_to(p1)
    assert inst["1"].connects_to(p2)


def test_route_manhattan_z_loop() -> None:
    c = gw.Cell()
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))

    # Z-loop: p1=(0,0) facing +x, p2=(-10, 30) facing -x. R=5.
    # dx=-10 < 0. dy=30 >= 4R=20.
    p1 = gw.Port("1", (0, 0), 0, xs)
    p2 = gw.Port("2", (-10, 30), 180, xs)

    inst = gw.route_manhattan(c, p1, p2, radius=5)

    assert inst["0"].connects_to(p1)
    assert inst["1"].connects_to(p2)


def test_route_manhattan_l_tight() -> None:
    c = gw.Cell()
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))

    # Tight L: p1=(0,0) facing +x, p2=(2, 30) facing +y (connect from 270)
    # dx=2 < R=5. dy=30.
    p1 = gw.Port("1", (0, 0), 0, xs)
    p2 = gw.Port("2", (2, 30), 270, xs)

    inst = gw.route_manhattan(c, p1, p2, radius=5)

    assert inst["0"].connects_to(p1)
    assert inst["1"].connects_to(p2)
