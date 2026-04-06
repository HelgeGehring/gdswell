# Copyright 2026 Helge Gehring, Simon Bilodeau and contributors.
# Licensed under the Apache License, Version 2.0.
import os
from enum import Enum

import gdswell as gw
from gdswell.components.straight import straight


def test_image_export() -> None:
    class LayerEnum(gw.Layer, Enum):
        WG = (1, 0)

    layer = LayerEnum.WG
    ls = gw.LayerSection(name="core", layer=layer, width=0.5)
    xs = gw.CrossSection(layer_sections=(ls,))

    c = straight(cross_section=xs, length=10.0)

    # Create a parent cell with an instance of the straight
    parent = gw.Cell()
    parent.add_ref(c, origin=(0, 0))
    parent.add_ref(c, origin=(0, 5))

    output_png = "test_hierarchical.png"
    if os.path.exists(output_png):
        os.remove(output_png)

    print(f"Exporting to {output_png}...")
    parent.to_image(output_png, width=400, height=300)

    if not (os.path.exists(output_png) and os.path.getsize(output_png) > 0):
        raise RuntimeError(f"Failure: Image '{output_png}' was not created or is empty.")
