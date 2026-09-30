"""Run with KiCad's own Python interpreter, not the Argus virtual environment."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def refill(board_path: Path, output: Path, expected_version: str) -> None:
    import pcbnew

    actual_version = pcbnew.Version()
    if actual_version != expected_version:
        raise RuntimeError(f"pcbnew {actual_version} differs from kicad-cli {expected_version}")
    if not board_path.with_suffix(".kicad_pro").is_file():
        raise RuntimeError("refill needs the adjacent copied project settings")
    board = pcbnew.LoadBoard(str(board_path))
    if board is None or board.GetProject() is None:
        raise RuntimeError("KiCad could not load the copied board and project")
    zones = list(board.Zones())
    if not zones:
        raise RuntimeError("no copper zones available for refill")
    # LoadBoard suppresses custom-rule parse errors. Reinitialize them explicitly.
    if board_path.with_suffix(".kicad_dru").exists():
        if not pcbnew.WriteDRCReport(board, str(output / "refill-rules.rpt"), pcbnew.EDA_UNITS_MM, True):
            raise RuntimeError("KiCad could not initialize the original custom rules")
    for zone in zones:
        zone.UnFill()
    unfilled = output / "refill-unfilled.kicad_pcb"
    if not pcbnew.SaveBoard(str(unfilled), board, True):
        raise RuntimeError("KiCad could not serialize the unfilled board")
    before = unfilled.read_bytes()
    if not board.BuildConnectivity() or not pcbnew.ZONE_FILLER(board).Fill(board.Zones()):
        raise RuntimeError("native copper zone refill failed")
    measurements = []
    for zone in zones:
        area = zone.CalculateFilledArea() / pcbnew.FromMM(1)**2
        if not math.isfinite(area) or area < 0:
            raise RuntimeError("native zone area is not finite and nonnegative")
        measurements.append({
            "id": zone.m_Uuid.AsString(), "name": zone.GetZoneName(),
            "layer": board.GetLayerName(zone.GetLayer()), "net": zone.GetNetname(),
            "filled_area_mm2": area,
        })
    if not pcbnew.SaveBoard(str(board_path), board, True):
        raise RuntimeError("KiCad could not save the refilled working board")
    for zone in zones:
        zone.UnFill()
    if not pcbnew.SaveBoard(str(unfilled), board, True) or unfilled.read_bytes() != before:
        raise RuntimeError("native refill changed the design outside stored fill geometry")
    report = {
        "operation": "pcbnew.ZONE_FILLER", "kicad_version": actual_version,
        "board": board_path.as_posix(), "old_fills_discarded": True,
        "non_fill_design_unchanged": True,
        "zones": sorted(measurements, key=lambda row: row["id"]),
    }
    (output / "refill.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    refill(args.board, args.output, args.expected_version)


if __name__ == "__main__":
    main()
