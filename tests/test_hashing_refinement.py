# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import unittest.mock as mock
from pathlib import Path

import pytest

from gdswell.hashing import get_total_source_hash


def test_hashing_concatenation_collision():
    # Test that a.bc and ab.c result in different hashes
    root = Path("/tmp")

    def func_bc():
        pass

    def func_c():
        pass

    with (
        mock.patch("inspect.getmodule") as mock_getmodule,
        mock.patch("gdswell.hashing.get_module_dependencies") as mock_deps,
        mock.patch("gdswell.hashing._SOURCE_HASH_CACHE", {}),
    ):
        mock_deps.return_value = (set(), set())  # No files

        # Case 1: mod="a", func="bc"
        mod_a = mock.Mock()
        mod_a.__name__ = "a"
        mod_a.__file__ = "/tmp/a.py"
        mock_getmodule.return_value = mod_a
        func_bc.__name__ = "bc"
        hash1 = get_total_source_hash(func_bc, root)

        # Case 2: mod="ab", func="c"
        mod_ab = mock.Mock()
        mod_ab.__name__ = "ab"
        mod_ab.__file__ = "/tmp/ab.py"
        mock_getmodule.return_value = mod_ab
        func_c.__name__ = "c"
        # Clear cache for the function if it was cached
        # (it shouldn't be as it's a diff function object)
        hash2 = get_total_source_hash(func_c, root)

        assert hash1 != hash2, f"Hashes should differ for a:bc and ab:c. Got {hash1} for both"


def test_hashing_strict_validation():
    root = Path("/tmp")

    def anonymous_func():
        pass

    with (
        mock.patch("inspect.getmodule") as mock_getmodule,
        mock.patch("gdswell.hashing._SOURCE_HASH_CACHE", {}),
    ):
        mod = mock.Mock()
        mod.__file__ = "/tmp/mod.py"
        # Missing __name__
        del mod.__name__
        mock_getmodule.return_value = mod

        with pytest.raises(RuntimeError, match="Could not determine module or function name"):
            get_total_source_hash(anonymous_func, root)


if __name__ == "__main__":
    pytest.main([__file__])
