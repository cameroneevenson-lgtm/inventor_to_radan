from __future__ import annotations

import os


def write_report(report_path: str,
                 bom_path: str,
                 out_path: str,
                 added_count: int,
                 expected_missing_dxfs: list[str],
                 orphan_dxfs: set[str],
                 missing_pdfs: set[str],
                 nonlaser_parts: list[str],
                 stock_cut_parts: list[str]) -> None:
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"BOM: {bom_path}\n")
        f.write(f"Folder: {os.path.dirname(bom_path)}\n")
        f.write(f"RADAN output: {out_path}\n")
        f.write("\n")
        f.write(f"Added to RADAN (rows): {added_count}\n")
        f.write("\n")

        f.write("Expected laser but missing DXF:\n")
        if expected_missing_dxfs:
            for name in expected_missing_dxfs:
                f.write(f"  {name}\n")
        else:
            f.write("  (none)\n")
        f.write("\n")

        f.write("Orphan DXFs (in folder but not referenced by BOM):\n")
        if orphan_dxfs:
            for name in sorted(orphan_dxfs):
                f.write(f"  {name}\n")
        else:
            f.write("  (none)\n")
        f.write("\n")

        f.write("DXFs missing PDFs:\n")
        if missing_pdfs:
            for base_name in sorted(missing_pdfs):
                f.write(f"  {base_name}.dxf (missing {base_name}.pdf)\n")
        else:
            f.write("  (none)\n")
        f.write("\n")

        f.write("Non-laser parts (no DXF; token-classified):\n")
        if nonlaser_parts:
            for p in nonlaser_parts:
                f.write(f"  {p}\n")
        else:
            f.write("  (none)\n")
        f.write("\n")

        f.write("Cut to length from stock (no DXF expected):\n")
        if stock_cut_parts:
            for p in stock_cut_parts:
                f.write(f"  {p}\n")
        else:
            f.write("  (none)\n")
        f.write("\n")
