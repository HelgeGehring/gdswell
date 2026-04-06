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
# # Hierarchical Netlist Extraction
#
# This example demonstrates how `extract_netlist` handles multi-layered cell hierarchies.
# GDSwell performs **single-level extraction**, meaning it identifies connections between
# the immediate children of the cell you are analyzing.
#
# ## Mixed Hierarchy with Alternating Bends
#
# In this example, we build a mixed hierarchy where composite cells (Straights + Bends)
# are connected via top-level leaf components:
# 1. **Straight**: A simple straight waveguide component.
# 2. **Bend**: A circular bend component.
# 3. **Composite Cell**: Composed of a straight and a bend.
# 4. **Top Cell**: Composed of two Composite cells connected via a bridging Straight.

# %%
import gdswell as gw
from gdswell.components.bend_circular import bend_circular
from gdswell.components.straight import straight
from gdswell.netlist import extract_netlist

# %% [markdown]
# ## 1. Define the PDK Cross-Section
# A basic cross-section (e.g., 500nm wide SOI waveguide) used for all components.

# %%
xs = gw.CrossSection(layer_sections=(gw.LayerSection("core", gw.Layer(1, 0), width=0.5),))


# %% [markdown]
# ## 2. Define a Composite cell
# Composed of a straight and a bend.


# %%
@gw.cell
def composite_cell() -> gw.Cell:
    """A composite cell with a straight and a bend."""
    c = gw.Cell()
    s = c.add_ref(straight(xs, length=10.0))
    b = c.add_ref_connected(bend_circular(xs, radius=10.0, angle=90.0), "0", s["1"])

    # Expose outer ports
    c.add_port(s["0"].renamed("in"))
    c.add_port(b["1"].renamed("out"))
    return c


# %% [markdown]
# ## 3. Define the Top cell
# Composed of two composite cells and one leaf straight connected in a chain.


# %%
@gw.cell
def top_cell() -> gw.Cell:
    """A top cell with alternating composite and leaf components."""
    c = gw.Cell()
    c1 = c.add_ref(composite_cell())
    # Connect a leaf straight directly at the top level
    l1 = c.add_ref_connected(straight(xs, length=5.0), "0", c1["out"])
    # Connect another composite cell
    c2 = c.add_ref_connected(composite_cell(), "in", l1["1"])

    # Expose top-level ports
    c.add_port(c1["in"].renamed("TOP_IN"))
    c.add_port(c2["out"].renamed("TOP_OUT"))
    return c


# %% [markdown]
# ## 4. Netlist Extraction
# Extracting the netlist of the **Top Cell** shows connections between its immediate children:
# the two composite cells and the bridging leaf straight.

# %%
# Extract netlists at different levels of the hierarchy
print("=== Extracting Composite Cell Netlist ===")
comp = composite_cell()
print(extract_netlist(comp))

print("\n" + "=" * 40 + "\n")

print("=== Extracting Top Cell Netlist ===\n")
top = top_cell()
print(extract_netlist(top))

# Show the top cell interactively in the documentation
top
