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
# # Parallel Generation
#
# `gdswell` is designed from the ground up for high-performance layout synthesis.
# This guide explains how to leverage your multi-core CPU to generate massive chips in seconds.
#
# ## How it Works
#
# When you call a `@cell` function, `gdswell` doesn't necessarily block your main thread.
# Instead, it:
# 1. Calculates the unique hash of the cell.
# 2. Checks the memory and disk caches.
# 3. If it's a "miss", it submits the generation task to a **Global Thread Pool**.
# 4. Returns a **FutureCell** proxy immediately.
#
# This allows the caller to continue instantiating other cells while the geometry
# is being generated in the background.
#
# ## Writing Parallel-Friendly Code
#
# To get the most out of parallelism, follow these patterns:
#
# ### 1. Exploit Independence
# If you have 1000 identical resonators, `gdswell` only builds one (cached).
# If you have 1000 **different** resonators, they can all be built in parallel.
#
# ### 2. Don't Wait Too Early
# The geometry is only finalized when you actually need it (e.g., for visualization,
# GDS export, or if you call `.wait()` on a Layout).
#
# %%
import gdswell as gw
from gdswell.components.straight import straight

# Define a PDK
xs = gw.CrossSection((gw.LayerSection("core", gw.Layer(1, 0), 0.5),))


@gw.cell
def parallel_demo() -> gw.Cell:
    c = gw.Cell()

    # This loop finishes almost instantly, because 'straight'
    # tasks are just submitted to the executor.
    for i in range(100):
        # Even if 'straight' was very slow, this loop wouldn't block.
        c.add_ref(straight(xs, length=10.0 + i))

    return c


# %% [markdown]
# ## Configuration
#
# You can control the parallel engine via environment variables or the `gw.config` object.
#
# - `GDSWELL_ASYNC_CELLS`: Set to `0` to disable background threads (useful for debugging).
# - `GDSWELL_MAX_WORKERS`: Set the maximum number of concurrent threads.
#
# %%
# Change config programmatically
gw.config.async_cells = True
gw.config.max_workers = 16

# %% [markdown]
# ## Thread Safety
#
# Every background thread works in its own isolated `Layout` context. `gdswell`
# handles the merging of these layouts into your main layout automatically when
# a cell reference is added. You don't need to worry about locking or resource
# contention in your component code.

# %% [markdown]
# ## When NOT to use Parallelism
#
# For very small designs, the overhead of thread management might exceed the
# speedup. If you find yourself debugging complex exceptions, try setting
# `gw.config.async_cells = False` to see a simplified traceback.
