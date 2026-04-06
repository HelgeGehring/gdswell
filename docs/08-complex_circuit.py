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
# # Complex Circuit Example
# This example demonstrates a complex recursive branching tree and various components.

# %%
from enum import Enum

import gdswell as gw
from gdswell.components.bend_circular import bend_circular
from gdswell.components.bend_s import bend_s
from gdswell.components.coupler import coupler
from gdswell.components.straight import straight
from gdswell.components.text import text

gw.clear_cache()


class Layers(gw.Layer, Enum):
    WG = (1, 0)
    SLAB = (2, 0)
    CLAD = (3, 0)


@gw.cell
def branching_tree(xs: gw.CrossSection, depth: int = 3, length: float = 150.0) -> gw.Cell:
    """A recursive branching structure."""
    c = gw.Cell()
    main = straight(xs, length=length)
    main_inst = c.add_ref(main, origin=(0, 0))

    # Add input port to the tree cell
    c.add_port(main_inst["0"])

    if depth > 0:
        # Recursive calls
        child = branching_tree(xs, depth - 1, length * 0.7)
        # S-bends to connect branches
        sb_left = bend_s(xs, width=length * 0.5, height=10.0 * depth)
        sb_right = bend_s(xs, width=length * 0.5, height=-10.0 * depth)

        # Position branches at the end of the straight section
        # Use a coupler to avoid double connection to main_inst["1"]

        ls0 = xs.layer_sections[0]
        cp = coupler(xs, length=length * 0.1, gap=ls0.width * 1.5)
        cp_inst = c.add_ref_connected(cp, port_name="w0", target_port=main_inst["1"])

        l_inst = c.add_ref_connected(sb_left, port_name="0", target_port=cp_inst["e0"])
        c.add_ref_connected(child, port_name="0", target_port=l_inst["1"])

        r_inst = c.add_ref_connected(sb_right, port_name="0", target_port=cp_inst["e1"])
        c.add_ref_connected(child, port_name="0", target_port=r_inst["1"])

    return c


@gw.cell
def complex_circuit() -> gw.Cell:
    # 1. Define Cross-Sections
    xs_rib = gw.CrossSection(
        (
            gw.LayerSection("core", Layers.WG, 0.5),
            gw.LayerSection("slab", Layers.SLAB, 3.0),
        )
    )

    xs_wide = gw.CrossSection((gw.LayerSection("core", Layers.WG, 2.0),))

    # Transition cross-section (Rib to Wide Strip)
    xs_trans = xs_rib.transition(xs_wide)

    c = gw.Cell()

    # 2. Build the circuit
    input_wg = straight(xs_rib, length=10.0)
    input_inst = c.add_ref(input_wg, origin=(0, 0))

    cp = coupler(xs_rib, length=20.0, gap=3.0)
    cp_inst = c.add_ref_connected(cp, port_name="w0", target_port=input_inst["1"])

    # Top arm: Transition + Custom S-bend
    trans_rib_wide = straight(xs_trans, length=15.0)
    trans_inst = c.add_ref_connected(trans_rib_wide, port_name="0", target_port=cp_inst["e0"])

    sbend = bend_s(trans_inst["1"].cross_section, width=40.0, height=20.0)
    sbend_inst = c.add_ref_connected(sbend, port_name="0", target_port=trans_inst["1"])

    out_top = straight(sbend_inst["1"].cross_section, length=20.0)
    c.add_ref_connected(out_top, port_name="0", target_port=sbend_inst["1"])

    # Bottom arm: Spiral Array showcase
    # We connect multiple spirals in a row, demonstrating caching
    last_port = cp_inst["e1"]

    # Add a chain of identical waveguides to further demonstrate caching
    last_port = input_inst["0"]
    for i in range(250):
        # Use a non-zero radius to ensure consistent port naming
        radius = (i % 5 + 2.0) + (i / 10)
        wg = bend_circular(cross_section=xs_rib, radius=radius, angle=90)
        wg_inst = c.add_ref_connected(wg, port_name="1", target_port=last_port)
        last_port = wg_inst["0"]

    # 3. Print some inferred lengths to console
    print(f"Custom S-bend inferred length: {sbend.info['length']:.3f} um")

    tree = branching_tree(xs_rib, depth=3, length=30.0)
    c.add_ref_connected(tree, port_name="0", target_port=last_port)

    # 4. Add Text Labels
    print("Adding text labels...")
    # Large gdswell title
    title = text("gdswell", size=200.0, layer=Layers.WG)
    c.add_ref(title, origin=(-1000, -500))

    # 2000 letters below
    # We create a long string and wrap it
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 "
    lots_of_text = (alphabet * 40)[:2000]
    wrapped_text = "\n".join([lots_of_text[i : i + 50] for i in range(0, 2000, 50)])
    body_text = text(wrapped_text, size=30.0, layer=Layers.SLAB)
    c.add_ref(body_text, origin=(-1000, -800))

    return c


# %%
top = complex_circuit()
# top = Layers.CLAD.onto(Layers.WG)(top)

# %% [markdown]
# ## Visualization
# The cell is automatically rendered here:

# %%
top.show()

# %% [markdown]
# ## Performance Statistics
#
# GDSwell tracks the efficiency of your cell generation. When you run `gw.print_stats()`,
# you see a detailed breakdown of how many times each function was called and how it was resolved:
#
# - **Calls**: Total number of times the function was requested.
# - **MemH (Memory Hit)**: The result was already in the current Python session's memory.
# - **DiskH (Disk Hit)**: The result was found in the persistent `.gdswell_cache` on disk.
# - **Comp. (Compile)**: The function actually had to be executed to generate new geometry.
# - **Build (min/avg/max)**: The time spent inside the function
#   (excluding children) during Compiles.
# - **Total Time**: The cumulative time spent generating this specific cell type across all calls.
#
# This data is invaluable for identifying bottlenecks in large layouts.

# %%
gw.print_stats()
