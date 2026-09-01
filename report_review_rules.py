"""The review gate's rules, shared by both report-review dialogs.

truck_nest_explorer's Qt dialog (dialogs/inventor_report_review_dialog.py
there) and this repo's Tk dialog (dialogs/report_review_dialog.py) show the
same report and must gate it identically. The toolkits cannot share widget
code, so the rules live here instead: which section is red/yellow/green,
which lines need their own checkbox, and what the banner counts. Stdlib
only, and listed in inline_runner.INLINE_IMPORT_NAMES so inline runs from
truck_nest_explorer clean it out of sys.modules like its siblings.
"""

from __future__ import annotations

# Non-laser and stock-cut are green, not yellow: every line in them matched
# a token or family the operator already classified, so they confirm a rule
# rather than ask for a decision. Green never produces a checkbox. One BOM
# put 18 non-laser parts in front of the two lines that mattered, which is
# the click-through fatigue that made the old single blanket checkbox
# worthless in the first place.
REVIEW_SECTION_LEVELS = {
    "Expected laser but missing DXF": "red",
    # A verification run cannot resolve these itself; somebody with the
    # RADAN vocabulary has to add the rule before the parts can be nested.
    "New descriptions": "yellow",
    "Orphan DXFs": "yellow",
    "DXFs missing PDFs": "yellow",
    "Non-laser parts": "green",
    "Cut to length from stock": "green",
}

COLORS = {
    "base": "#111827",
    "muted": "#475569",
    "green": "#15803D",
    "yellow": "#A16207",
    "red": "#B91C1C",
}


def warning_lines(report_text: str) -> list[tuple[str, str]]:
    """(level, line) for every red/yellow item in the report - the
    individual things that need their own checkbox, not the section
    header above them or a "(none)" that has nothing to acknowledge."""
    active_level = ""
    lines: list[tuple[str, str]] = []
    for line in report_text.splitlines():
        stripped = line.strip()
        if stripped.endswith(":"):
            active_level = ""
            for section, level in REVIEW_SECTION_LEVELS.items():
                if stripped.startswith(section):
                    active_level = level
                    break
            continue
        if not stripped or stripped == "(none)":
            continue
        if active_level in ("red", "yellow"):
            lines.append((active_level, stripped))
    return lines


def warning_counts(report_text: str) -> tuple[int, int]:
    """(critical, review) - red and yellow line counts. Banners read these
    so they can never disagree with the checkboxes warning_lines grows."""
    lines = warning_lines(report_text)
    critical_count = sum(1 for level, _ in lines if level == "red")
    review_count = sum(1 for level, _ in lines if level == "yellow")
    return critical_count, review_count
