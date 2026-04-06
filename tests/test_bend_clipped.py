# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from gdswell.components.bend_circular import bend_circular
from gdswell.cross_section import CrossSection, LayerSection
from gdswell.layer import Layer


def test_bend_circular_clipping():
    """Verify that bend_circular clips layer sections to radius 0 to avoid self-intersection."""
    l1 = Layer(1, 0)
    # Section with offset 15, width 10. Radius 15.
    # Inner edge is at offset 15 + 5 = 20.
    # Since radius is 15, inner edge is "beyond" the center (20 > 15).
    # It should be clipped to 15.
    ls = LayerSection(name="wg", layer=l1, width=10.0, offset=15.0)
    xs = CrossSection(layer_sections=(ls,))

    radius = 15.0
    angle = 90.0
    c = bend_circular(cross_section=xs, radius=radius, angle=angle)

    # Center of rotation for this bend is (0, 15)
    center_y = 15.0

    shapes = c.kdb.shapes(c.layout.layer(l1))
    poly = next(shapes.each()).polygon
    dpoly = poly.to_dtype(c.layout.kdb.dbu)

    for p in dpoly.each_point_hull():
        # All points should be at y <= 15 (clipped to center line or below)
        # using a small epsilon for float precision
        assert p.y <= center_y + 1e-6, f"Point {p} crossed the center of rotation!"


def test_bend_circular_full_clipping():
    """Verify that a section entirely beyond the center is removed (width 0)."""
    l1 = Layer(1, 0)
    # Section with offset 25, width 10. Radius 15.
    # Edges are at 20 and 30. Both are > 15.
    # Both should be clipped to 15, result in width 0.
    ls = LayerSection(name="wg", layer=l1, width=10.0, offset=25.0)
    xs = CrossSection(layer_sections=(ls,))

    radius = 15.0
    angle = 90.0
    c = bend_circular(cross_section=xs, radius=radius, angle=angle)

    assert c.is_empty(l1), "Cell should be empty as the section was entirely clipped."


def test_bend_circular_transition_clipping():
    """Verify that bend_circular handles expression clipping for transitions."""
    from gdswell.cross_section import S

    l1 = Layer(1, 0)
    # Transition from width 10 to 30. Radius 15. Offset 10*S.
    # At s=1: width 30, offset 10 -> inner edge = 10 + 15 = 25 (> 15).
    # Symbolic clipping should pin the inner edge to 15.
    ls = LayerSection(name="wg", layer=l1, width=10 + 20 * S, offset=10 * S)
    xs = CrossSection(layer_sections=(ls,))

    radius = 15.0
    angle = 90.0
    c = bend_circular(cross_section=xs, radius=radius, angle=angle)

    center_y = 15.0
    shapes = c.kdb.shapes(c.layout.layer(l1))
    poly = next(shapes.each()).polygon
    dpoly = poly.to_dtype(c.layout.kdb.dbu)

    for p in dpoly.each_point_hull():
        assert p.y <= center_y + 1e-6, f"Point {p} crossed the center of rotation!"


def test_bend_circular_port_cross_section():
    """Verify that port cross-sections of a clipped bend are NOT clipped."""
    l1 = Layer(1, 0)
    # Section with offset 15, width 10. Radius 15.
    # Inner edge is at offset 15 + 5 = 20.
    # Since radius is 15, inner edge is clipped to 15 in geometry.
    ls = LayerSection(name="wg", layer=l1, width=10.0, offset=15.0)
    xs = CrossSection(layer_sections=(ls,))

    radius = 15.0
    angle = 90.0
    c = bend_circular(cross_section=xs, radius=radius, angle=angle)

    # Port cross-section should have the original width 10.0, not clipped
    # Port "0" (or "1") cross-section check
    xs0 = c.ports["0"].cross_section
    assert xs0.layer_sections[0].width == 10.0, (
        f"Expected width 10.0, got {xs0.layer_sections[0].width}"
    )
    assert xs0.layer_sections[0].offset == 15.0, (
        f"Expected offset 15.0, got {xs0.layer_sections[0].offset}"
    )
