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
    import pyvista as pv

    from gdswell.stackup import ResolvedStackup, ResolvedStackup2D


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


def _extrude_region_uniform(
    region: "kdb_.Region",
    z_lo: float,
    z_hi: float,
    dbu: float,
) -> "list":
    """Extrude every polygon in ``region`` vertically from ``z_lo`` to ``z_hi``.

    Returns one ``pv.PolyData`` per ``kdb.Polygon`` in the region. Each
    polygon's hull is triangulated as a 2D cap at ``z_lo`` and then
    ``.extrude([0, 0, z_hi - z_lo], capping=True)`` lifts it to a 3D prism
    with both caps and side walls. Empty regions return an empty list.
    """
    import numpy as np
    import pyvista as pv

    meshes: "list[pv.PolyData]" = []
    dz = z_hi - z_lo
    for kpoly in region.each():
        hull = _kdb_polygon_hull_um(kpoly, dbu)
        if len(hull) < 3:
            continue
        points = np.array([(x, y, z_lo) for (x, y) in hull], dtype=float)
        faces = [len(hull), *range(len(hull))]
        cap = pv.PolyData(points, faces=faces).triangulate()
        meshes.append(cap.extrude([0.0, 0.0, dz], capping=True))
    return meshes


def _rotate_to_lex_min(hull: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Cyclically rotate ``hull`` so its lexicographically-minimum vertex is first.

    Gives a canonical starting index for two hulls that should pair up by
    index when lofting. Both rings rotated this way agree on which vertex is
    "first" as long as their point sets are congruent under cyclic rotation.
    """
    idx = min(range(len(hull)), key=lambda i: hull[i])
    return hull[idx:] + hull[:idx]


def _loft_region_pair(
    region_lo: "kdb_.Region",
    region_hi: "kdb_.Region",
    z_lo: float,
    z_hi: float,
    dbu: float,
    entry_name: str,
) -> "list":
    """Loft each polygon in ``region_lo`` to the matching polygon in ``region_hi``.

    Returns one closed ``pv.PolyData`` per paired polygon. Pairing is
    canonical: both regions' polygons are sorted by ``(bbox.left, bbox.bottom)``
    in dbu, and within each polygon the hull points are rotated so the
    lexicographically-minimum dbu point comes first. Topology must match
    between the two rings — same polygon count, same point count per
    polygon — otherwise ``NotImplementedError`` is raised with a message
    consistent with ``_loft_intervals`` so the user gets a coherent failure
    mode from both viewers.

    The resulting mesh has triangulated top and bottom caps and quad side
    walls; ``.triangulate()`` converts the whole thing to a triangle mesh.
    """
    import numpy as np
    import pyvista as pv

    def polys_sorted(region: "kdb_.Region") -> "list[kdb_.Polygon]":
        return sorted(region.each(), key=lambda p: (p.bbox().left, p.bbox().bottom))

    polys_lo = polys_sorted(region_lo)
    polys_hi = polys_sorted(region_hi)
    if len(polys_lo) != len(polys_hi):
        raise NotImplementedError(
            f"Polygon-count mismatch for entry {entry_name!r} between "
            f"z={z_lo} and z={z_hi}: {len(polys_lo)} polygon(s) "
            f"-> {len(polys_hi)} polygon(s). Split the entry into "
            "smaller z-ranges with stable topology, or simplify the "
            "LayerBase recipe to preserve polygon count along z."
        )

    meshes: "list[pv.PolyData]" = []
    for p_lo, p_hi in zip(polys_lo, polys_hi):
        # Use dbu-integer hull points for canonical rotation, then convert to µm.
        hull_lo_dbu = [(pt.x, pt.y) for pt in p_lo.each_point_hull()]
        hull_hi_dbu = [(pt.x, pt.y) for pt in p_hi.each_point_hull()]
        if len(hull_lo_dbu) != len(hull_hi_dbu):
            raise NotImplementedError(
                f"Point-count mismatch in polygon of entry {entry_name!r} "
                f"between z={z_lo} ({len(hull_lo_dbu)} pts) and "
                f"z={z_hi} ({len(hull_hi_dbu)} pts). Split the entry into "
                "smaller z-ranges with stable topology."
            )
        hull_lo_dbu = _rotate_to_lex_min(hull_lo_dbu)
        hull_hi_dbu = _rotate_to_lex_min(hull_hi_dbu)
        n = len(hull_lo_dbu)

        # Convert to µm; bottom ring then top ring.
        bot = np.array([(x * dbu, y * dbu, z_lo) for (x, y) in hull_lo_dbu], dtype=float)
        top = np.array([(x * dbu, y * dbu, z_hi) for (x, y) in hull_hi_dbu], dtype=float)
        points = np.vstack([bot, top])

        # VTK face format: [n_pts, p0, p1, ..., n_pts, p0, ...]
        faces: list[int] = []
        # Bottom cap (reversed so its normal points -z, away from the prism interior).
        faces.extend([n, *reversed(range(n))])
        # Top cap (forward winding, normal +z).
        faces.extend([n, *range(n, 2 * n)])
        # Side walls — one quad per edge.
        for i in range(n):
            j = (i + 1) % n
            faces.extend([4, i, j, n + j, n + i])

        meshes.append(pv.PolyData(points, faces=faces).triangulate())
    return meshes


def _regions_equal(a: "kdb_.Region", b: "kdb_.Region") -> bool:
    """True iff ``a`` and ``b`` cover the same xy area.

    ``kdb.Region.__eq__`` is identity-based (returns ``False`` for two
    shape-identical regions built separately), and there is no public
    ``hash()`` method. XOR-is-empty is the cheapest set-theoretic test.
    """
    return (a ^ b).is_empty()


def _prism_meshes(
    z_to_region: "dict[float, kdb_.Region]",
    dbu: float,
    entry_name: str,
) -> "list":
    """Dispatch a single prism's cut region dict to extrude or loft.

    Rules (matching the spec's "Mesh assembly" pass):

    - 0 z-keys (all cut away) → empty list.
    - 1 z-key (zero-thickness sheet) → empty list (3D-only concept).
    - 2 z-keys with regions that compare set-equal → uniform vertical extrude.
    - Otherwise → loft each adjacent z-pair via ``_loft_region_pair``.

    Topology changes between adjacent z-keys (different polygon or point counts)
    propagate ``NotImplementedError`` from ``_loft_region_pair`` — the caller is
    expected to split the entry into smaller z-ranges with stable topology.
    """
    z_keys = sorted(z for z, r in z_to_region.items() if not r.is_empty())
    if len(z_keys) < 2:
        return []

    if len(z_keys) == 2 and _regions_equal(z_to_region[z_keys[0]], z_to_region[z_keys[1]]):
        return _extrude_region_uniform(z_to_region[z_keys[0]], z_keys[0], z_keys[1], dbu)

    meshes: list = []
    for z_lo, z_hi in zip(z_keys, z_keys[1:]):
        meshes.extend(
            _loft_region_pair(z_to_region[z_lo], z_to_region[z_hi], z_lo, z_hi, dbu, entry_name)
        )
    return meshes


def plot_stackup_3d(
    resolved: "ResolvedStackup",
    *,
    plotter: "pv.Plotter | None" = None,
    color_map: "dict[str, object] | None" = None,
    opacity: float = 0.3,
    opacity_map: "dict[str, float] | None" = None,
    show_edges: bool = False,
    show_legend: bool = True,
    jupyter_backend: "str | None" = None,  # noqa: ARG001 — consumed by caller's .show()
) -> "pv.Plotter":
    """Render a ``ResolvedStackup`` in 3D as a configured ``pv.Plotter``.

    This is a **raw-prism** preview: each kept entry is lofted from its own
    ``z_to_region`` and added to the plotter without applying ``cut_by``
    subtractions. Overlapping prisms render as overlapping translucent solids;
    the default ``opacity=0.3`` keeps bulk media (substrate, BOX, claddings)
    see-through so features inside them stay visible, and ``opacity_map``
    is the escape hatch for making specific prisms opaque.

    Cuts are intentionally left to the downstream 3D backend (e.g. meshwell):
    robust 3D booleans require exact-arithmetic CSG that VTK does not provide,
    and the rendered preview here is meant for sanity-checking the painter's
    order, layer footprints, and z-extents — not for producing simulation
    geometry. ``keep=False`` cutters still skip rendering (their ``cut_by``
    references are honoured by the backend that consumes ``ResolvedStackup``).

    The returned plotter has depth peeling enabled (so translucent overlaps
    composite correctly), an axes triad, a white background, and a legend
    when ``show_legend=True``. The function does **not** call ``.show()``;
    the caller decides when to display. ``jupyter_backend`` is reserved
    for symmetry with the docs idiom — pass it through to ``plotter.show()``
    yourself.
    """
    import pyvista as pv

    color_map = color_map or {}
    opacity_map = opacity_map or {}
    name_to_color: dict[str, tuple[float, ...]] = {}

    if plotter is None:
        plotter = pv.Plotter()

    plotter.background_color = "white"  # ty: ignore[invalid-assignment]
    plotter.enable_depth_peeling(
        number_of_peels=8, occlusion_ratio=0.0
    )  # ty: ignore[missing-argument]
    plotter.show_axes()  # ty: ignore[missing-argument]

    legend_seen: set[str] = set()
    for prism in resolved.prisms:
        if not prism.keep:
            continue
        meshes = _prism_meshes(prism.z_to_region, resolved.dbu, prism.name)
        if not meshes:
            continue

        fc = _palette_color_for_name(prism.name, color_map, name_to_color)
        op = opacity_map.get(prism.name, opacity)
        for mesh in meshes:
            label = prism.name if prism.name not in legend_seen else None
            plotter.add_mesh(
                mesh,
                color=fc,
                opacity=op,
                show_edges=show_edges,
                name=prism.name,
                label=label,
            )
            legend_seen.add(prism.name)

    if show_legend and legend_seen:
        plotter.add_legend()  # ty: ignore[missing-argument]

    return plotter
