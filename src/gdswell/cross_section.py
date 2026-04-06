# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, Callable, Union, cast

if TYPE_CHECKING:
    from gdswell.cell import Cell
    from gdswell.layout import Layout

import numpy as np
import sympy

from gdswell.layer import Layer

S = sympy.Symbol("s")


@dataclass(frozen=True)
class LayerSection:
    """
    A section of a cross-section on a specific layer.

    Attributes:
        name: Name of the section.
        layer: Layer object.
        width: Width of the section. Can be a float or a sympy expression of 's'.
        offset: Offset from the center. Can be a float or a sympy expression of 's'.
    """

    name: str
    layer: Layer
    width: float | sympy.Expr
    offset: float | sympy.Expr = 0.0

    @cached_property
    def _fw(self) -> Callable[[np.ndarray], np.ndarray]:
        if isinstance(self.width, (int, float)):
            return lambda s: np.full_like(s, float(self.width), dtype=float)
        return cast(Callable[[np.ndarray], np.ndarray], sympy.lambdify(S, self.width, "numpy"))

    @cached_property
    def _fo(self) -> Callable[[np.ndarray], np.ndarray]:
        if isinstance(self.offset, (int, float)):
            return lambda s: np.full_like(s, float(self.offset), dtype=float)
        return cast(Callable[[np.ndarray], np.ndarray], sympy.lambdify(S, self.offset, "numpy"))

    @cached_property
    def _hash_string(self) -> str:
        """Cached deterministic string for hashing."""
        w_str = str(self.width) if isinstance(self.width, sympy.Expr) else f"{self.width:.10g}"
        o_str = str(self.offset) if isinstance(self.offset, sympy.Expr) else f"{self.offset:.10g}"
        return f"LS({self.name},{self.layer.layer},{self.layer.datatype},{w_str},{o_str})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, LayerSection):
            return False
        if self.name != other.name or self.layer != other.layer:
            return False

        # Fast comparison for numbers to handle floating point precision
        def close(a: Any, b: Any) -> bool:
            if type(a) in (float, int) and type(b) in (float, int):
                return abs(float(a) - float(b)) < 1e-12
            return a == b

        return close(self.width, other.width) and close(self.offset, other.offset)

    def evaluate(self, s_val: float) -> LayerSection:
        """Evaluate width and offset at a given position s and return a static LayerSection."""
        w, o = self.evaluate_vectorized(np.array([float(s_val)]))
        return LayerSection(name=self.name, layer=self.layer, width=float(w[0]), offset=float(o[0]))

    def evaluate_vectorized(self, s_vals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Evaluate width and offset at multiple positions s."""
        w = self._fw(s_vals)
        o = self._fo(s_vals)

        if np.isscalar(w):
            w = np.full_like(s_vals, float(cast(Any, w)), dtype=float)
        if np.isscalar(o):
            o = np.full_like(s_vals, float(cast(Any, o)), dtype=float)

        return w, o

    def to_dict(self) -> dict[str, Any]:
        """Returns a JSON-serializable dictionary representation."""
        return {
            "type": "LayerSection",
            "name": self.name,
            "layer": self.layer.to_dict(),
            "width": str(self.width) if isinstance(self.width, sympy.Expr) else self.width,
            "offset": str(self.offset) if isinstance(self.offset, sympy.Expr) else self.offset,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayerSection:
        """Create a LayerSection from a dictionary."""
        from gdswell.layer import Layer

        width = data["width"]
        if isinstance(width, str):
            width = sympy.sympify(width)
        offset = data["offset"]
        if isinstance(offset, str):
            offset = sympy.sympify(offset)

        return cls(
            name=data["name"], layer=Layer.from_dict(data["layer"]), width=width, offset=offset
        )

    def clip(
        self, min_val: float | None = None, max_val: float | None = None
    ) -> LayerSection | None:
        """
        Return a new LayerSection with width and offset clipped to the given range.
        If the section is entirely outside the range, returns None.
        Supports both constant values and SymPy expressions.
        """
        d_left = self.offset + self.width / 2
        d_right = self.offset - self.width / 2

        def _smart_max(a: Any, b: Any) -> Any:
            if isinstance(a, sympy.Expr) or isinstance(b, sympy.Expr):
                return sympy.Max(a, b)
            return max(float(a), float(b))

        def _smart_min(a: Any, b: Any) -> Any:
            if isinstance(a, sympy.Expr) or isinstance(b, sympy.Expr):
                return sympy.Min(a, b)
            return min(float(a), float(b))

        if min_val is not None:
            d_left = _smart_max(d_left, min_val)
            d_right = _smart_max(d_right, min_val)
        if max_val is not None:
            d_left = _smart_min(d_left, max_val)
            d_right = _smart_min(d_right, max_val)

        new_width = d_left - d_right
        if not isinstance(new_width, sympy.Expr):
            if new_width <= 1e-12:
                return None

        new_offset = (d_left + d_right) / 2

        return LayerSection(
            name=self.name,
            layer=self.layer,
            width=new_width,
            offset=new_offset,
        )


@dataclass(frozen=True)
class CellSection:
    """
    A section of a cross-section that places a cell periodically along the path.

    Attributes:
        name: Name of the section.
        cell: The gdswell Cell to place.
        periodicity: Spacing between cell placements. Can be a float or s-expression.
        x_offset_initial: Offset along the path from the start to start placing cells.
            Can be a float or s-expression.
        x_offset_final: Offset along the path from the end to stop placing cells.
            Can be a float or s-expression.
        y_offset: Offset perpendicular to the path. Can be a float or s-expression.
    """

    name: str
    cell: Cell
    periodicity: float | sympy.Expr
    x_offset_initial: float | sympy.Expr = 0.0
    x_offset_final: float | sympy.Expr = 0.0
    y_offset: float | sympy.Expr = 0.0

    @cached_property
    def _hash_string(self) -> str:
        """Cached deterministic string for hashing."""
        p = (
            str(self.periodicity)
            if isinstance(self.periodicity, sympy.Expr)
            else f"{self.periodicity:.10g}"
        )
        xi = (
            str(self.x_offset_initial)
            if isinstance(self.x_offset_initial, sympy.Expr)
            else f"{self.x_offset_initial:.10g}"
        )
        xf = (
            str(self.x_offset_final)
            if isinstance(self.x_offset_final, sympy.Expr)
            else f"{self.x_offset_final:.10g}"
        )
        y = str(self.y_offset) if isinstance(self.y_offset, sympy.Expr) else f"{self.y_offset:.10g}"
        return f"CS({self.name},{self.cell.name},{p},{xi},{xf},{y})"

    @cached_property
    def _fp(self) -> Callable[[np.ndarray], np.ndarray]:
        if isinstance(self.periodicity, (int, float)):
            return lambda s: np.full_like(s, float(self.periodicity), dtype=float)
        return cast(
            Callable[[np.ndarray], np.ndarray], sympy.lambdify(S, self.periodicity, "numpy")
        )

    @cached_property
    def _fxi(self) -> Callable[[np.ndarray], np.ndarray]:
        if isinstance(self.x_offset_initial, (int, float)):
            return lambda s: np.full_like(s, float(self.x_offset_initial), dtype=float)
        return cast(
            Callable[[np.ndarray], np.ndarray], sympy.lambdify(S, self.x_offset_initial, "numpy")
        )

    @cached_property
    def _fxf(self) -> Callable[[np.ndarray], np.ndarray]:
        if isinstance(self.x_offset_final, (int, float)):
            return lambda s: np.full_like(s, float(self.x_offset_final), dtype=float)
        return cast(
            Callable[[np.ndarray], np.ndarray], sympy.lambdify(S, self.x_offset_final, "numpy")
        )

    @cached_property
    def _fy(self) -> Callable[[np.ndarray], np.ndarray]:
        if isinstance(self.y_offset, (int, float)):
            return lambda s: np.full_like(s, float(self.y_offset), dtype=float)
        return cast(Callable[[np.ndarray], np.ndarray], sympy.lambdify(S, self.y_offset, "numpy"))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, CellSection):
            return False
        if self.name != other.name or self.cell != other.cell:
            return False

        # Fast comparison for numbers
        def close(a: Any, b: Any) -> bool:
            if type(a) in (float, int) and type(b) in (float, int):
                return abs(float(a) - float(b)) < 1e-12
            return a == b

        return (
            close(self.periodicity, other.periodicity)
            and close(self.x_offset_initial, other.x_offset_initial)
            and close(self.x_offset_final, other.x_offset_final)
            and close(self.y_offset, other.y_offset)
        )

    def evaluate(self, s_val: float) -> CellSection:
        """Evaluate parameters at a given position s and return a static CellSection."""
        s = np.array([float(s_val)])
        p = self._fp(s)[0]
        xi = self._fxi(s)[0]
        xf = self._fxf(s)[0]
        y = self._fy(s)[0]
        return CellSection(
            name=self.name,
            cell=self.cell,
            periodicity=float(p),
            x_offset_initial=float(xi),
            x_offset_final=float(xf),
            y_offset=float(y),
        )

    def to_dict(self) -> dict[str, Any]:
        """Returns a JSON-serializable dictionary representation."""
        return {
            "type": "CellSection",
            "name": self.name,
            "cell": self.cell.name,
            "periodicity": str(self.periodicity)
            if isinstance(self.periodicity, sympy.Expr)
            else self.periodicity,
            "x_offset_initial": str(self.x_offset_initial)
            if isinstance(self.x_offset_initial, sympy.Expr)
            else self.x_offset_initial,
            "x_offset_final": str(self.x_offset_final)
            if isinstance(self.x_offset_final, sympy.Expr)
            else self.x_offset_final,
            "y_offset": str(self.y_offset)
            if isinstance(self.y_offset, sympy.Expr)
            else self.y_offset,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], layout: Layout | None = None) -> CellSection:
        """Create a CellSection from a dictionary."""
        if layout is None:
            msg = "Layout context required to restore CellSection from dictionary."
            raise ValueError(msg)

        cell_name = data["cell"]
        # 1. Check layout cache first (handles Cell and FutureCell)
        res_cell = layout._cache.get(cell_name)

        if not res_cell:
            # 2. Check klayout cells
            kdb_cell = layout.kdb.cell(cell_name)
            if not kdb_cell:
                from gdswell.config import config

                if config.use_disk_cache:
                    # 3. Try to load from disk cache
                    cache_file = config.cache_dir / f"{cell_name}.oas"
                    if cache_file.exists():
                        layout._read_internal(str(cache_file), cell_name=cell_name)
                        kdb_cell = layout.kdb.cell(cell_name)

            if kdb_cell:
                from gdswell.cell import Cell

                res_cell = Cell._from_kdb_cell(kdb_cell, layout=layout)
        if not res_cell:
            msg = f"Cell '{cell_name}' not found in layout while restoring CellSection."
            raise KeyError(msg)

        periodicity = data["periodicity"]
        if isinstance(periodicity, str) and not periodicity.replace(".", "", 1).isdigit():
            periodicity = sympy.sympify(periodicity)

        x_offset_initial = data.get("x_offset_initial", 0.0)
        if isinstance(x_offset_initial, str) and not x_offset_initial.replace(".", "", 1).isdigit():
            x_offset_initial = sympy.sympify(x_offset_initial)

        x_offset_final = data.get("x_offset_final", 0.0)
        if isinstance(x_offset_final, str) and not x_offset_final.replace(".", "", 1).isdigit():
            x_offset_final = sympy.sympify(x_offset_final)

        y_offset = data.get("y_offset", 0.0)
        if isinstance(y_offset, str) and not y_offset.replace(".", "", 1).isdigit():
            y_offset = sympy.sympify(y_offset)

        return cls(
            name=data["name"],
            cell=res_cell,
            periodicity=periodicity,
            x_offset_initial=x_offset_initial,
            x_offset_final=x_offset_final,
            y_offset=y_offset,
        )


@dataclass(frozen=True)
class CrossSection:
    """
    Represents the transverse profile of a waveguide.
    Consists of multiple LayerSection and CellSection entries.
    """

    layer_sections: tuple[LayerSection, ...] = ()
    cell_sections: tuple[CellSection, ...] = ()

    def __call__(self) -> CrossSection:
        return self

    def __post_init__(self) -> None:
        # Pre-sort layer sections by name for deterministic equality and hashing
        if self.layer_sections:
            sorted_ls = tuple(sorted(self.layer_sections, key=lambda s: s.name))
            if sorted_ls != self.layer_sections:
                object.__setattr__(self, "layer_sections", sorted_ls)

    @cached_property
    def _hash_string(self) -> str:
        """Cached deterministic string for hashing."""
        ls_hashes = ",".join(s._hash_string for s in self.layer_sections)
        cs_hashes = ",".join(s._hash_string for s in self.cell_sections)
        return f"XS(({ls_hashes}),({cs_hashes}))"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, CrossSection):
            return False
        # Connectivity equality only depends on layer sections
        return self.layer_sections == other.layer_sections

    def evaluate(self, s: float) -> CrossSection:
        """Evaluate all sections at position s."""
        return CrossSection(
            layer_sections=tuple(sec.evaluate(s) for sec in self.layer_sections),
            cell_sections=tuple(sec.evaluate(s) for sec in self.cell_sections),
        )

    def without_cell_sections(self) -> CrossSection:
        """Return a new CrossSection without any cell sections."""
        return CrossSection(layer_sections=self.layer_sections)

    def evaluate_vectorized(
        self, s: np.ndarray
    ) -> list[tuple[LayerSection | CellSection, np.ndarray | None, np.ndarray | None]]:
        """Evaluate all sections at multiple positions s."""
        results = []
        for section in self.layer_sections:
            ws, offsets = section.evaluate_vectorized(s)
            results.append((section, ws, offsets))
        for section in self.cell_sections:
            results.append((section, None, None))
        return results

    def to_dict(self) -> dict[str, Any]:
        """Returns a JSON-serializable dictionary representation."""
        return {
            "layer_sections": [s.to_dict() for s in self.layer_sections],
            "cell_sections": [s.to_dict() for s in self.cell_sections],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], layout: Layout | None = None) -> CrossSection:
        """Create a CrossSection from a dictionary."""
        layer_sections = [
            LayerSection.from_dict(s_data) for s_data in data.get("layer_sections", [])
        ]
        if not layer_sections and "sections" in data:
            layer_sections = [LayerSection.from_dict(s_data) for s_data in data["sections"]]

        cell_sections = [
            CellSection.from_dict(s_data, layout=layout) for s_data in data.get("cell_sections", [])
        ]
        return cls(layer_sections=tuple(layer_sections), cell_sections=tuple(cell_sections))

    def transition(self, other: CrossSection, f_s: sympy.Expr | None = None) -> CrossSection:
        """
        Create a new CrossSection that transitions from self to other.

        Args:
            other: The target CrossSection.
            f_s: A sympy expression of 'S' that defines the transition profile (0 to 1).
                 Defaults to S (linear transition from 0 to 1).
        """
        if f_s is None:
            f_s = S

        if self.cell_sections or other.cell_sections:
            msg = "CrossSection transition is not supported for sections with cell_sections."
            raise ValueError(msg)

        # Match sections by name
        self_sections = {s.name: s for s in self.layer_sections}
        other_sections = {s.name: s for s in other.layer_sections}

        all_names = set(self_sections.keys()) | set(other_sections.keys())

        new_sections = []
        for name in all_names:
            s1 = self_sections.get(name)
            s2 = other_sections.get(name)

            if s1 and s2:
                if s1.layer != s2.layer:
                    raise ValueError(
                        f"Section '{name}' has mismatched layers: {s1.layer} vs {s2.layer}"
                    )

                # Interpolate width and offset
                w = s1.width + (s2.width - s1.width) * f_s
                o = s1.offset + (s2.offset - s1.offset) * f_s
                new_sections.append(LayerSection(name=name, layer=s1.layer, width=w, offset=o))
            elif s1:
                # Transition width to 0 if not in other
                w = s1.width * (1 - f_s)
                new_sections.append(
                    LayerSection(name=name, layer=s1.layer, width=w, offset=s1.offset)
                )
            elif s2:
                # Transition from width 0 if not in self
                w = s2.width * f_s
                new_sections.append(
                    LayerSection(name=name, layer=s2.layer, width=w, offset=s2.offset)
                )

        return CrossSection(tuple(new_sections))

    def clip(self, min_val: float | None = None, max_val: float | None = None) -> CrossSection:
        """
        Return a new CrossSection with all layer sections clipped to the given range.
        """
        new_sections = []
        for section in self.layer_sections:
            clipped = section.clip(min_val, max_val)
            if clipped is not None:
                new_sections.append(clipped)
        return CrossSection(tuple(new_sections), self.cell_sections)


CrossSectionCallable = Union[CrossSection, Callable[[], CrossSection]]
