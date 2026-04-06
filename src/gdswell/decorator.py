# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import functools
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Set, TypeVar, cast

import klayout.db as kdb_

from gdswell.cache import save_to_disk_cache
from gdswell.cell import Cell
from gdswell.config import config
from gdswell.future_cell import FutureCell
from gdswell.hashing import compute_cell_name
from gdswell.layout import Layout

_EXECUTOR = ThreadPoolExecutor(max_workers=config.max_workers)
_GLOBAL_PENDING: Dict[str, Any] = {}
_GLOBAL_LOCK = threading.RLock()


def _finalize_cell(
    cell: Cell,
    func: Callable[..., Cell],
    unique_name: str,
    bound_args: dict[str, str],
    deps: Set[Path] | None = None,
    external_pkgs: Set[str] | None = None,
) -> None:
    """Rename, add metadata, freeze, and optionally cache a cell."""
    if not isinstance(cell, Cell):
        msg = f"@cell function '{getattr(func, '__name__', 'unknown')}' must return a 'Cell'"
        raise TypeError(msg)

    if cell.frozen:
        name = getattr(func, "__name__", "unknown")
        raise RuntimeError(
            f"@cell decorated function '{name}' returned a cell "
            "that is already frozen. "
            "This usually happens if you call and return another @cell "
            "decorated function directly. "
            "Instead, create a new Cell() and use add_ref() to instantiate "
            "the sub-component."
        )

    # Rename for cache consistency
    cell.kdb.name = unique_name

    cell._function_name = getattr(func, "__name__", "unknown")
    cell._function_module = getattr(func, "__module__", "unknown")

    # Attach metadata and freeze
    for key, val in {
        "function_name": cell._function_name,
        "function_module": cell._function_module,
        "params": json.dumps(bound_args),
    }.items():
        cell._kdb_cell.add_meta_info(kdb_.LayoutMetaInfo(key, val, None, True))

    cell.freeze()

    # Save to disk cache
    if config.use_disk_cache:
        save_to_disk_cache(cell, unique_name, deps=deps, external_pkgs=external_pkgs)


def _build_cell_task(
    func: Callable[..., Cell],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    unique_name: str,
    bound_args: dict[str, str],
    deps: Set[Path] | None = None,
    external_pkgs: Set[str] | None = None,
) -> Cell:
    """Task to build a cell in a background thread."""
    from gdswell.stats import _record_build_time

    # Each thread works in its own Layout context to ensure thread-safety
    with Layout(name=f"thread_{unique_name}") as layout:
        try:
            start_time = time.perf_counter()
            created_cell = func(*args, **kwargs)
        except Exception:
            raise
        # Ensure all sub-cells generated in this thread are also completed
        layout.wait()
        duration = time.perf_counter() - start_time
        _record_build_time(getattr(func, "__name__", "unknown"), duration)

        _finalize_cell(created_cell, func, unique_name, bound_args, deps, external_pkgs)

        # Cleanup global pending registry
        with _GLOBAL_LOCK:
            _GLOBAL_PENDING.pop(unique_name, None)

        return created_cell


F = TypeVar("F", bound=Callable[..., Cell])


def cell(func: F) -> F:
    """
    Decorator to memoize a Cell based on its function and arguments.
    """
    func_name = getattr(func, "__name__", "unknown")
    fq = getattr(func, "__qualname__", "unknown")

    if func_name != fq:
        msg = (
            f"@cell decorated function '{func_name}' must be defined at the module level. "
            f"Nested functions or class methods (qualname '{fq}') are not supported "
            "as they break persistent caching."
        )
        raise RuntimeError(msg)

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Cell:
        from gdswell.stats import (
            _record_build_time,
            _record_call,
            _record_hit_disk,
            _record_hit_memory,
        )

        # Record call
        _record_call(func_name)

        # 1. Deterministic name
        try:
            unique_name, bound_args, deps, external_pkgs = compute_cell_name(func, args, kwargs)
        except TypeError as e:
            # Re-raise with function name context
            raise TypeError(
                f"Arguments to @cell decorated function '{func_name}' "
                f"with args {args} and kwargs {kwargs} "
                f"must be hashable. Error: {str(e)}"
            )

        # 2. Local cache lookup (for identity preservation)
        layout = Layout.get_active()

        with layout._lock:
            if unique_name in layout._cache:
                _record_hit_memory(func_name)
                return layout._cache[unique_name]

            # 3. KDB lookup (if realized but not in our wrapper cache)
            if layout.kdb.cell(unique_name) is not None:
                _record_hit_memory(func_name)
                cell = layout.cell(unique_name)
                return cell

            # 4. Disk cache lookup
            cache_file = config.cache_dir / f"{unique_name}.oas"
            if config.use_disk_cache and cache_file.exists():
                cell = layout._read_internal(str(cache_file), cell_name=unique_name)
                _record_hit_disk(func_name)
                return cell

            # 5. Global build synchronization (In-flight builds in other layouts/threads)
            with _GLOBAL_LOCK:
                if unique_name in _GLOBAL_PENDING:
                    future = _GLOBAL_PENDING[unique_name]
                    f_cell = FutureCell(future, layout, unique_name)
                    layout._cache[unique_name] = f_cell
                    layout._pending_cells.add(f_cell)
                    return f_cell

            # 6. Create cell on miss
            if not config.async_cells:
                start_time = time.perf_counter()
                created_cell = func(*args, **kwargs)
                duration = time.perf_counter() - start_time
                from gdswell.stats import _record_build_time

                _record_build_time(func_name, duration)

                _finalize_cell(created_cell, func, unique_name, bound_args, deps, external_pkgs)
                with layout._lock:
                    layout._cache[unique_name] = created_cell
                return created_cell
            else:
                # Asynchronously
                with _GLOBAL_LOCK:
                    # Double check after re-acquiring lock
                    if unique_name in _GLOBAL_PENDING:
                        future = _GLOBAL_PENDING[unique_name]
                    else:
                        future = _EXECUTOR.submit(
                            _build_cell_task,
                            func,
                            args,
                            kwargs,
                            unique_name,
                            bound_args,
                            deps,
                            external_pkgs,
                        )
                        _GLOBAL_PENDING[unique_name] = future

                f_cell = FutureCell(future, layout, unique_name)
                with layout._lock:
                    layout._cache[unique_name] = f_cell
                layout._pending_cells.add(f_cell)
                return f_cell

    return cast(F, wrapper)


if __name__ == "__main__":
    # Example usage
    from gdswell.layer import Layer

    class MyLayers(Layer, Enum):
        WG = (1, 0)

    @cell
    def sample_wg(width: float = 2.0, length: float = 15.0) -> Cell:
        """A simple waveguide geometry."""
        c = Cell()
        # Add a polygon
        c.add_polygon(
            [
                (0.0, -width / 2),
                (length, -width / 2),
                (length, width / 2),
                (0.0, width / 2),
            ],
            layer=MyLayers.WG,
        )
        return c

    @cell
    def top_level_cell(cell: Cell) -> Cell:
        """A cell that instantiates multiple waveguides."""
        layout = Layout.get_active()
        c = layout.create_cell()

        # Instantiate waveguides
        print("   Adding references to 'sample_wg' in 'top_level'...")
        wg1 = sample_wg(width=5.0, length=20.0)
        wg2 = sample_wg(width=5.0, length=20.0)
        wg3 = sample_wg(width=1.0, length=100.0)

        c.add_ref(wg1, origin=(0.0, 0.0))
        c.add_ref(wg2, origin=(0.0, 10.0))
        c.add_ref(wg3, origin=(0.0, 20.0))
        c.add_ref(cell, origin=(0.0, 30.0))

        return c

    print("--- gdswell @cell decorator Example ---")
    with Layout(name="demo_layout") as layout:
        print("1. Creating a hierarchical cell 'top_level_cell' that contains waveguides")
        wg1_partial = functools.partial(sample_wg, 5.0, length=20.0)
        # Note: top_level_cell expects a Cell, but here we pass a partial?
        # The original code might have intended to demonstrate something specific.
        # Fixed to pass a Cell.
        top = top_level_cell(wg1_partial())
        print(f"   Returned Top Cell Name: {top.name}")

        print("\n2. Inspecting the top cell's properties:")
        for prop in top.kdb.properties():
            print(f"   - {prop}: {top.kdb.property(prop)}")

        print(
            "\n3. Validating that cached cells were reused within "
            "'top_level_cell' (see console output above)"
        )

        print("\nDone! Feel free to export `layout.kdb.write('demo.gds')` to inspect visually!")

        options = kdb_.SaveLayoutOptions()
        options.write_context_info = True
        options.gds2_write_cell_properties = True
        options.gds2_write_file_properties = True
        layout.kdb.write("demo.gds", options)
