# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import importlib.util
import sys
from pathlib import Path

import pytest

import gdswell as gw


def test_module_ambiguity(tmp_path: Path) -> None:
    # Setup
    gw.config.use_disk_cache = False
    gw.clear_cache()

    # Define two modules with IDENTICAL function content but DIFFERENT module names
    mod1_path = tmp_path / "mod1.py"
    mod2_path = tmp_path / "mod2.py"

    content = """
import gdswell as gw
@gw.cell
def my_rect(w: float, h: float):
    c = gw.Cell()
    c.add_polygon([(0, 0), (w, 0), (w, h), (0, h)], layer=gw.Layer(1, 0))
    return c
"""
    mod1_path.write_text(content)
    mod2_path.write_text(content)

    # Import them
    def import_mod(name, path):
        spec = importlib.util.spec_from_file_location(name, str(path))
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    m1 = import_mod("mod1", mod1_path)
    m2 = import_mod("mod2", mod2_path)

    try:
        with gw.Layout():
            c1 = m1.my_rect(10.0, 20.0)
            c2 = m2.my_rect(10.0, 20.0)

            # Their names SHOULD be different because they are in different modules
            # even though their code and parameters are identical.
            assert c1.name != c2.name

            # The name format is {func_name}_{param_hash}_{source_hash}
            # The source_hash should be different.
            hash1 = c1.name.split("_")[-1]
            hash2 = c2.name.split("_")[-1]
            assert hash1 != hash2, f"Source hashes should differ: {hash1} vs {hash2}"
    finally:
        # Cleanup
        if "mod1" in sys.modules:
            del sys.modules["mod1"]
        if "mod2" in sys.modules:
            del sys.modules["mod2"]


if __name__ == "__main__":
    pytest.main([__file__])
