# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Callable, Iterable

if TYPE_CHECKING:
    from gdswell.cell import Cell
    from gdswell.cross_section import CrossSection
    from gdswell.instance import Instance
    from gdswell.port import Port


from gdswell.decorator import cell


@cell
def chain_components(
    components: Iterable[Cell | Callable[[], Cell]],
) -> Cell:
    """
    Chain a list of components sequentially.
    The first component is placed at the origin.
    The resulting cell will have ports '0' and '1' at the ends of the chain.
    """
    from gdswell.cell import Cell

    it = iter(components)
    try:
        first = next(it)
        if callable(first) and not isinstance(first, Cell):
            first = first()
    except StopIteration:
        raise ValueError("Cannot chain empty list of components")

    c = Cell()
    # Place first component at origin
    inst = c.add_ref(first, origin=(0, 0), rotation=0)
    p0 = inst["0"]
    p1 = inst["1"]

    accumulated_length = first.info.get("length")
    if accumulated_length is None:
        raise ValueError(f"Component '{first.name}' is missing 'length' in its info.")

    for comp in it:
        if callable(comp) and not isinstance(comp, Cell):
            comp = comp()

        comp_len = comp.info.get("length")
        if comp_len is None:
            raise ValueError(f"Component '{comp.name}' is missing 'length' in its info.")
        accumulated_length += comp_len

        p1 = c.add_ref_connected(comp, "0", p1)["1"]

    c.add_port(p0.renamed("0"))
    c.add_port(p1.renamed("1"))
    c.add_info("length", accumulated_length)
    return c


def route_step_by_step(
    cell: Cell,
    port1: Port,
    port2: Port,
    components: Iterable[Cell | Callable[[], Cell]],
) -> Instance:
    """Produce a waveguide path by chaining components and adding it to the cell."""
    chained_cell = chain_components(components)

    # Place the entire chain such that its '0' connects to port1
    inst = cell.add_ref_connected(chained_cell, "0", port1)
    final_port = inst["1"]

    if not final_port.connects_to(port2):
        dx = port2.position[0] - final_port.position[0]
        dy = port2.position[1] - final_port.position[1]
        da = (port2.angle - final_port.angle) % 360
        raise RuntimeError(
            f"Route failed: {final_port} does not connect to {port2}.\n"
            f"  Distance: dx={dx:.3e}, dy={dy:.3e}, dist={(dx**2 + dy**2) ** 0.5:.3e}\n"
            f"  Angle difference: {da}° (Expected 180° for connection)"
        )

    return inst


def route_l_cell(
    dx: float,
    dy: float,
    radius: float,
    bend_factory: Callable[..., Cell],
    straight_factory: Callable[..., Cell],
    balanced: bool = False,
) -> Cell:
    """Cell factory for an L-route based on relative coordinates."""
    comps = _get_route_l_components_raw(
        dx, dy, radius, bend_factory, straight_factory, balanced=balanced
    )
    return chain_components(comps)


def route_z_cell(
    dx: float,
    dy: float,
    radius: float,
    bend_factory: Callable[..., Cell],
    straight_factory: Callable[..., Cell],
    balanced: bool = False,
) -> Cell:
    """Cell factory for a Z-route based on relative coordinates."""
    comps = _get_route_z_components_raw(
        dx, dy, radius, bend_factory, straight_factory, balanced=balanced
    )
    return chain_components(comps)


def route_u_cell(
    dx: float,
    dy: float,
    radius: float,
    bend_factory: Callable[..., Cell],
    straight_factory: Callable[..., Cell],
    balanced: bool = False,
) -> Cell:
    """Cell factory for a U-route based on relative coordinates."""
    comps = _get_route_u_components_raw(
        dx, dy, radius, bend_factory, straight_factory, balanced=balanced
    )
    return chain_components(comps)


def route_manhattan_cell(
    dx: float,
    dy: float,
    target_rel_angle: int,
    radius: float,
    bend_factory: Callable[..., Cell],
    straight_factory: Callable[..., Cell],
    balanced: bool = False,
) -> Cell:
    """Cell factory for a Manhattan route based on relative coordinates."""
    match target_rel_angle:
        case 0:
            return route_z_cell(dx, dy, radius, bend_factory, straight_factory, balanced=balanced)
        case 180:
            return route_u_cell(dx, dy, radius, bend_factory, straight_factory, balanced=balanced)
        case 90 | 270:
            return route_l_cell(dx, dy, radius, bend_factory, straight_factory, balanced=balanced)
        case _:
            raise ValueError(f"Unsupported Manhattan routing relative angle: {target_rel_angle}°.")


def route_manhattan(
    cell: Cell,
    port1: Port,
    port2: Port,
    radius: float,
    cross_section: CrossSection | None = None,
    bend: Callable | None = None,
    straight: Callable | None = None,
    start_straight_length: float = 0.0,
    with_cell_sections_in_bend: bool = True,
    balanced: bool = False,
) -> Instance:
    """High-level Manhattan router."""
    from gdswell.components.bend_circular import bend_circular
    from gdswell.components.straight import straight as straight_comp

    bend_func = bend or bend_circular
    straight_func = straight or straight_comp
    xs = cross_section or port1.cross_section

    # Prepare factories
    bend_xs = xs
    if not with_cell_sections_in_bend:
        bend_xs = xs().without_cell_sections()

    bend_factory = functools.partial(bend_func, bend_xs)
    straight_factory = functools.partial(straight_func, xs)

    if start_straight_length > 0:
        # Handle start straight separately to keep the core route cell clean and reusable
        s_inst = cell.add_ref_connected(straight_factory(start_straight_length), "0", port1)
        port1 = s_inst["1"]

    a1 = port1.angle % 360
    a2 = port2.angle % 360
    target_flow = (a2 + 180) % 360
    target_rel_angle = int((target_flow - a1) % 360)

    dx, dy = _get_local_coords(
        a1, port1.position[0], port1.position[1], port2.position[0], port2.position[1]
    )

    route_cell = route_manhattan_cell(
        dx, dy, target_rel_angle, radius, bend_factory, straight_factory, balanced=balanced
    )
    return cell.add_ref_connected(route_cell, "0", port1)


def route_l(
    cell: Cell,
    port1: Port,
    port2: Port,
    radius: float,
    cross_section: CrossSection | None = None,
    bend: Callable | None = None,
    straight: Callable | None = None,
    start_straight_length: float = 0.0,
    with_cell_sections_in_bend: bool = True,
    balanced: bool = False,
) -> Instance:
    """Manhattan L-route placement."""
    from gdswell.components.bend_circular import bend_circular
    from gdswell.components.straight import straight as straight_comp

    bend_func = bend or bend_circular
    straight_func = straight or straight_comp
    xs = cross_section or port1.cross_section

    # Prepare factories
    bend_xs = xs
    if not with_cell_sections_in_bend:
        bend_xs = xs().without_cell_sections()

    bend_factory = functools.partial(bend_func, bend_xs)
    straight_factory = functools.partial(straight_func, xs)

    if start_straight_length > 0:
        s_inst = cell.add_ref_connected(straight_factory(start_straight_length), "0", port1)
        port1 = s_inst["1"]

    dx, dy = _get_local_coords(
        port1.angle % 360,
        port1.position[0],
        port1.position[1],
        port2.position[0],
        port2.position[1],
    )
    route_cell = route_l_cell(dx, dy, radius, bend_factory, straight_factory, balanced=balanced)
    return cell.add_ref_connected(route_cell, "0", port1)


def route_z(
    cell: Cell,
    port1: Port,
    port2: Port,
    radius: float,
    cross_section: CrossSection | None = None,
    bend: Callable | None = None,
    straight: Callable | None = None,
    start_straight_length: float = 0.0,
    with_cell_sections_in_bend: bool = True,
    balanced: bool = False,
) -> Instance:
    """Manhattan Z-route placement."""
    from gdswell.components.bend_circular import bend_circular
    from gdswell.components.straight import straight as straight_comp

    bend_func = bend or bend_circular
    straight_func = straight or straight_comp
    xs = cross_section or port1.cross_section

    # Prepare factories
    bend_xs = xs
    if not with_cell_sections_in_bend:
        bend_xs = xs().without_cell_sections()

    bend_factory = functools.partial(bend_func, bend_xs)
    straight_factory = functools.partial(straight_func, xs)

    if start_straight_length > 0:
        s_inst = cell.add_ref_connected(straight_factory(start_straight_length), "0", port1)
        port1 = s_inst["1"]

    dx, dy = _get_local_coords(
        port1.angle % 360,
        port1.position[0],
        port1.position[1],
        port2.position[0],
        port2.position[1],
    )
    route_cell = route_z_cell(dx, dy, radius, bend_factory, straight_factory, balanced=balanced)
    return cell.add_ref_connected(route_cell, "0", port1)


def route_u(
    cell: Cell,
    port1: Port,
    port2: Port,
    radius: float,
    cross_section: CrossSection | None = None,
    bend: Callable | None = None,
    straight: Callable | None = None,
    start_straight_length: float = 0.0,
    with_cell_sections_in_bend: bool = True,
    balanced: bool = False,
) -> Instance:
    """Manhattan U-route placement."""
    from gdswell.components.bend_circular import bend_circular
    from gdswell.components.straight import straight as straight_comp

    bend_func = bend or bend_circular
    straight_func = straight or straight_comp
    xs = cross_section or port1.cross_section

    # Prepare factories
    bend_xs = xs
    if not with_cell_sections_in_bend:
        bend_xs = xs().without_cell_sections()

    bend_factory = functools.partial(bend_func, bend_xs)
    straight_factory = functools.partial(straight_func, xs)

    if start_straight_length > 0:
        s_inst = cell.add_ref_connected(straight_factory(start_straight_length), "0", port1)
        port1 = s_inst["1"]

    dx, dy = _get_local_coords(
        port1.angle % 360,
        port1.position[0],
        port1.position[1],
        port2.position[0],
        port2.position[1],
    )
    route_cell = route_u_cell(dx, dy, radius, bend_factory, straight_factory, balanced=balanced)
    return cell.add_ref_connected(route_cell, "0", port1)


# --- Geometry Generation Functions (No Side Effects) ---


def _get_route_l_components_raw(
    dx: float,
    dy: float,
    radius: float,
    bend: Callable,
    straight: Callable,
    balanced: bool = False,
) -> list[functools.partial[Cell]]:
    """Geometric components for an L-route using relative coordinates."""
    # We assume 'target_rel_angle' was used to dispatch here, but let's re-verify relative flow
    # for internal consistency if needed. For now, we trust the relative dx, dy.

    # In _get_local_coords, dx is ALWAYS along the port1 direction.
    # rel_target_flow of 90 means port2 is at +90 deg relative to port1.
    # Since we don't have port2 angle here, we rely on dx, dy signs.

    if dy > 0:  # rel_target_flow = 90
        if dx >= radius and dy >= radius:
            res: list[functools.partial[Cell]] = []
            if dx > radius:
                res.append(functools.partial(straight, dx - radius))
            res.append(functools.partial(bend, radius, 90))
            if dy > radius:
                res.append(functools.partial(straight, dy - radius))
            return res
        else:
            # Tight: decompose into Z-route + final 90 bend
            # This recursion is tricky without Port objects.
            # But we can just calculate the components for the Z-part.
            z_comps = _get_route_z_components_raw(
                dx - radius, dy - radius, radius, bend, straight, balanced=balanced
            )
            return z_comps + [functools.partial(bend, radius, 90)]
    else:  # dy < 0, rel_target_flow = 270
        if dx >= radius and dy <= -radius:
            res: list[functools.partial[Cell]] = []
            if dx > radius:
                res.append(functools.partial(straight, dx - radius))
            res.append(functools.partial(bend, radius, -90))
            if abs(dy) > radius:
                res.append(functools.partial(straight, abs(dy) - radius))
            return res
        else:
            z_comps = _get_route_z_components_raw(
                dx - radius, dy + radius, radius, bend, straight, balanced=balanced
            )
            return z_comps + [functools.partial(bend, radius, -90)]


def _get_route_z_components_raw(
    dx: float,
    dy: float,
    radius: float,
    bend: Callable,
    straight: Callable,
    balanced: bool = False,
) -> list[functools.partial[Cell]]:
    """Geometric components for a Z-route using relative coordinates."""
    if abs(dy) < 1e-9 and dx > 0:
        return [functools.partial(straight, dx)]
    elif abs(dy) >= 2 * radius and dx >= 2 * radius:
        # Wide Z
        l3 = dx - 2 * radius
        if balanced:
            res: list[functools.partial[Cell]] = []
            if l3 > 1e-9:
                res.append(functools.partial(straight, l3 / 2))
            res.append(functools.partial(bend, radius, 90 if dy > 0 else -90))
            res.append(functools.partial(straight, abs(dy) - 2 * radius))
            res.append(functools.partial(bend, radius, -90 if dy > 0 else 90))
            if l3 > 1e-9:
                res.append(functools.partial(straight, l3 / 2))
            return res
        else:
            # Bend as early as possible
            res: list[functools.partial[Cell]] = [
                functools.partial(bend, radius, 90 if dy > 0 else -90),
                functools.partial(straight, abs(dy) - 2 * radius),
                functools.partial(bend, radius, -90 if dy > 0 else 90),
            ]
            if l3 > 1e-9:
                res.append(functools.partial(straight, l3))
            return res
    else:
        # Behind or Jog
        if dx < 2 * radius:
            if abs(dy) < 4 * radius:
                raise RuntimeError(
                    f"Z-route behind and tight in Y: dx={dx:.3f}, dy={dy:.3f}. "
                    f"Required |dy| >= 4*radius ({4 * radius}) for this configuration."
                )
            return [
                functools.partial(bend, radius, 90 if dy > 0 else -90),
                functools.partial(bend, radius, 90 if dy > 0 else -90),
                functools.partial(straight, -dx),
                functools.partial(bend, radius, -90 if dy > 0 else 90),
                functools.partial(straight, abs(dy) - 4 * radius),
                functools.partial(bend, radius, -90 if dy > 0 else 90),
            ]
        elif dx >= 4 * radius:
            l_extra = radius
            l_mid = dx - 4 * radius
            return [
                functools.partial(bend, radius, -90 if dy > 0 else 90),
                functools.partial(straight, l_extra),
                functools.partial(bend, radius, 90 if dy > 0 else -90),
                functools.partial(straight, l_mid),
                functools.partial(bend, radius, 90 if dy > 0 else -90),
                functools.partial(straight, l_extra + abs(dy)),
                functools.partial(bend, radius, -90 if dy > 0 else 90),
            ]
        else:
            raise RuntimeError(
                f"Z-route too tight: dx={dx:.3f}, dy={dy:.3f}. "
                f"Requires dx >= 2*radius ({2 * radius}) and |dy| >= 2*radius ({2 * radius}) "
                "or dx < 2*radius and |dy| >= 4*radius."
            )


def _get_route_u_components_raw(
    dx: float,
    dy: float,
    radius: float,
    bend: Callable,
    straight: Callable,
    balanced: bool = False,
) -> list[functools.partial[Cell]]:
    """Geometric components for a U-route using relative coordinates."""
    if abs(dy) >= 2 * radius:
        # For U-route, the most "balanced" (compact) is the greedy one.
        l_out = max(radius, dx + radius)
        l_back = l_out - dx

        res: list[functools.partial[Cell]] = [
            functools.partial(straight, l_out),
            functools.partial(bend, radius, 90 if dy > 0 else -90),
            functools.partial(straight, abs(dy) - 2 * radius),
            functools.partial(bend, radius, 90 if dy > 0 else -90),
        ]
        if l_back > 1e-9:
            res.append(functools.partial(straight, l_back))
        return res
    else:
        raise RuntimeError(
            f"Tight U-route: dy={dy:.3f}. Required |dy| >= 2*radius ({2 * radius}) "
            "for current U-route implementation."
        )


# --- Internal Helpers ---


def _get_local_coords(a1: int, x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    dx_abs, dy_abs = x2 - x1, y2 - y1
    match int(a1 % 360):
        case 0:
            return dx_abs, dy_abs
        case 90:
            return dy_abs, -dx_abs
        case 180:
            return -dx_abs, -dy_abs
        case 270:
            return -dy_abs, dx_abs
        case _:
            raise ValueError(
                f"Manhattan routing requires 90-degree aligned ports, got {a1}°. "
                "Check that port angles are 0, 90, 180, or 270 degrees."
            )


def _get_global_pos(a1: int, x1: float, y1: float, dx: float, dy: float) -> tuple[float, float]:
    match int(a1 % 360):
        case 0:
            return x1 + dx, y1 + dy
        case 90:
            return x1 - dy, y1 + dx
        case 180:
            return x1 - dx, y1 - dy
        case 270:
            return x1 + dy, y1 - dx
        case _:
            raise ValueError(
                f"Manhattan routing requires 90-degree aligned ports, got {a1}°. "
                "Check that port angles are 0, 90, 180, or 270 degrees."
            )
