# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

import functools
from typing import Any, Callable, Protocol, cast, runtime_checkable

import numpy as np
import sympy

from gdswell.cell import Cell
from gdswell.cross_section import CrossSection, CrossSectionCallable, S
from gdswell.port import Port


@functools.lru_cache(maxsize=1024)
def _cached_diff(expr: sympy.Expr, symbol: sympy.Symbol) -> sympy.Expr:
    """Cached sympy differentiation."""
    return sympy.diff(expr, symbol)


@functools.lru_cache(maxsize=1024)
def _cached_lambdify(expr: sympy.Expr, symbol: sympy.Symbol) -> Callable[[np.ndarray], np.ndarray]:
    """Cached sympy lambdification."""
    return cast(Callable[[np.ndarray], np.ndarray], sympy.lambdify(symbol, expr, "numpy"))


@functools.lru_cache(maxsize=1024)
def _cached_speed_expr(dx_ds: sympy.Expr, dy_ds: sympy.Expr) -> sympy.Expr:
    """Cached sympy speed expression."""
    return sympy.sqrt(dx_ds**2 + dy_ds**2)


@functools.lru_cache(maxsize=1024)
def _cached_integrate_length(speed_expr: sympy.Expr) -> float | None:
    """Cached symbolic integration of the speed expression."""
    res = sympy.integrate(speed_expr, (S, 0, 1))
    if res.is_number:
        return float(res)
    return None


@runtime_checkable
class PathEvaluator(Protocol):
    """Protocol for evaluating path positions, derivatives, and length."""

    @property
    def length(self) -> float:
        """Physical length of the path."""
        ...

    def evaluate_pos(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Evaluate (x, y) at s."""
        ...

    def evaluate_deriv(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Evaluate (dx/ds, dy/ds) at s."""
        ...

    def evaluate_speed(self, s: np.ndarray) -> np.ndarray:
        """Evaluate speed sqrt((dx/ds)^2 + (dy/ds)^2) at s."""
        ...

    def evaluate_theta(self, s: np.ndarray) -> np.ndarray:
        """Evaluate tangent angle arctan2(dy/ds, dx/ds) at s."""
        ...


class SympyPathEvaluator:
    """Sympy-based implementation of PathEvaluator."""

    def __init__(self, x_expr: sympy.Expr | str, y_expr: sympy.Expr | str):
        self.x_expr = sympy.sympify(x_expr)
        self.y_expr = sympy.sympify(y_expr)

        self.dx_ds_expr = _cached_diff(self.x_expr, S)
        self.dy_ds_expr = _cached_diff(self.y_expr, S)
        self.speed_expr = _cached_speed_expr(self.dx_ds_expr, self.dy_ds_expr)

        self.fx = _cached_lambdify(self.x_expr, S)
        self.fy = _cached_lambdify(self.y_expr, S)
        self.fdx = _cached_lambdify(self.dx_ds_expr, S)
        self.fdy = _cached_lambdify(self.dy_ds_expr, S)

    @functools.cached_property
    def length(self) -> float:
        """Calculate physical length using symbolic or numerical integration."""
        # 1. Try symbolic integration
        # res = _cached_integrate_length(self.speed_expr)
        # if res is not None:
        #     return res

        # 2. Fast check for constant speed (like straights and circles)
        if S not in self.speed_expr.free_symbols:
            return float(self.speed_expr.evalf())

        # 3. Fallback to numerical integration (extremely fast and accurate enough)
        s_vals = np.linspace(0, 1.0, 1001)
        speed_vals = self.evaluate_speed(s_vals)
        return float(np.trapezoid(speed_vals, s_vals))

    def evaluate_pos(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Evaluate (x, y) at s."""
        return self._eval(self.fx, s), self._eval(self.fy, s)

    def evaluate_deriv(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Evaluate (dx/ds, dy/ds) at s."""
        return self._eval(self.fdx, s), self._eval(self.fdy, s)

    def evaluate_speed(self, s: np.ndarray) -> np.ndarray:
        """Evaluate speed sqrt((dx/ds)^2 + (dy/ds)^2) at s."""
        dx, dy = self.evaluate_deriv(s)
        return np.sqrt(dx**2 + dy**2)

    def evaluate_theta(self, s: np.ndarray) -> np.ndarray:
        """Evaluate tangent angle arctan2(dy/ds, dx/ds) at s."""
        dx, dy = self.evaluate_deriv(s)
        return np.arctan2(dy, dx)

    def _eval(self, f: Callable[[np.ndarray], np.ndarray], s: np.ndarray) -> np.ndarray:
        val = f(s)
        if np.isscalar(val):
            return np.full_like(s, val, dtype=float)
        return np.atleast_1d(val).astype(float)


@functools.lru_cache(maxsize=1024)
def _get_sympy_path_evaluator(
    x_expr: sympy.Expr | str, y_expr: sympy.Expr | str
) -> SympyPathEvaluator:
    """Cached factory for SympyPathEvaluator."""
    return SympyPathEvaluator(x_expr, y_expr)


def generic_path(
    cross_section: CrossSectionCallable,
    x_expr: sympy.Expr | str,
    y_expr: sympy.Expr | str,
    npoints: int = 100,
) -> Cell:
    """
    Create a waveguide following an arbitrary path defined by SymPy expressions.

    Args:
        cross_section: The cross-section to use.
        x_expr: Sympy expression for x(s).
        y_expr: Sympy expression for y(s).
        npoints: Number of points along the path for discretization.
    """
    c = Cell()
    path = _get_sympy_path_evaluator(x_expr, y_expr)
    xs = cross_section()
    _populate_path(c, xs, path, npoints)
    add_ports(c, path, xs)
    return c


def _populate_path(
    c: Cell,
    cross_section: CrossSection,
    path: PathEvaluator,
    npoints: int = 100,
) -> None:
    """Populate a cell with a waveguide following an arbitrary path."""
    s_vals = np.linspace(0, 1.0, npoints)

    # Skip geometry if the path has zero length (logical adapter case)
    if path.length > 1e-12:
        _add_layer_sections(c, path, cross_section, s_vals)
        _add_cell_sections(c, path, cross_section, s_vals)

    c.add_info("length", path.length)


def _add_layer_sections(
    c: Cell,
    path: PathEvaluator,
    cross_section: CrossSection,
    s_vals: np.ndarray,
) -> None:
    """Evaluate and add LayerSections (polygons/extrusions)."""
    x_vals, y_vals = path.evaluate_pos(s_vals)
    thetas = path.evaluate_theta(s_vals)
    cos_thetas = np.cos(thetas)
    sin_thetas = np.sin(thetas)

    for section in cross_section.layer_sections:
        ws, offsets = section.evaluate_vectorized(s_vals)

        l_offs = offsets + ws / 2
        r_offs = offsets - ws / 2

        pts_top_x = x_vals - l_offs * sin_thetas
        pts_top_y = y_vals + l_offs * cos_thetas

        pts_bottom_x = x_vals - r_offs * sin_thetas
        pts_bottom_y = y_vals + r_offs * cos_thetas

        poly_pts_x = np.concatenate([pts_top_x, pts_bottom_x[::-1]])
        poly_pts_y = np.concatenate([pts_top_y, pts_bottom_y[::-1]])
        poly_pts = np.stack([poly_pts_x, poly_pts_y], axis=1)

        c.add_polygon(poly_pts.tolist(), layer=section.layer)


def _add_cell_sections(
    c: Cell,
    path: PathEvaluator,
    cross_section: CrossSection,
    s_vals: np.ndarray,
) -> None:
    """Evaluate and add CellSections (periodic placements)."""
    if not cross_section.cell_sections:
        return

    # Compute cumulative path length at each grid point
    dx_vals, dy_vals = path.evaluate_deriv(s_vals)
    speed_vals = np.sqrt(dx_vals**2 + dy_vals**2)

    cum_dist = np.zeros_like(s_vals)
    _diffs = np.diff(s_vals)
    cum_dist[1:] = np.cumsum(0.5 * (speed_vals[:-1] + speed_vals[1:]) * _diffs)
    total_path_length = cum_dist[-1]

    x_vals, y_vals = path.evaluate_pos(s_vals)

    for section in cross_section.cell_sections:
        static_section = section.evaluate(0.0)
        periodicity = float(static_section.periodicity)
        x_initial = float(static_section.x_offset_initial)
        x_final = float(static_section.x_offset_final)
        y0 = float(static_section.y_offset)

        if periodicity <= 0:
            continue

        valid_length = total_path_length - x_final
        if valid_length < x_initial:
            continue

        num_placements = int(np.floor((valid_length - x_initial) / periodicity)) + 1
        if num_placements <= 0:
            continue

        l_placements = x_initial + np.arange(num_placements) * periodicity
        l_placements = l_placements[l_placements <= valid_length + 1e-9]

        s_placements = np.interp(l_placements, cum_dist, s_vals)

        x_p, y_p = path.evaluate_pos(s_placements)
        thetas_p = path.evaluate_theta(s_placements)

        for i, _ in enumerate(s_placements):
            angle = np.rad2deg(float(thetas_p[i]))
            manhattan_angle = int(round(angle / 90.0) * 90.0) % 360

            origin_x = float(x_p[i]) - y0 * np.sin(thetas_p[i])
            origin_y = float(y_p[i]) + y0 * np.cos(thetas_p[i])

            c.add_ref(
                section.cell,
                origin=(origin_x, origin_y),
                rotation=cast(Any, manhattan_angle),
            )


def add_ports(
    c: Cell,
    path: PathEvaluator,
    cross_section: CrossSection,
) -> None:
    """Add ports to the beginning and end of the path."""
    # Port 0 (s=0)
    x0, y0 = path.evaluate_pos(np.array([0.0]))
    th0 = path.evaluate_theta(np.array([0.0]))
    angle0 = (np.rad2deg(float(th0[0])) + 180.0) % 360.0
    c.add_port(
        Port(
            name="0",
            position=(float(x0[0]), float(y0[0])),
            angle=angle0,
            cross_section=cross_section.evaluate(0.0),
        )
    )

    # Port 1 (s=1)
    x1, y1 = path.evaluate_pos(np.array([1.0]))
    th1 = path.evaluate_theta(np.array([1.0]))
    angle1 = np.rad2deg(float(th1[0])) % 360.0
    c.add_port(
        Port(
            name="1",
            position=(float(x1[0]), float(y1[0])),
            angle=angle1,
            cross_section=cross_section.evaluate(1.0),
        )
    )
