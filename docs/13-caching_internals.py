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
# # Caching Internals
#
# One of the most unique features of `gdswell` is its hierarchical caching system.
# This guide explains how it works, how it detects changes, and how to manage it.
#
# ## The Two-Tier Cache
#
# 1. **Memory Cache**: Extremely fast. Stores generated `Cell` objects in your current
#    Python session. Ideal for iterative script execution.
# 2. **Disk Cache**: Persistent across sessions. Stores GDS files in the `.gdswell_cache` directory.
#
# ## Transitive Source Hashing
#
# Unlike simple caches that only look at function arguments,
# `gdswell` uses **Transitive Source Hashing**.
# When a `@cell` function is called, its unique signature is computed based on:
#
# 1. **The Function Source**: The literal Python code of the function.
# 2. **Arguments**: All parameters passed to the function.
# 3. **Cell Dependencies**: Any other `@cell` functions called within this function.
# 4. **External Code**: Changes in imported library functions (if they are also decorated).
#
# ### The "Tree-Falling" Effect
# If you edit a low-level "leaf" component (like a single waveguide taper), `gdswell`
# automatically invalidates the cache for that component
# **and every parent component that uses it**.
# This ensures your final chip always reflects the current state of your code, while
# maintaining maximum reuse for parts of the design that haven't changed.
#
# ## Metadata and Debugging
#
# Every cached item on disk consists of several files:
# - `.gds`: The actual physical geometry.
# - `.json`: Metadata including the hash, creation time, and **dependency list**.
#
# If you are curious why a cell is re-executing, you can inspect the `.json` file in
# your `.gdswell_cache` directory to see what dependencies it tracked.
#
# ## Managing the Cache
#
# You can interact with the cache using these utility functions:

# %%

# Completely wipe the disk cache (forcing a full re-build of the chip)
# gw.clear_cache()

# %% [markdown]
# ## Best Practices
#
# - **Keep @cell functions small**: More granular cells mean better cache reuse.
# - **Avoid non-deterministic arguments**: If a function argument changes on every run
#   (like a timestamp or a random seed), caching will be disabled for that branch.
# - **Use Enums for Layers**: Enums provide stable hash signatures compared to raw tuples.
