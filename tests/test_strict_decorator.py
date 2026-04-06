# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import pytest

from gdswell.cell import Cell
from gdswell.decorator import cell


def test_nested_cell_fails_even_in_test():
    """Verify that nested cells are now forbidden even in test modules."""

    def outer():
        @cell
        def nested_cell():
            c = Cell()
            return c

    with pytest.raises(RuntimeError, match="must be defined at the module level"):
        outer()


def test_class_method_cell_fails_even_in_test():
    """Verify that class methods are now forbidden even in test modules."""
    with pytest.raises(RuntimeError, match="must be defined at the module level"):

        class MyComponent:
            @cell
            def method_cell(self):
                """This is defined at 'class' level, so qualname is MyComponent.method_cell."""
                return Cell()


def test_verify_enforcement_at_definition():
    with pytest.raises(RuntimeError, match="must be defined at the module level"):

        @cell
        def really_nested():
            return Cell()


if __name__ == "__main__":
    pytest.main([__file__])
