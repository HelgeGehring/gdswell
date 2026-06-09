# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import klayout.db as kdb_

if TYPE_CHECKING:
    from collections.abc import Mapping

    import matplotlib.axes
    import matplotlib.colors

    from gdswell.stackup import ResolvedStackup2D


def _palette_color_for_name(
    name: str,
    color_map: "Mapping[str, object]",
    name_to_color: "dict[str, tuple[float, ...]]",
) -> object:
    """Return a stable color for ``name`` using the shared tab20 allocator.

    ``color_map`` is the user-supplied override dict. ``name_to_color`` is the
    per-call cache that records first-seen order; the i-th unique name not in
    ``color_map`` gets the i-th tab20 entry. Mutates ``name_to_color`` in place
    on first sighting; never mutates it when ``color_map`` is the source. Both
    ``plot_cross_section`` and ``plot_stackup_3d`` call this so they allocate
    matching colors when neither receives an explicit ``color_map``.
    """
    if name in color_map:
        return color_map[name]
    if name not in name_to_color:
        import matplotlib.colors as mcolors
        import matplotlib.pyplot as plt

        cmap = plt.get_cmap("tab20")
        palette = tuple(tuple(c) for c in mcolors.to_rgba_array(cmap(range(cmap.N))))
        name_to_color[name] = palette[len(name_to_color) % len(palette)]
    return name_to_color[name]


@contextlib.contextmanager
def _view_context(kdb_cell: kdb_.Cell):
    """Context manager to setup and teardown a klayout LayoutView for rendering."""
    import klayout.lay as lay

    view = lay.LayoutView()
    try:
        view.set_config("background-color", "#ffffff")
        # Use a duplicate of the layout for the view to avoid the view
        # destroying the original layout when it is destroyed.
        view.show_layout(kdb_cell.layout().dup(), False)
        view.add_missing_layers()
        view.max_hier()
        view.active_cellview().set_cell_name(kdb_cell.name)
        view.zoom_fit()
        yield view
    finally:
        view.destroy()


def export_image(kdb_cell: kdb_.Cell, filename: str, width: int = 800, height: int = 600) -> None:
    """
    Export a klayout cell to a PNG image.

    Args:
        kdb_cell: The klayout.db.Cell to export.
        filename: The name of the file to save the image to (should end in .png).
        width: The width of the image in pixels.
        height: The height of the image in pixels.
    """
    with _view_context(kdb_cell) as view:
        view.save_image(filename, width, height)


def get_image_bytes(kdb_cell: kdb_.Cell, width: int = 800, height: int = 600) -> bytes:
    """
    Return the PNG image bytes for a klayout cell.

    Args:
        kdb_cell: The klayout.db.Cell to export.
        width: The width of the image in pixels.
        height: The height of the image in pixels.

    Returns:
        The PNG data bytes.
    """
    with _view_context(kdb_cell) as view:
        pixel_buffer = view.get_pixels_with_options(width, height, 1, 1, 1.0, kdb_.DBox())
        return pixel_buffer.to_png_data()


def plot_cross_section(
    resolved_2d: "ResolvedStackup2D",
    ax: "matplotlib.axes.Axes | None" = None,
    *,
    apply_cuts: bool = True,
    color_map: dict[str, str] | None = None,
) -> "matplotlib.axes.Axes":
    """Render a ``ResolvedStackup2D`` as a 2D cross-section figure.

    The figure's x-axis is arclength ``s`` along the cutline in microns;
    the y-axis is stackup height ``z`` in microns. Each kept prism is
    rendered as a filled patch in (s, z); ``keep=False`` cutters are not
    drawn directly (their geometry is subtracted from the prisms that
    reference them via ``cut_by`` when ``apply_cuts=True``).

    Args:
        resolved_2d: The 2D resolved stackup to plot.
        ax: An existing matplotlib Axes to draw on. If ``None``, creates
            a new figure+axes via ``plt.subplots()``.
        apply_cuts: If ``True`` (default), each prism's final geometry
            is computed as ``raw_region − ⋃(cut_by raw_regions)``. If
            ``False``, raw per-entry regions are plotted as-is and
            overlaps render as overlapping patches.
        color_map: Optional override mapping prism names to matplotlib
            colors. Names absent from the map fall back to a cyclic
            ``tab20`` palette indexed by first-occurrence order.

    Returns:
        The matplotlib Axes the cross-section was drawn on.
    """
    import matplotlib.patches as mpatches
    import matplotlib.path as mpath
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots()

    dbu = resolved_2d.dbu
    color_map = color_map or {}

    name_to_color: dict[str, tuple[float, ...]] = {}

    def color_for(name: str):
        return _palette_color_for_name(name, color_map, name_to_color)

    legend_seen: set[str] = set()

    for prism in resolved_2d.polygons:
        if not prism.keep:
            continue
        if apply_cuts:
            final = prism.region.dup()
            for j in prism.cut_by:
                final -= resolved_2d.polygons[j].region
        else:
            final = prism.region
        if final.is_empty():
            continue

        fc = color_for(prism.name)
        label = prism.name if prism.name not in legend_seen else None
        legend_seen.add(prism.name)

        for kpoly in final.each():
            verts: list[tuple[float, float]] = []
            codes: list[int] = []
            hull = [(p.x * dbu, p.y * dbu) for p in kpoly.each_point_hull()]
            if not hull:
                continue
            verts.extend(hull)
            verts.append(hull[0])  # close
            codes.append(int(mpath.Path.MOVETO))
            codes.extend([int(mpath.Path.LINETO)] * (len(hull) - 1))
            codes.append(int(mpath.Path.CLOSEPOLY))
            for h in range(kpoly.holes()):
                hole = [(p.x * dbu, p.y * dbu) for p in kpoly.each_point_hole(h)]
                if not hole:
                    continue
                verts.extend(hole)
                verts.append(hole[0])
                codes.append(int(mpath.Path.MOVETO))
                codes.extend([int(mpath.Path.LINETO)] * (len(hole) - 1))
                codes.append(int(mpath.Path.CLOSEPOLY))
            path = mpath.Path(verts, codes)
            patch = mpatches.PathPatch(
                path,
                facecolor=fc,
                edgecolor="black",
                linewidth=0.5,
                alpha=0.7,
                label=label,
            )
            ax.add_patch(patch)
            label = None  # only first patch carries the legend label

    ax.set_aspect("equal")
    ax.set_xlabel("s [µm]")
    ax.set_ylabel("z [µm]")
    ax.autoscale_view()
    if legend_seen:
        ax.legend(loc="best")
    return ax


# ─── 3D stackup viewer helpers ──────────────────────────────────────────────
# Everything below supports plot_stackup_3d. The helpers are kept private
# (underscore-prefixed) so they can later split into _pyvista_meshing.py
# without breaking callers.


def _kdb_polygon_hull_um(kpoly: "kdb_.Polygon", dbu: float) -> list[tuple[float, float]]:
    """Return the kdb polygon's outer hull as (x, y) tuples in µm.

    Holes are ignored — v1 of the 3D viewer does not support holes; the
    extrude/loft pipeline assumes the hull is the full footprint. Callers
    that need holes should subtract them at the 2D-region level before
    calling.
    """
    return [(p.x * dbu, p.y * dbu) for p in kpoly.each_point_hull()]
