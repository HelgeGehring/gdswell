# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Transitions & Generic Paths
#
# Designing complex photonic or RF circuits often requires smooth transitions between
# different waveguide widths or custom paths defined by mathematical expressions.
# `gdswell` provides a flexible API for defining these transitions and paths.

# %% [markdown]
# ## Cross-Section Transitions
#
# You can transition between any two `CrossSection` objects. This will interpolate
# the widths and offsets of all layers present in the cross-sections.
#
# The `transition` method supports:
# *   **Linear interpolation**: The default behavior.
# *   **Custom functions**: Use SymPy expressions (like `S**2` for parabolic) to define the
#     interpolation profile.

# %%
from enum import Enum

import sympy

import gdswell as gw
from gdswell.components.bend_circular import bend_circular
from gdswell.components.generic_path import generic_path
from gdswell.components.straight import straight
from gdswell.cross_section import CrossSection, LayerSection, S


class Layers(gw.Layer, Enum):
    WG = (1, 0)
    CLADDING = (2, 0)


# Define two cross-sections for the transition
xs_narrow = CrossSection(
    (
        LayerSection(name="core", layer=Layers.WG, width=0.5),
        LayerSection(name="clad", layer=Layers.CLADDING, width=3.0),
    )
)

xs_wide = CrossSection(
    (
        LayerSection(name="core", layer=Layers.WG, width=2.0),
        LayerSection(name="clad", layer=Layers.CLADDING, width=5.0),
    )
)

# %% [markdown]
# ## Linear and Parabolic Tapers
#
# Let's create a cell that demonstrates different types of tapers.


# %%
@gw.cell
def taper_demo() -> gw.Cell:
    c = gw.Cell()
    length = 10.0

    # 1. Linear Taper
    xs_linear = xs_narrow.transition(xs_wide)
    taper_lin = straight(cross_section=xs_linear, length=length)
    c.add_ref(taper_lin, origin=(0, 0))

    # 2. Parabolic Taper
    # f(s) goes from 0 to 1 as s goes from 0 to length
    xs_parabolic = xs_narrow.transition(xs_wide, f_s=S**2)
    taper_para = straight(cross_section=xs_parabolic, length=length)
    c.add_ref(taper_para, origin=(0, 10))

    return c


taper_demo()

# %% [markdown]
# ## Generic Paths (Sine Wave)
#
# You can define custom paths using SymPy expressions for $x(s)$ and $y(s)$, where $s$ is the
# parameter that represents the path progress from 0 to 1.


# %%
@gw.cell
def sine_demo() -> gw.Cell:
    c = gw.Cell()

    # x(s) and y(s) as functions of S (from 0 to 1)
    x_expr = 20 * S
    y_expr = 2 * sympy.sin(2 * sympy.pi * S)

    sine_wg = generic_path(cross_section=xs_narrow, x_expr=x_expr, y_expr=y_expr, npoints=200)
    c.add_ref(sine_wg)
    return c


sine_demo()

# %% [markdown]
# ## Tapered Bends
#
# Transitions can also be applied to curved components like bends.


# %%
@gw.cell
def tapered_bend_demo() -> gw.Cell:
    c = gw.Cell()

    xs_bend = xs_narrow.transition(xs_wide)
    t_bend = bend_circular(cross_section=xs_bend, radius=10.0, angle=90.0)

    # The bend's ports will also have transposed cross-sections
    # Connect a wide straight to the outputs
    s_end = straight(cross_section=xs_wide, length=5.0)

    inst_bend = c.add_ref(t_bend)
    c.add_ref_connected(s_end, port_name="0", target_port=inst_bend["1"])

    return c


tapered_bend_demo()
