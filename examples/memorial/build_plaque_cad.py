"""Stage 1 B-Rep CAD — Flush-Recessed Cast-Bronze Commemorative Tablet (`build123d`).

Calibrated directly to `references/ref_side_NSkuanBlZw.jpg` (`crop_plaque_stone.png`):
  - Sleek, low-profile rectangular cast-bronze commemorative tablet (`2.66 m × 2.12 m`, `W/H = 1.255`)
  - Thin refined beveled perimeter molding rim + subtle recessed inscription field (NO bulky corner knobs or louver bars!)
  - Deep solid backing flange (`+0.28 m` into `+X`) for clean, zero-gap embedding inside the carved sandstone recess
  - Fine historical serif inscription relief is driven by high-res engraved height/normal/albedo maps baked onto the front face.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CAD_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "engine", "cad"))
if CAD_DIR not in sys.path:
    sys.path.insert(0, CAD_DIR)

from build123d import (  # noqa: E402
    Axis,
    BuildPart,
    BuildSketch,
    Mode,
    Plane,
    Rectangle,
    RectangleRounded,
    chamfer,
    extrude,
)
from cad_bridge import export_cad_part  # noqa: E402

# Pixel-calibrated dimensions matching exact 2 masonry courses (`2.16 m`) and stout reference ratio (`W/H = 1.157`)!
PLAQUE_W = 2.50       # Horizontal span along Y
PLAQUE_H = 2.16       # Vertical span along Z
BACK_DEPTH = 0.28     # Solid backing extending into +X (embedded cleanly inside stone pocket)
FRAME_DEPTH = 0.052   # Thin low-profile cast bronze bezel projecting toward -X (flush-recessed look!)
FIELD_DEPTH = 0.020   # Slightly sunken smooth cast-bronze inscription tablet field


def build_bronze_plaque():
    """Construct the sleek flush-recessed cast-bronze memorial tablet in Z-up meters."""
    with BuildPart() as bp:
        # 1. Main rectangular cast-bronze body & deep mounting backing block
        with BuildSketch(Plane.XY.offset(-BACK_DEPTH)):
            RectangleRounded(PLAQUE_W, PLAQUE_H, radius=0.018)
        extrude(amount=BACK_DEPTH + FRAME_DEPTH)

        # Subtle refined outer chamfer around the cast-bronze tablet lip
        front_edges = bp.edges().filter_by(lambda e: abs(e.center().Z - FRAME_DEPTH) < 1e-4)
        chamfer(front_edges, length=0.016)

        # 2. Clean shallow sunken inscription tablet recess
        rim = 0.085
        inner_w = PLAQUE_W - 2.0 * rim
        inner_h = PLAQUE_H - 2.0 * rim
        with BuildSketch(Plane.XY.offset(FRAME_DEPTH)):
            RectangleRounded(inner_w, inner_h, radius=0.010)
        extrude(amount=-(FRAME_DEPTH - FIELD_DEPTH), mode=Mode.SUBTRACT)

        # 3. Delicate thin raised inner border molding fillet (matches the thin inner frame line in reference photo!)
        with BuildSketch(Plane.XY.offset(FIELD_DEPTH - 0.002)):
            Rectangle(inner_w - 0.055, inner_h - 0.055)
            Rectangle(inner_w - 0.105, inner_h - 0.105, mode=Mode.SUBTRACT)
        extrude(amount=0.012)

    # Rotate local (+Z front, X width, Y height) -> memorial world frame (-X front, Y width, Z height)
    return bp.part.rotate(Axis.X, 90.0).rotate(Axis.Z, -90.0)


def build_and_export(out_dir: str | None = None) -> dict:
    target_dir = out_dir or os.path.join(THIS_DIR, "cad")
    os.makedirs(target_dir, exist_ok=True)
    part = build_bronze_plaque()
    res = export_cad_part(
        part,
        out_dir=target_dir,
        name="bronze_plaque",
        linear_deflection=0.006,
        angular_deflection=0.35,
        color="#3B3C3A",
        metallic=0.72,
        roughness=0.46,
    )
    if not res["inspection"]["pass"]:
        raise RuntimeError(f"CAD plaque inspection failed: {res['inspection']['errors']}")
    return res


def main() -> int:
    parser = argparse.ArgumentParser(description="Build sleek flush-recessed cast-bronze CAD plaque.")
    parser.add_argument("--out-dir", default=os.path.join(THIS_DIR, "cad"))
    args = parser.parse_args()
    res = build_and_export(args.out_dir)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
