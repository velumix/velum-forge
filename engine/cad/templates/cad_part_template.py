r"""Starter Velum Forge precision B-Rep CAD part: 250 mm Marine Stainless Deck Cleat.

Demonstrates exact engineering dimensions in meters, parametric fillets/chamfers,
countersunk mounting holes, Z=0 ground alignment, X/Y symmetry, and dual STEP + GLB export.

Usage:
    .\tools\cad\.venv\Scripts\python.exe tools\cad\templates\cad_part_template.py --out-dir .qa-out\cleat
"""

from __future__ import annotations

import argparse
import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CAD_DIR = os.path.dirname(THIS_DIR)
if CAD_DIR not in sys.path:
    sys.path.insert(0, CAD_DIR)

from build123d import (  # noqa: E402
    Align,
    Box,
    BuildPart,
    BuildSketch,
    Cylinder,
    Locations,
    Mode,
    Plane,
    RectangleRounded,
    chamfer,
    extrude,
    fillet,
)
from cad_bridge import export_cad_part  # noqa: E402


def build_marine_deck_cleat():
    """Build a 250 mm stainless steel Herreshoff-style marine dock/deck cleat (meters, Z>=0)."""
    base_len = 0.130
    base_wid = 0.056
    base_h = 0.010

    horn_len = 0.250
    horn_z = 0.060
    horn_h = 0.022
    horn_w = 0.024

    with BuildPart() as cleat:
        # 1. Mounting base plate resting cleanly at Z = 0
        with BuildSketch(Plane.XY):
            RectangleRounded(base_len, base_wid, radius=0.012)
        extrude(amount=base_h)

        top_edges = cleat.edges().filter_by(lambda e: abs(e.center().Z - base_h) < 1e-5)
        chamfer(top_edges, length=0.002)

        # 2. Two riser legs connecting base plate (Z=0.004 overlap) into horn (Z=horn_z)
        leg_x = 0.036
        for sign in (-1.0, 1.0):
            with BuildPart() as leg:
                with BuildSketch(Plane.XY.offset(0.004)):
                    with Locations((sign * leg_x, 0)):
                        RectangleRounded(0.022, 0.018, radius=0.005)
                extrude(amount=horn_z - 0.004)
            cleat.part = cleat.part + leg.part

        # 3. Sculpted horizontal horn bar (rounded profile with clean B-Rep fillets)
        with BuildPart() as horn:
            with BuildSketch(Plane.XY.offset(horn_z - horn_h * 0.5)):
                RectangleRounded(horn_len, horn_w, radius=horn_w * 0.45)
            extrude(amount=horn_h)
            # Clean underside overhang relief
            for sign in (-1.0, 1.0):
                with BuildSketch(Plane.XZ):
                    with Locations((sign * 0.100, horn_z - horn_h * 0.5 - 0.004)):
                        RectangleRounded(0.068, 0.018, radius=0.004)
                extrude(amount=horn_w * 0.75, both=True, mode=Mode.SUBTRACT)
            fillet(horn.edges(), radius=0.002)
        cleat.part = cleat.part + horn.part

        # 4. Smooth cast-metal junction fillets between legs and base plate
        base_join_edges = cleat.edges().filter_by(
            lambda e: abs(e.center().Z - base_h) < 0.002 and abs(e.center().X) < 0.052 and abs(e.center().Y) < 0.016
        )
        if base_join_edges:
            fillet(base_join_edges, radius=0.002)

        # 5. Four countersunk mounting bolt holes cleanly through base plate
        hole_locs = [
            (-0.048, -0.017),
            (-0.048, 0.017),
            (0.048, -0.017),
            (0.048, 0.017),
        ]
        with Locations([(x, y, base_h) for x, y in hole_locs]):
            Cylinder(
                radius=0.0032,
                height=base_h + 0.01,
                align=(Align.CENTER, Align.CENTER, Align.MAX),
                mode=Mode.SUBTRACT,
            )
            Cylinder(
                radius=0.0056,
                height=0.0035,
                align=(Align.CENTER, Align.CENTER, Align.MAX),
                mode=Mode.SUBTRACT,
            )

        # 6. Trim any tiny stray protrusion below Z=0 so grounding is exact
        with Locations((0, 0, -0.025)):
            Box(0.5, 0.5, 0.05, mode=Mode.SUBTRACT)

    return cleat.part


def main() -> int:
    parser = argparse.ArgumentParser(description="Build & export Velum Forge marine deck cleat CAD asset.")
    parser.add_argument("--out-dir", default=os.path.join(CAD_DIR, ".out"), help="Output directory")
    parser.add_argument("--name", default="marine_deck_cleat", help="Output base filename")
    args = parser.parse_args()

    part = build_marine_deck_cleat()
    result = export_cad_part(
        part,
        args.out_dir,
        args.name,
        linear_deflection=0.0015,
        angular_deflection=0.45,
        color=(0.76, 0.79, 0.82, 1.0),
        metallic=0.88,
        roughness=0.22,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

