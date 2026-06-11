# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

import klayout.db as kdb

from gdswell.layer import LayerBase

if TYPE_CHECKING:
    import gdswell as gw
    from gdswell.cross_section import CrossSection


@dataclass(frozen=True, eq=False)
class StackupEntry:
    """One logical 3D body: a named cross-section that varies with z.

    ``z_to_layer`` maps absolute z values to ``LayerBase`` recipes. The 3D
    backend (e.g. meshwell) is responsible for interpolating between adjacent
    z-keys when it lofts the prism — typically a linear morph producing
    slanted sidewalls. A single-key entry is a zero-thickness sheet — useful
    as a boundary tag or as a cut surface.
    """

    name: str
    z_to_layer: dict[float, LayerBase] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.z_to_layer) < 1:
            raise ValueError("StackupEntry.z_to_layer must have at least one key")

    @classmethod
    def uniform(cls, name: str, layer: LayerBase, zmin: float, zmax: float) -> StackupEntry:
        """Convenience: 2-key entry with the same layer at zmin and zmax."""
        return cls(name=name, z_to_layer={zmin: layer, zmax: layer})

    # --- algebra -------------------------------------------------------------

    def __add__(self, other: StackupEntry | Stackup) -> Stackup:
        rhs = Stackup._coerce_items(other, keep=True)
        return Stackup(items=(StackupItem(self, True),) + rhs)

    def __sub__(self, other: StackupEntry | Stackup) -> Stackup:
        rhs = Stackup._coerce_items(other, keep=False)
        return Stackup(items=(StackupItem(self, True),) + rhs)

    # --- layer-recipe operations --------------------------------------------

    def map_layers(self, fn: Callable[[LayerBase], LayerBase]) -> StackupEntry:
        """Return a new entry with ``fn`` applied to every layer recipe."""
        return replace(
            self,
            z_to_layer={z: fn(L) for z, L in self.z_to_layer.items()},
        )

    def size(self, dx: float, dy: float | None = None) -> StackupEntry:
        return self.map_layers(lambda L: L.size(dx, dy))

    def transformed(self, t: kdb.Trans | kdb.DTrans) -> StackupEntry:
        return self.map_layers(lambda L: L.transformed(t))

    def round_corners(self, r1: float, r2: float, segments: int) -> StackupEntry:
        return self.map_layers(lambda L: L.round_corners(r1, r2, segments))

    def bbox(self) -> StackupEntry:
        return self.map_layers(lambda L: L.bbox())

    def interacting(self, other: LayerBase, *, invert: bool = False) -> StackupEntry:
        if invert:
            return self.map_layers(lambda L: L.not_interacting(other))
        return self.map_layers(lambda L: L.interacting(other))

    def inside(self, other: LayerBase) -> StackupEntry:
        return self.map_layers(lambda L: L.inside(other))

    def outside(self, other: LayerBase) -> StackupEntry:
        return self.map_layers(lambda L: L.outside(other))

    def overlapping(self, other: LayerBase, min_count: int = 1) -> StackupEntry:
        return self.map_layers(lambda L: L.overlapping(other, min_count))

    # --- equality / hashing ---------------------------------------------------

    def _sorted_items(self) -> tuple[tuple[float, LayerBase], ...]:
        return tuple(sorted(self.z_to_layer.items(), key=lambda kv: kv[0]))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StackupEntry):
            return False
        return self.name == other.name and self._sorted_items() == other._sorted_items()

    def __hash__(self) -> int:
        return hash(
            (
                self.name,
                tuple((z, L._hash_string) for z, L in self._sorted_items()),
            )
        )

    @property
    def _hash_string(self) -> str:
        body = ",".join(f"{z}:{L._hash_string}" for z, L in self._sorted_items())
        return f"Entry({self.name},{body})"

    def __repr__(self) -> str:
        body = ", ".join(f"{z}: {L!r}" for z, L in self._sorted_items())
        return f"StackupEntry({self.name!r}, {{{body}}})"


@dataclass(frozen=True)
class StackupItem:
    """One slot in a Stackup: an entry plus a ``keep`` flag.

    ``keep`` is carried through to the resolved output verbatim: every slot
    becomes one ``ResolvedPrism`` (1:1 indexing). Downstream 3D backends use
    the flag to decide whether a prism contributes an output volume or is
    only a cutter referenced by other prisms' ``cut_by``.
    """

    entry: StackupEntry
    keep: bool


@dataclass(frozen=True, eq=False)
class Stackup:
    """An ordered list of (entry, keep) items composed by + / -.

    Composition is strict left-to-right (painter's algorithm). Use parentheses
    for explicit grouping.
    """

    items: tuple[StackupItem, ...] = ()

    @classmethod
    def of(cls, *entries: StackupEntry) -> Stackup:
        return cls(items=tuple(StackupItem(e, True) for e in entries))

    # --- coercion helpers ----------------------------------------------------

    @staticmethod
    def _coerce_items(other: StackupEntry | Stackup, *, keep: bool) -> tuple[StackupItem, ...]:
        if isinstance(other, StackupEntry):
            return (StackupItem(other, keep),)
        if isinstance(other, Stackup):
            if keep:
                return other.items
            return tuple(StackupItem(it.entry, False) for it in other.items)
        raise TypeError(
            f"Stackup composition expects a StackupEntry or Stackup, got {type(other).__name__}"
        )

    # --- algebra -------------------------------------------------------------

    def __add__(self, other: StackupEntry | Stackup) -> Stackup:
        rhs = Stackup._coerce_items(other, keep=True)
        return Stackup(items=self.items + rhs)

    def __sub__(self, other: StackupEntry | Stackup) -> Stackup:
        rhs = Stackup._coerce_items(other, keep=False)
        return Stackup(items=self.items + rhs)

    def __radd__(self, other: StackupEntry) -> Stackup:
        if isinstance(other, StackupEntry):
            return Stackup(items=(StackupItem(other, True),) + self.items)
        return NotImplemented

    def __rsub__(self, other: StackupEntry) -> Stackup:
        if isinstance(other, StackupEntry):
            return Stackup(
                items=(StackupItem(other, True),)
                + tuple(StackupItem(it.entry, False) for it in self.items)
            )
        return NotImplemented

    # --- layer-recipe operations --------------------------------------------

    def map_layers(self, fn: Callable[[LayerBase], LayerBase]) -> Stackup:
        return Stackup(
            items=tuple(StackupItem(it.entry.map_layers(fn), it.keep) for it in self.items)
        )

    def size(self, dx: float, dy: float | None = None) -> Stackup:
        return self.map_layers(lambda L: L.size(dx, dy))

    def transformed(self, t: kdb.Trans | kdb.DTrans) -> Stackup:
        return self.map_layers(lambda L: L.transformed(t))

    def round_corners(self, r1: float, r2: float, segments: int) -> Stackup:
        return self.map_layers(lambda L: L.round_corners(r1, r2, segments))

    def bbox(self) -> Stackup:
        return self.map_layers(lambda L: L.bbox())

    def interacting(self, other: LayerBase, *, invert: bool = False) -> Stackup:
        return Stackup(
            items=tuple(
                StackupItem(it.entry.interacting(other, invert=invert), it.keep)
                for it in self.items
            )
        )

    def inside(self, other: LayerBase) -> Stackup:
        return self.map_layers(lambda L: L.inside(other))

    def outside(self, other: LayerBase) -> Stackup:
        return self.map_layers(lambda L: L.outside(other))

    def overlapping(self, other: LayerBase, min_count: int = 1) -> Stackup:
        return self.map_layers(lambda L: L.overlapping(other, min_count))

    # --- equality / hashing --------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Stackup):
            return False
        return self.items == other.items

    def __hash__(self) -> int:
        return hash(tuple((it.entry, it.keep) for it in self.items))

    @property
    def _hash_string(self) -> str:
        body = ",".join(f"{'+' if it.keep else '-'}{it.entry._hash_string}" for it in self.items)
        return f"Stackup({body})"

    def __repr__(self) -> str:
        body = ", ".join(f"{'+' if it.keep else '-'}{it.entry!r}" for it in self.items)
        return f"Stackup([{body}])"

    def __str__(self) -> str:
        """Render the stackup as a human-readable table in painter's order.

        Columns: index, keep flag, entry name, z (µm), layer recipe. Entries
        with two equal-recipe z-keys collapse to a ``zmin → zmax`` row; entries
        with three or more keys (or differing recipes per key) get one row per
        key, so slanted-sidewall morphs stay visible at a glance.
        """
        if not self.items:
            return "Stackup: (empty)"

        cols = ("#", "keep", "name", "z (µm)", "layer")
        rows: list[list[str]] = []
        for i, it in enumerate(self.items):
            zs = sorted(it.entry.z_to_layer)
            keep_mark = "+" if it.keep else "−"
            uniform = (
                len(zs) == 2
                and it.entry.z_to_layer[zs[0]]._hash_string
                == it.entry.z_to_layer[zs[1]]._hash_string
            )
            if uniform:
                rows.append(
                    [
                        str(i),
                        keep_mark,
                        it.entry.name,
                        f"{zs[0]:>7.3f} → {zs[-1]:.3f}",
                        _short_layer_label(it.entry.z_to_layer[zs[0]]),
                    ]
                )
            else:
                for j, z in enumerate(zs):
                    rows.append(
                        [
                            str(i) if j == 0 else "",
                            keep_mark if j == 0 else "",
                            it.entry.name if j == 0 else "",
                            f"{z:>7.3f}",
                            _short_layer_label(it.entry.z_to_layer[z]),
                        ]
                    )

        widths = [max(len(cols[k]), *(len(r[k]) for r in rows)) for k in range(len(cols))]
        sep = "─" * (sum(widths) + 2 * (len(cols) - 1))

        def fmt(row: list[str] | tuple[str, ...]) -> str:
            return "  ".join(c.ljust(w) for c, w in zip(row, widths))

        n = len(self.items)
        header_line = f"Stackup: {n} {'entry' if n == 1 else 'entries'} (painter's order)"
        return "\n".join((header_line, sep, fmt(cols), sep, *(fmt(r) for r in rows), sep))

    def resolve(self, cell: "gw.Cell") -> ResolvedStackup:
        """Materialize each entry's xy regions at its own z-keys (no resampling).
        Populate ``cut_by`` via O(N²) 3D-bbox overlap (z-range gate then xy-bbox
        intersection). The 3D backend performs the actual cuts.
        """
        # 1. Materialize raw per-z regions for every entry slot.
        raw: list[dict[float, kdb.Region]] = [
            {z: L.get_shapes(cell) for z, L in it.entry.z_to_layer.items()} for it in self.items
        ]

        # 2. Per-entry 3D bbox cache (None if entry has no geometry anywhere).
        bboxes: list[tuple[float, float, kdb.Box] | None] = [_entry_3d_bbox(r) for r in raw]

        # 3. For each slot i, find all later slots j whose 3D bbox overlaps i's.
        n = len(self.items)
        cut_by: list[tuple[int, ...]] = []
        for i in range(n):
            bi = bboxes[i]
            if bi is None:
                cut_by.append(())
                continue
            edges = tuple(
                j
                for j in range(i + 1, n)
                if (bj := bboxes[j]) is not None and _bbox3d_overlaps(bi, bj)
            )
            cut_by.append(edges)

        # 4. Emit one ResolvedPrism per slot.
        prisms = tuple(
            ResolvedPrism(
                name=it.entry.name,
                z_to_region=raw[i],
                mesh_order=i,
                keep=it.keep,
                cut_by=cut_by[i],
            )
            for i, it in enumerate(self.items)
        )
        return ResolvedStackup(prisms=prisms, dbu=cell.layout.kdb.dbu)

    def resolve_cutline(
        self,
        cell: "gw.Cell",
        cutline: tuple[tuple[float, float], tuple[float, float]],
    ) -> ResolvedStackup2D:
        """Materialise each entry's 2D polygons in the cutline plane.

        ``cutline`` is two ``(x, y)`` points in microns: start and end of a
        single line segment. The output ``ResolvedStackup2D`` mirrors the
        3D ``ResolvedStackup`` shape: same 1:1 slot indexing, same
        ``mesh_order`` / ``keep`` / ``cut_by`` semantics. ``cut_by`` is
        built from 2D bbox overlap in the cutline plane.

        Output regions use the (s, z) -> (x, y) convention; dbu is
        inherited from ``cell.layout.kdb.dbu``.
        """
        dbu = cell.layout.kdb.dbu
        (x0, y0), (x1, y1) = cutline
        cutline_edge = kdb.Edge(
            kdb.Point(int(round(x0 / dbu)), int(round(y0 / dbu))),
            kdb.Point(int(round(x1 / dbu)), int(round(y1 / dbu))),
        )

        # Per-entry, per-z-key cutline intervals (in dbu along the cutline).
        per_entry_intervals: list[dict[float, tuple[tuple[int, int], ...]]] = []
        for it in self.items:
            z_to_iv: dict[float, tuple[tuple[int, int], ...]] = {}
            for z, layer_recipe in it.entry.z_to_layer.items():
                xy_region = layer_recipe.get_shapes(cell)
                z_to_iv[z] = _cutline_intervals(xy_region, cutline_edge)
            per_entry_intervals.append(z_to_iv)

        # Loft each entry's intervals into a 2D region in (s, z).
        regions_2d: list[kdb.Region] = [
            _loft_intervals(z_to_iv, dbu, name=it.entry.name)
            for it, z_to_iv in zip(self.items, per_entry_intervals)
        ]

        # cut_by from 2D bbox overlap in the cutline plane.
        n = len(self.items)
        bboxes: list[kdb.Box | None] = [None if r.is_empty() else r.bbox() for r in regions_2d]
        cut_by: list[tuple[int, ...]] = []
        for i in range(n):
            bi = bboxes[i]
            if bi is None:
                cut_by.append(())
                continue
            edges = tuple(
                j
                for j in range(i + 1, n)
                if (bj := bboxes[j]) is not None and not (bi & bj).empty()
            )
            cut_by.append(edges)

        polygons = tuple(
            ResolvedPolygon2D(
                name=it.entry.name,
                region=regions_2d[i],
                mesh_order=i,
                keep=it.keep,
                cut_by=cut_by[i],
            )
            for i, it in enumerate(self.items)
        )
        return ResolvedStackup2D(polygons=polygons, dbu=dbu)

    def resolve_cross_section(
        self,
        cross_section: "CrossSection",
        s: float = 0.0,
    ) -> ResolvedStackup2D:
        """Resolve the stackup against a CrossSection evaluated at ``s``.

        Builds a 1 µm synthetic straight whose xy layout matches the
        evaluated CrossSection's LayerSection rectangles, then calls
        ``resolve_cutline`` with a midspan perpendicular cutline. Topology
        mismatch is impossible on this path: every layer becomes a
        constant-width rectangle along the straight, so the cutline
        crosses each layer's region exactly once at every z-key.

        ``CrossSection.cell_sections`` are dropped with a ``UserWarning``
        that points the user at the workaround: build a real ``Cell``
        that places the cells along an actual path, then call
        ``resolve_cutline`` on it with a cutline of your choice.
        """
        import warnings

        xs_static = cross_section.evaluate(s)
        if xs_static.cell_sections:
            names = ", ".join(repr(cs.name) for cs in xs_static.cell_sections)
            warnings.warn(
                f"CrossSection contains CellSection(s) {{{names}}}; these "
                "are not representable in resolve_cross_section because "
                "their xy extent depends on a path. To include them, "
                "build a Cell that places the cells along your path and "
                "call Stackup.resolve_cutline(cell, cutline) directly, "
                "choosing the cutline xy-line yourself.",
                UserWarning,
                stacklevel=2,
            )
        cell, cutline = _build_synthetic_straight(xs_static)
        return self.resolve_cutline(cell, cutline)


def _short_layer_label(layer: LayerBase) -> str:
    """Compact label for a ``LayerBase`` suitable for table output.

    ``str(layer)`` is already nice for ``Layer`` enum members (e.g. ``Pdk.WG``)
    but falls back to the dataclass ``__repr__`` for derived recipes, which
    embeds the verbose ``<Pdk.WG: Layer(1, 0)>`` form of each child layer.
    This collapses those enum-member reprs back to their dotted name so a
    nested recipe like ``LayerSize(layer=Pdk.WG, dx=-0.05, dy=None)`` stays
    readable.
    """
    import re

    return re.sub(r"<(\w+(?:\.\w+)+): Layer\(\d+, \d+\)>", r"\1", str(layer))


def _entry_3d_bbox(
    z_to_region: dict[float, kdb.Region],
) -> tuple[float, float, kdb.Box] | None:
    """Return ``(zmin, zmax, xy_bbox)`` for the entry, or ``None`` if it has
    no geometry at any z (every region is empty).

    The xy bbox is the union of per-z region bboxes, expressed as a
    ``kdb.Box`` in dbu. Single-z entries have zmin == zmax. The union
    covers the entry's full extruded footprint, so a downstream backend
    that lofts between z-keys can be bounded by it.
    """
    if not z_to_region:
        return None
    xy = kdb.Box()  # empty
    for r in z_to_region.values():
        if not r.is_empty():
            xy += r.bbox()
    if xy.empty():
        return None
    return min(z_to_region), max(z_to_region), xy


def _bbox3d_overlaps(a: tuple[float, float, kdb.Box], b: tuple[float, float, kdb.Box]) -> bool:
    """True iff the two 3D bboxes overlap. z-range gate then xy-bbox test.

    The z-gate uses strict ``<``, so entries that meet at a single z-plane
    (one ends where the other begins) are treated as overlapping. This is
    conservative on purpose: a 3D backend may loft an entry's footprint
    just past its declared z-keys (curve tolerance, arc fits), so we
    cannot rule the touching case out at bbox level. The cost of a false
    overlap is a no-op cut in the backend; the cost of a missed overlap
    would be silently wrong geometry.
    """
    az0, az1, axy = a
    bz0, bz1, bxy = b
    if az1 < bz0 or bz1 < az0:
        return False
    return not (axy & bxy).empty()


@dataclass(frozen=True)
class ResolvedPrism:
    """The output of ``Stackup.resolve(cell)``: one frozen recipe per source entry.

    ``z_to_region`` maps z values to ``kdb.Region``s at the entry's own z-keys
    (no resampling). ``mesh_order`` equals the entry's position in the source
    ``Stackup``. ``keep`` mirrors ``StackupItem.keep`` — ``False`` prisms are
    cutters retained in the output so ``cut_by`` indices can reference them,
    but downstream backends do not emit them as output volumes. ``cut_by`` is
    a tuple of indices ``j > self.mesh_order`` whose 3D bbox overlaps this
    prism's; downstream backends subtract those prisms' raw solids to obtain
    the final volume.
    """

    name: str
    z_to_region: dict[float, kdb.Region]
    mesh_order: int
    keep: bool = True
    cut_by: tuple[int, ...] = ()


@dataclass(frozen=True)
class ResolvedStackup:
    """Output of ``Stackup.resolve(cell)``: a tuple of prisms indexed 1:1 with
    the source ``Stackup.items``.

    Both ``keep=True`` and ``keep=False`` prisms appear in ``prisms``. The
    1:1 indexing invariant lets ``ResolvedPrism.cut_by`` use compact integer
    indices and matches the painter's-order semantics already encoded in the
    input ``Stackup``.

    ``dbu`` is the database unit (µm per integer dbu) inherited from the
    source ``Cell.layout.kdb.dbu``. All ``kdb.Region`` polygons in this
    container's ``ResolvedPrism.z_to_region`` use this dbu; consumers
    that convert to µm should multiply integer dbu coordinates by it.
    """

    prisms: tuple[ResolvedPrism, ...] = ()
    dbu: float = 0.001


@dataclass(frozen=True)
class ResolvedPolygon2D:
    """One frozen 2D recipe per source entry, lofted onto the cutline plane.

    ``region`` is a ``kdb.Region`` in dbu with the **(s, z) -> (x, y)
    convention**: x = arclength ``s`` along the cutline; y = stackup
    height ``z``. The coordinate system is NOT the layout's xy plane;
    consumers must respect this or they will misread the data. dbu is
    inherited from the source ``Cell.layout.kdb.dbu``.

    The metadata fields (``name``, ``mesh_order``, ``keep``, ``cut_by``)
    carry the same semantics as ``ResolvedPrism``: 1:1 indexing with
    ``Stackup.items``, forward-only painter's ``cut_by``, ``keep=False``
    slots retained so other prisms' ``cut_by`` can reference them.
    """

    name: str
    region: kdb.Region
    mesh_order: int
    keep: bool = True
    cut_by: tuple[int, ...] = ()


@dataclass(frozen=True)
class ResolvedStackup2D:
    """Output of ``Stackup.resolve_cutline`` and ``Stackup.resolve_cross_section``:
    a tuple of 2D polygons indexed 1:1 with the source ``Stackup.items``.

    Same invariants as ``ResolvedStackup``: both ``keep=True`` and
    ``keep=False`` slots appear; index ``i`` in ``polygons`` matches slot
    ``i`` in ``Stackup.items``; ``cut_by`` indices reference this tuple.

    ``dbu`` is the database unit (µm per integer dbu) inherited from the
    source ``Cell.layout.kdb.dbu``. Convert dbu integer coordinates in
    each ``ResolvedPolygon2D.region`` to µm by multiplying by ``dbu``.
    """

    polygons: tuple[ResolvedPolygon2D, ...] = ()
    dbu: float = 0.001


def _build_synthetic_straight(
    xs_static: "CrossSection",
) -> "tuple[gw.Cell, tuple[tuple[float, float], tuple[float, float]]]":
    """Construct a 1 µm-long synthetic straight from an already-evaluated
    CrossSection and return ``(cell, cutline)`` where the cutline is
    perpendicular to the straight at its midspan.

    Each ``LayerSection`` produces one rectangle on its layer covering
    ``x ∈ [0, L]`` and ``y ∈ [offset - width/2, offset + width/2]``.
    ``CellSection``s are ignored on this path (the caller is responsible
    for warning); they are path-dependent placements and cannot be
    represented as a transverse profile at a single ``s``.

    The cutline is vertical at ``x = L/2``, spanning ``y`` from the
    union of all LayerSection y-extents padded by 1 µm on each side.
    """
    import gdswell as gw

    layout = gw.Layout(name="_synthetic_xs", set_as_default=False)
    cell = gw.Cell(layout=layout)
    L = 1.0  # length in µm; any positive value works.

    y_min, y_max = float("inf"), float("-inf")
    for ls in xs_static.layer_sections:
        w = float(ls.width)
        o = float(ls.offset)
        y_lo, y_hi = o - w / 2.0, o + w / 2.0
        if y_hi <= y_lo:
            continue  # zero-width section → no polygon.
        cell.add_polygon([(0.0, y_lo), (L, y_lo), (L, y_hi), (0.0, y_hi)], ls.layer)
        y_min = min(y_min, y_lo)
        y_max = max(y_max, y_hi)

    margin = 1.0
    if y_min == float("inf"):
        # No layer sections produced any geometry; pick a degenerate range
        # so the cutline is still well-defined.
        y_min, y_max = -margin, margin
    cutline = ((L / 2.0, y_min - margin), (L / 2.0, y_max + margin))
    return cell, cutline


def _cutline_intervals(region: kdb.Region, cutline: kdb.Edge) -> tuple[tuple[int, int], ...]:
    """Slice ``region`` with ``cutline`` and return sorted dbu intervals.

    Uses ``kdb.Edges([cutline]) & region`` to get the segments of the
    cutline that lie inside the region. Each resulting edge is projected
    onto the cutline to produce an ``(s_start, s_end)`` pair in dbu,
    with ``s_start <= s_end``. The full list is sorted by ``s_start``.

    klayout does not guarantee the order of edges returned by the
    Edges-Region intersection, so the sort here is mandatory for
    downstream pairing in ``_loft_intervals``.
    """
    if region.is_empty():
        return ()
    inside_edges = kdb.Edges([cutline]) & region
    if inside_edges.is_empty():
        return ()

    p0, p1 = cutline.p1, cutline.p2
    vx, vy = p1.x - p0.x, p1.y - p0.y
    len_sq = vx * vx + vy * vy  # int; 0 only for a degenerate cutline
    if len_sq == 0:
        return ()
    import math

    inv_len = 1.0 / math.sqrt(len_sq)

    def s_dbu(p: kdb.Point) -> int:
        # Signed projection of (p - p0) onto (p1 - p0), normalised to arclength.
        signed_dot = (p.x - p0.x) * vx + (p.y - p0.y) * vy
        return int(round(signed_dot * inv_len))

    pairs: list[tuple[int, int]] = []
    for e in inside_edges.each():
        a, b = s_dbu(e.p1), s_dbu(e.p2)
        if a > b:
            a, b = b, a
        pairs.append((a, b))
    pairs.sort(key=lambda iv: iv[0])
    return tuple(pairs)


def _loft_intervals(
    z_to_intervals: dict[float, tuple[tuple[int, int], ...]],
    dbu: float,
    name: str,
) -> kdb.Region:
    """Loft sorted dbu intervals at adjacent z-keys into 2D polygons in the
    cutline plane.

    For each adjacent pair of z-keys ``(z_lo, z_hi)``:
        - Intervals at the two z-keys must already be sorted by ``s_start``
          (the caller is responsible — ``_cutline_intervals`` does this).
        - Empty interval sets at either end of the pair produce no polygon.
        - Equal non-zero counts produce one trapezoid per index-wise pair.
        - Non-equal non-zero counts raise ``NotImplementedError`` with a
          message that names the entry and z-values, so the user can split
          the entry into smaller z-ranges with stable topology.

    Single-z-key entries (zero-thickness sheets) produce an empty region:
    sheet semantics are a 3D-only concept per the spec.

    The output ``kdb.Region`` is in dbu with the (s, z) -> (x, y)
    convention. z values are converted to dbu via ``int(round(z / dbu))``.
    """
    zs = sorted(z_to_intervals)
    if len(zs) < 2:
        return kdb.Region()

    region = kdb.Region()
    for z_lo, z_hi in zip(zs, zs[1:]):
        intervals_lo = z_to_intervals[z_lo]
        intervals_hi = z_to_intervals[z_hi]
        if not intervals_lo or not intervals_hi:
            continue
        if len(intervals_lo) != len(intervals_hi):
            raise NotImplementedError(
                f"Interval-count mismatch for entry {name!r} between "
                f"z={z_lo} and z={z_hi}: {len(intervals_lo)} intervals "
                f"-> {len(intervals_hi)} intervals. Split the entry into "
                "smaller z-ranges with stable topology, or simplify the "
                "LayerBase recipe to preserve polygon count along z."
            )
        y_lo = int(round(z_lo / dbu))
        y_hi = int(round(z_hi / dbu))
        for (s0_a, s0_b), (s1_a, s1_b) in zip(intervals_lo, intervals_hi):
            poly = kdb.Polygon(
                [
                    kdb.Point(s0_a, y_lo),
                    kdb.Point(s0_b, y_lo),
                    kdb.Point(s1_b, y_hi),
                    kdb.Point(s1_a, y_hi),
                ]
            )
            region.insert(poly)
    return region
