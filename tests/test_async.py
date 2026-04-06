# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import time
from enum import Enum

import pytest

import gdswell as gw


class MyLayers(gw.Layer, Enum):
    WG = (1, 0)


@gw.cell
def slow_cell(name: str, delay: float = 0.5) -> gw.Cell:
    time.sleep(delay)
    c = gw.Cell()
    c.add_polygon([(0, 0), (10, 0), (10, 1), (0, 1)], layer=MyLayers.WG)
    c.add_info("source", name)
    return c


@gw.cell
def hierarchical_cell(c1: gw.Cell, c2: gw.Cell) -> gw.Cell:
    c = gw.Cell()
    c.add_ref(c1, origin=(0, 0))
    c.add_ref(c2, origin=(0, 10))
    return c


@gw.cell
def broken_cell() -> gw.Cell:
    raise ValueError("Intentional error")


def test_async_parallelism() -> None:
    gw.config.async_cells = True
    with gw.Layout() as layout:
        top = layout.create_cell()
        start = time.perf_counter()
        # These should start in background threads
        print("DEBUG: calling f1")
        f1 = slow_cell("cell1", delay=0.5)
        print("DEBUG: calling f1 done")
        f2 = slow_cell("cell2", delay=0.5)
        print("DEBUG: calling f2 done")

        mid = time.perf_counter()
        print(f"DEBUG: end - start = {mid - start:.4f}s")
        # Wrapper should return almost balance immediately
        assert mid - start < 0.2

        # Accessing properties should wait
        assert f1.info["source"] == "cell1"
        assert f2.info["source"] == "cell2"

        # After being 'used' (e.g. via add_ref), it should be in the layout
        top.add_ref(f1)

        end = time.perf_counter()
        # Total time should be approx 0.5s, not 1.0s
        assert end - start < 0.8

        # Identity preservation in layout
        assert layout.cell(f1.name) is f1


def test_async_hierarchy() -> None:
    with gw.Layout() as _layout:
        # 1. Start two slow cells
        f1 = slow_cell("A", delay=0.2)
        f2 = slow_cell("B", delay=0.2)

        # 2. Pass them to a third cell (which is also async by default)
        # The hierarchical_cell function will be executed in a thread.
        # Inside that thread, it will call c.add_ref(f1), which will wait for f1.
        f3 = hierarchical_cell(f1, f2)

        # Access f3
        assert sum(1 for _ in f3.kdb.each_inst()) == 2

        # Verify names
        assert "slow_cell" in f1.name
        assert "slow_cell" in f2.name
        assert "hierarchical_cell" in f3.name


def test_async_error_propagation() -> None:
    gw.config.async_cells = True

    with gw.Layout():
        f = broken_cell()
        with pytest.raises(ValueError, match="Intentional error"):
            _ = f.name  # Trigger await


@pytest.fixture(autouse=True)
def skip_if_pypy() -> None:
    pass  # Placeholder for actual implementation if needed


if __name__ == "__main__":
    pytest.main([__file__])
