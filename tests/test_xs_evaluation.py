# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from enum import Enum

import numpy as np
import pytest

import gdswell as gw
from gdswell.components.bend_circular import bend_circular
from gdswell.components.generic_path import generic_path
from gdswell.components.straight import straight


class MyLayers(gw.Layer, Enum):
    WG = (1, 0)


def test_layer_section_evaluation() -> None:
    ls = gw.LayerSection("core", MyLayers.WG, width=0.5 + 0.1 * gw.S, offset=0.2 * gw.S)
    ls_static = ls.evaluate(1.0)

    assert ls_static.width == 0.6
    assert ls_static.offset == 0.2
    assert isinstance(ls_static.width, float)
    assert isinstance(ls_static.offset, float)


def test_layer_section_vectorized() -> None:
    ls = gw.LayerSection("core", MyLayers.WG, width=0.5 + 0.1 * gw.S, offset=0.2 * gw.S)
    s_vals = np.array([0.0, 1.0, 2.0])
    ws, offsets = ls.evaluate_vectorized(s_vals)

    np.testing.assert_allclose(ws, [0.5, 0.6, 0.7])
    np.testing.assert_allclose(offsets, [0.0, 0.2, 0.4])


def test_cross_section_evaluation() -> None:
    ls1 = gw.LayerSection("core", MyLayers.WG, width=0.5 + 0.1 * gw.S)
    xs = gw.CrossSection(layer_sections=(ls1,))
    xs_static = xs.evaluate(2.0)

    ls = xs_static.layer_sections[0]
    assert ls.width == 0.7
    assert isinstance(ls.width, float)


def test_straight_port_evaluation() -> None:
    # Taper from 0.5 to 1.0
    xs = gw.CrossSection(
        layer_sections=(gw.LayerSection("core", MyLayers.WG, width=0.5 + 0.5 * gw.S),)
    )
    s = straight(cross_section=xs, length=10.0)

    ls0 = s["0"].cross_section.layer_sections[0]
    ls1 = s["1"].cross_section.layer_sections[0]
    assert ls0.width == 0.5
    assert ls1.width == 1.0
    assert isinstance(ls0.width, float)
    assert isinstance(ls1.width, float)


def test_cross_section_vectorized() -> None:
    ls1 = gw.LayerSection("core", MyLayers.WG, width=0.5 + 0.1 * gw.S)
    xs = gw.CrossSection(layer_sections=(ls1,))
    s_vals = np.array([0.0, 1.0])
    results = xs.evaluate_vectorized(s_vals)

    ls_res, ws, offsets = results[0]
    assert ws is not None
    np.testing.assert_allclose(ws, [0.5, 0.6])


def test_length_inference_circular() -> None:
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", MyLayers.WG, width=0.5),))
    radius = 10.0
    angle = 90.0
    # Circular bend x = R*sin(angle_rad*s), y = R*(1-cos(angle_rad*s))
    # speed = sqrt((R*angle_rad*cos)^2 + (R*angle_rad*sin)^2) = R*angle_rad
    # length = integrate(R*angle_rad, (s, 0, 1)) = R*angle_rad
    angle_rad = np.pi * angle / 180.0
    expected_length = radius * angle_rad

    bn = bend_circular(cross_section=xs, radius=radius, angle=angle)
    assert bn.info["length"] == pytest.approx(expected_length)
    assert bn["1"].position[0] == pytest.approx(radius * np.sin(angle_rad))
    assert bn["1"].position[1] == pytest.approx(radius * (1 - np.cos(angle_rad)))


def test_length_inference_variable_speed() -> None:
    xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", MyLayers.WG, width=0.5),))
    # x = s^2, y = 0
    # speed = 2s
    # length = 1.0 (integral of 2s from 0 to 1)
    c = generic_path(cross_section=xs, x_expr=gw.S**2, y_expr=0 * gw.S)

    assert c.info["length"] == pytest.approx(1.0)
    assert c["0"].angle == 180
    assert c["1"].angle == 0
