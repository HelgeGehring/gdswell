# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import contextlib

import klayout.db as kdb_


@contextlib.contextmanager
def _view_context(kdb_cell: kdb_.Cell):
    """Context manager to setup and teardown a klayout LayoutView for rendering."""
    import klayout.lay as lay

    view = lay.LayoutView()
    try:
        view.set_config("background-color", "#ffffff")
        # Use a duplicate of the layout for the view to avoid the view
        # destroying the original layout when it is destroyed.
        view.show_layout(kdb_cell.layout().dup(), False)
        view.add_missing_layers()
        view.max_hier()
        view.active_cellview().set_cell_name(kdb_cell.name)
        view.zoom_fit()
        yield view
    finally:
        view.destroy()


def export_image(kdb_cell: kdb_.Cell, filename: str, width: int = 800, height: int = 600) -> None:
    """
    Export a klayout cell to a PNG image.

    Args:
        kdb_cell: The klayout.db.Cell to export.
        filename: The name of the file to save the image to (should end in .png).
        width: The width of the image in pixels.
        height: The height of the image in pixels.
    """
    with _view_context(kdb_cell) as view:
        view.save_image(filename, width, height)


def get_image_bytes(kdb_cell: kdb_.Cell, width: int = 800, height: int = 600) -> bytes:
    """
    Return the PNG image bytes for a klayout cell.

    Args:
        kdb_cell: The klayout.db.Cell to export.
        width: The width of the image in pixels.
        height: The height of the image in pixels.

    Returns:
        The PNG data bytes.
    """
    with _view_context(kdb_cell) as view:
        pixel_buffer = view.get_pixels_with_options(width, height, 1, 1, 1.0, kdb_.DBox())
        return pixel_buffer.to_png_data()
