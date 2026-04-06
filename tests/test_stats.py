# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import time
from pathlib import Path

import pytest

import gdswell as gw


@gw.cell
def stats_component(w: float = 10.0) -> gw.Cell:
    time.sleep(0.01)  # Ensure measurable build time
    c = gw.Cell()
    c.add_polygon([(0, 0), (w, 0), (w, 1), (0, 1)], layer=gw.Layer(1, 0))
    return c


def test_telemetry_recording(tmp_path: Path) -> None:
    gw.config.cache_dir = tmp_path / "cache"
    gw.config.use_disk_cache = True
    gw.config.async_cells = False
    gw.reset_stats()
    gw.clear_cache()

    # 1. First call: Miss (Build)
    with gw.Layout():
        stats_component(w=20.0)

        s = gw.get_stats()["stats_component"]
        assert s.calls == 1
        assert s.hits_memory == 0
        assert s.hits_disk == 0
        assert s.compiles == 1
        assert len(s.build_times) == 1
        assert s.build_times[0] >= 0.01
        assert s.min_build_time >= 0.01
        assert s.max_build_time == s.min_build_time

        # 2. Second call (same layout): Memory Hit
        stats_component(w=20.0)

        s = gw.get_stats()["stats_component"]
        assert s.calls == 2
        assert s.hits_memory == 1
        assert s.hits_disk == 0
        assert s.compiles == 1  # Still 1 build

    # 3. Third call (new layout): Disk Hit
    with gw.Layout():
        stats_component(w=20.0)

    s = gw.get_stats()["stats_component"]
    assert s.calls == 3
    assert s.hits_memory == 1
    assert s.hits_disk == 1
    assert s.compiles == 1

    # 4. Fourth call (new parameters): New Build
    with gw.Layout():
        stats_component(w=30.0)

    s = gw.get_stats()["stats_component"]
    assert s.calls == 4
    assert s.hits_memory == 1
    assert s.hits_disk == 1
    assert s.compiles == 2
    assert s.total_time == sum(s.build_times)

    # Verify print_stats doesn't crash
    gw.print_stats()


if __name__ == "__main__":
    pytest.main([__file__])
