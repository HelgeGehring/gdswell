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
# # Stackup
#
# A `Stackup` describes how the 2D layers in your layout extend into 3D — what
# material lives at what height, how its xy footprint morphs with z, and which
# entries override which. From the same `Stackup` you can produce either of two
# outputs:
#
# - **3D**: `stack.resolve(cell)` returns a `ResolvedStackup` describing how
#   each layer polygon should be extruded and cut against the others.
# - **2D**: `stack.resolve_cutline(cell, cutline)` or
#   `stack.resolve_cross_section(cs)` returns a `ResolvedStackup2D` containing
#   the 2D polygons of the cross-sectional view.
#
# Both outputs share the same painter's-algorithm metadata: `mesh_order`,
# `keep`, and `cut_by`. This page works through both outputs on a small but
# realistic silicon-photonic stack: a rib waveguide with a TiN heater wired
# out to a metal pad.

# %%
from enum import Enum

import matplotlib.pyplot as plt

import gdswell as gw

# %% [markdown]
# ## A silicon-photonic PDK
#
# A handful of layers is enough to express a complete rib-waveguide device. The
# `DEVICE` layer plays the role of "everywhere this chiplet exists" — we draw
# it once over the whole device extent and reuse it as the xy footprint for
# every bulk medium (Si substrate, buried oxide, oxide cladding).


# %%
class Pdk(gw.Layer, Enum):
    DEVICE = (15, 0)  # device extent — substrate, BOX, cladding bodies
    WG = (1, 0)  # full-Si rib (220 nm)
    SLAB = (2, 0)  # partial-etch Si slab (70 nm) under and beside the rib
    HEATER = (10, 0)  # TiN heater above the rib
    VIA1 = (11, 0)  # via from heater pad to METAL1
    METAL1 = (12, 0)  # routing metal


# %% [markdown]
# ## Building entries
#
# A `StackupEntry` is one logical 3D body: a name plus a `z_to_layer` dict
# mapping absolute z values (µm) to `LayerBase` recipes. The convenience
# constructor `StackupEntry.uniform(name, layer, zmin, zmax)` builds a 2-key
# entry with vertical sidewalls; passing the dict directly lets you vary the
# xy recipe with z to produce slanted sidewalls or a topology that morphs
# between the keys.

# %%
# Bulk media — substrate, buried oxide, oxide claddings. All reuse the
# device-extent footprint, so the cross-section will show them filling the
# whole frame.
substrate = gw.StackupEntry.uniform("Substrate", Pdk.DEVICE, -2.0, -1.0)
box = gw.StackupEntry.uniform("BOX", Pdk.DEVICE, -1.0, 0.0)
lower_clad = gw.StackupEntry.uniform("Lower_clad", Pdk.DEVICE, 0.0, 1.5)
upper_clad = gw.StackupEntry.uniform("Upper_clad", Pdk.DEVICE, 1.6, 2.5)

# Silicon: a 70 nm slab and the 220 nm rib that sits on top of it. The rib
# uses a 50 nm-per-side slanted sidewall via a z-varying recipe.
si_slab = gw.StackupEntry.uniform("Si_slab", Pdk.SLAB, 0.0, 0.07)
si_rib = gw.StackupEntry("Si_rib", {0.0: Pdk.WG, 0.22: Pdk.WG.size(-0.05)})

# TiN heater, a via column, and a metal-1 pad.
heater = gw.StackupEntry.uniform("Heater", Pdk.HEATER, 1.5, 1.6)
via1 = gw.StackupEntry.uniform("Via1", Pdk.VIA1, 1.55, 2.5)
metal1 = gw.StackupEntry.uniform("Metal1", Pdk.METAL1, 2.5, 3.5)

# %% [markdown]
# ## Composing with `+` and `-`
#
# `Stackup` composition is strict painter's order (left-to-right). `+` appends
# an entry with `keep=True`; `-` appends it with `keep=False` — the entry's
# geometry still participates in later `cut_by` computations, but downstream
# backends will not emit it as an output volume. Use parentheses for explicit
# grouping when mixing the two.

# %%
stack = substrate + box + lower_clad + upper_clad + si_slab + si_rib + heater + via1 + metal1

# %% [markdown]
# ## Pretty-printing
#
# `print(stack)` renders the stackup as a table in painter's order. Uniform
# entries collapse to a single `zmin → zmax` row; z-varying entries get one
# row per z-key so slanted sidewalls and topology morphs stay visible (look
# at `Si_rib`).

# %%
print(stack)

# %% [markdown]
# ## Drawing the device
#
# To resolve the stackup we need a cell with polygons on each layer. The
# device is a 20 µm-long rib waveguide with a TiN heater strip running along
# it; both ends of the heater fan out to a metal-1 pad south of the
# waveguide, contacted by a small via column.

# %%
layout = gw.Layout()
cell = gw.Cell(layout=layout)

L = 20.0  # propagation length, µm
W = 8.0  # transverse half-extent, µm

# Device extent — every bulk-medium entry resolves through this polygon.
cell.add_polygon([(0.0, -W), (L, -W), (L, W), (0.0, W)], Pdk.DEVICE)

# Si rib (500 nm) and surrounding slab (6 µm).
cell.add_polygon([(0.0, -0.25), (L, -0.25), (L, 0.25), (0.0, 0.25)], Pdk.WG)
cell.add_polygon([(0.0, -3.0), (L, -3.0), (L, 3.0), (0.0, 3.0)], Pdk.SLAB)

# TiN heater: a 2 µm strip over the rib plus a 6 × 3 µm contact pad south of it.
cell.add_polygon([(0.0, -1.0), (L, -1.0), (L, 1.0), (0.0, 1.0)], Pdk.HEATER)
cell.add_polygon(
    [(L / 2 - 3, -5.5), (L / 2 + 3, -5.5), (L / 2 + 3, -2.5), (L / 2 - 3, -2.5)],
    Pdk.HEATER,
)

# Via1 (2 × 0.5 µm column) and a METAL1 pad sized like the heater pad.
cell.add_polygon(
    [(L / 2 - 1, -5.0), (L / 2 + 1, -5.0), (L / 2 + 1, -4.5), (L / 2 - 1, -4.5)],
    Pdk.VIA1,
)
cell.add_polygon(
    [(L / 2 - 3, -5.5), (L / 2 + 3, -5.5), (L / 2 + 3, -2.5), (L / 2 - 3, -2.5)],
    Pdk.METAL1,
)

# %% [markdown]
# ## Resolving in 3D
#
# `Stackup.resolve(cell)` materialises each entry's xy regions at its own
# z-keys (no resampling) and emits one `ResolvedPrism` per slot. The
# downstream 3D backend is expected to consume the output and apply cuts in
# real 3D space, so `.resolve` itself does no 2D booleans — disjoint slots
# simply omit each other from `cut_by`.

# %%
resolved = stack.resolve(cell)
print(f"{'name':<12s}  {'order':>5s}  {'keep':>4s}  cut_by")
print("─" * 50)
for p in resolved.prisms:
    print(f"{p.name:<12s}  {p.mesh_order:>5d}  {str(p.keep):>4s}  {p.cut_by}")

# %% [markdown]
# `cut_by` is a forward-only list of slot indices whose 3D bbox overlaps this
# prism's; a 3D backend subtracts those entries' raw solids to obtain each
# kept prism's final volume.

# %% [markdown]
# ## Cutting in 2D — `resolve_cutline`
#
# To get a 2D cross-section, pass a cutline (two xy points in microns)
# through the cell. The output `ResolvedStackup2D` carries per-entry
# `kdb.Region`s in the **(s, z) → (x, y)** convention: the region's x-axis
# is arclength `s` along the cutline; its y-axis is the stackup height `z`.

# %%
cutline = ((L / 2, -W + 1.0), (L / 2, W - 1.0))  # transverse cut at midspan
resolved_2d = stack.resolve_cutline(cell, cutline)

# Two views: the full stack on the left, a zoom on the silicon layers on the
# right. The 220 nm rib and 70 nm slab are honest to scale, which is why they
# vanish in the full-stack view next to micron-thick claddings.
fig, (ax_full, ax_zoom) = plt.subplots(1, 2, figsize=(12, 4.5))
gw.plot_cross_section(resolved_2d, ax=ax_full)
ax_full.set_title("Full stack — transverse cut")

gw.plot_cross_section(resolved_2d, ax=ax_zoom)
ax_zoom.set_xlim(5.5, 8.5)
ax_zoom.set_ylim(-0.1, 0.35)
ax_zoom.set_aspect("auto")  # break aspect lock so the slanted rib reads clearly
ax_zoom.set_title("Zoom on the Si rib + slab")
plt.tight_layout()
plt.show()

# %% [markdown]
# The bulk media (substrate, BOX, oxide claddings) fill the frame; on top of
# them you can see the heater strip, the heater contact pad with a via
# climbing up through the upper cladding, and the metal-1 pad capping the
# via. The zoom on the right reveals the 220 nm slanted-sidewall rib sitting
# on the 70 nm slab — both vanish in the full-stack view because they are
# honestly to scale next to micron-thick claddings.

# %% [markdown]
# ## Painter's algorithm and `cut_by`
#
# Later entries cut earlier ones where their 3D (or 2D) bboxes overlap.
# `plot_cross_section` applies these cuts by default (`apply_cuts=True`) so
# you see each prism's final, carved patch. Compare with `apply_cuts=False`,
# which renders the raw per-entry regions before any subtraction — useful
# for debugging painter's order.

# %%
fig, ax = plt.subplots(figsize=(8, 4.5))
gw.plot_cross_section(resolved_2d, ax=ax, apply_cuts=False)
ax.set_title("Same stackup, apply_cuts=False (raw per-entry regions overlap)")
plt.tight_layout()
plt.show()

# %% [markdown]
# ## The `-` operator: `keep=False` cutters
#
# `-` adds an entry as a *cutter*: it participates in `cut_by` like any other
# slot, but downstream backends don't emit it as an output volume. A typical
# use is an etch mask that removes oxide from a region without leaving an
# explicit "etched" material behind.

# %%
etch = gw.StackupEntry.uniform("Etch", Pdk.SLAB.size(0.5), 1.5, 2.5)
carved_stack = (
    substrate
    + box
    + lower_clad
    + upper_clad
    + si_slab
    + si_rib
    - etch  # cutter: removes oxide where the slab (grown by 500 nm) is drawn
)
print(carved_stack)

# %%
resolved_carved = carved_stack.resolve_cutline(cell, cutline)

fig, ax = plt.subplots(figsize=(8, 4.5))
gw.plot_cross_section(resolved_carved, ax=ax)
ax.set_title("Etched oxide opening above the slab (keep=False cutter)")
plt.tight_layout()
plt.show()

# %% [markdown]
# ## Cutting in 2D — `resolve_cross_section`
#
# For waveguide work, you usually already have a `CrossSection`. The
# convenience `Stackup.resolve_cross_section(xs, s=0.0)` evaluates the
# `CrossSection` at `s`, builds a synthetic straight whose xy layout matches
# the evaluated profile, and slices it with a perpendicular midspan cutline.
# No manual cutline needed.

# %%
xs = gw.CrossSection(
    layer_sections=(
        gw.LayerSection(name="device", layer=Pdk.DEVICE, width=16.0, offset=0.0),
        gw.LayerSection(name="slab", layer=Pdk.SLAB, width=6.0, offset=0.0),
        gw.LayerSection(name="rib", layer=Pdk.WG, width=0.5, offset=0.0),
    )
)

# A trimmed stack — just the rib-waveguide layers around the silicon.
rib_stack = substrate + box + lower_clad + si_slab + si_rib
resolved_xs = rib_stack.resolve_cross_section(xs)

fig, ax = plt.subplots(figsize=(8, 3.5))
gw.plot_cross_section(resolved_xs, ax=ax)
ax.set_xlim(6.5, 9.5)
ax.set_ylim(-0.1, 0.35)
ax.set_aspect("auto")
ax.set_title("Cross-section evaluated directly from a CrossSection (zoom on Si)")
plt.tight_layout()
plt.show()
