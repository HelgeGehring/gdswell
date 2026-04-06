# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import importlib.util
import sys
from pathlib import Path

import pytest

import gdswell as gw


def test_source_invalidation(tmp_path: Path) -> None:
    # Setup cache
    test_cache_dir = tmp_path / "cache"
    gw.config.cache_dir = test_cache_dir
    gw.config.use_disk_cache = True
    gw.clear_cache()

    # Define a component in a temporary file to simulate source changes
    temp_module_path = tmp_path / "my_temp_module.py"

    def write_module(width: float) -> None:
        with open(temp_module_path, "w") as f:
            f.write(f"""
import gdswell as gw
@gw.cell
def my_component():
    c = gw.Cell()
    c.add_polygon([(0, 0), ({width}, 0), ({width}, 1), (0, 1)], layer=gw.Layer(1, 0))
    return c
""")

    # 1. First version
    write_module(10.0)

    # Import the module dynamically
    spec = importlib.util.spec_from_file_location("my_temp_module", str(temp_module_path))
    assert spec is not None
    assert spec.loader is not None
    my_temp_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(my_temp_module)

    with gw.Layout():
        c1 = my_temp_module.my_component()
        name1 = c1.name
        assert (test_cache_dir / f"{name1}.oas").exists()

    # 2. Second version (source changed)
    write_module(20.0)

    # Reload the module
    if "my_temp_module" in sys.modules:
        del sys.modules["my_temp_module"]

    # We need to re-create the spec and module because the source changed
    spec = importlib.util.spec_from_file_location("my_temp_module", str(temp_module_path))
    assert spec is not None
    assert spec.loader is not None
    my_temp_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(my_temp_module)

    with gw.Layout():
        c2 = my_temp_module.my_component()
        name2 = c2.name

        # The name should be different because the source hash changed
        assert name1 != name2
        assert (test_cache_dir / f"{name2}.oas").exists()


def test_dependency_invalidation(tmp_path: Path) -> None:
    # Setup cache
    test_cache_dir = tmp_path / "cache"
    gw.config.cache_dir = test_cache_dir
    gw.config.use_disk_cache = True
    gw.clear_cache()

    dep_path = tmp_path / "my_dep.py"
    main_path = tmp_path / "my_main.py"

    def write_files(dep_val: float) -> None:
        with open(dep_path, "w") as f:
            f.write(f"VAL = {dep_val}\n")
        with open(main_path, "w") as f:
            f.write("""
import gdswell as gw
import my_dep
@gw.cell
def main_comp():
    c = gw.Cell()
    # Use the dependency
    c.add_polygon([(0, 0), (my_dep.VAL, 0), (my_dep.VAL, 1), (0, 1)], layer=gw.Layer(1, 0))
    return c
""")

    # 1. First version
    write_files(5.0)

    # Add tmp_path to sys.path so we can import these
    sys.path.insert(0, str(tmp_path))
    try:
        import my_main  # ty: ignore[unresolved-import]

        with gw.Layout():
            c1 = my_main.main_comp()
            name1 = c1.name

        # 2. Update dependency ONLY
        write_files(15.0)

        # Reload modules
        if "my_main" in sys.modules:
            del sys.modules["my_main"]
        if "my_dep" in sys.modules:
            del sys.modules["my_dep"]

        import my_main  # ty: ignore[unresolved-import]

        with gw.Layout():
            c2 = my_main.main_comp()
            name2 = c2.name

            # The name should be different because the dependency file changed
            assert name1 != name2
    finally:
        sys.path.pop(0)


if __name__ == "__main__":
    pytest.main([__file__])
