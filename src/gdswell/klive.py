# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
from __future__ import annotations

import json
import os
import socket
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import klayout.db as kdb


def show(kdb_cell: kdb.Cell) -> None:
    """
    Stream a specific cell to Klive for live viewing in KLayout.

    Args:
        kdb_cell: The klayout.db.Cell to show.
    """

    kdb_layout = kdb_cell.layout()
    cell_name = kdb_cell.name

    # Save to temp file
    fd, path = tempfile.mkstemp(suffix=".gds")
    os.close(fd)
    try:
        kdb_layout.write(path)

        data = {"gds": os.path.abspath(path)}
        if cell_name is not None:
            data["top_cell"] = cell_name

        with socket.create_connection(("localhost", 8082), timeout=0.5) as sock:
            msg = json.dumps(data) + "\n"
            sock.sendall(msg.encode())

    except (ConnectionRefusedError, socket.timeout):
        print(
            "Could not connect to Klive on localhost:8082. "
            "Is KLayout running with the Klive plugin?"
        )
    except Exception as e:
        print(f"Error streaming to Klive: {e}")
