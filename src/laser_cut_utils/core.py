"""
core.py — Pure-Python geometry helpers for tab-and-slot generation.

No FreeCAD imports here: all functions work on plain (x, y) tuples so they
can be unit-tested without a FreeCAD installation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Basic 2-D vector helpers
# ---------------------------------------------------------------------------

class Vec2(NamedTuple):
    x: float
    y: float

    def __add__(self, other: "Vec2") -> "Vec2":  # type: ignore[override]
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":  # type: ignore[override]
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vec2":  # type: ignore[override]
        return Vec2(self.x * scalar, self.y * scalar)

    def __rmul__(self, scalar: float) -> "Vec2":
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> "Vec2":
        return Vec2(self.x / scalar, self.y / scalar)

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalize(self) -> "Vec2":
        n = self.length()
        if n < 1e-9:
            raise ValueError("Cannot normalize a zero-length vector.")
        return Vec2(self.x / n, self.y / n)

    def perpendicular(self) -> "Vec2":
        """Returns the 90° CCW perpendicular."""
        return Vec2(-self.y, self.x)

    def dot(self, other: "Vec2") -> float:
        return self.x * other.x + self.y * other.y


# ---------------------------------------------------------------------------
# Tab layout
# ---------------------------------------------------------------------------

@dataclass
class TabParams:
    """Parameters driving tab-and-slot generation."""
    tab_width: float        # width of each tab (mm)
    tab_height: float       # height (= material thickness, mm)
    tab_spacing: float      # gap between consecutive tabs (mm)
    hole_clearance: float   # clearance applied to slot width (mm)
    use_variables: bool = False


@dataclass
class TabRect:
    """One tab rectangle described by its four corners in sketch-local 2-D."""
    corners: list[Vec2] = field(default_factory=list)   # [p1, p2, p3, p4] CCW
    center: Vec2 = Vec2(0.0, 0.0)

    @classmethod
    def from_center(cls, center: Vec2, half_w: float, half_h: float,
                    dir_vec: Vec2, perp_vec: Vec2) -> "TabRect":
        p1 = center - dir_vec * half_w - perp_vec * half_h
        p2 = center + dir_vec * half_w - perp_vec * half_h
        p3 = center + dir_vec * half_w + perp_vec * half_h
        p4 = center - dir_vec * half_w + perp_vec * half_h
        return cls(corners=[p1, p2, p3, p4], center=center)


def compute_tab_count(edge_length: float, tab_width: float, tab_spacing: float) -> int:
    """
    Return the number of tabs that fit along *edge_length*.

    Uses round() to pick the nearest integer, same logic as the original code.
    """
    if tab_width + tab_spacing <= 0:
        raise ValueError("tab_width + tab_spacing must be > 0.")
    return max(1, round(edge_length / (tab_spacing + tab_width)))


def compute_tab_offset(edge_length: float, num_tabs: int,
                       tab_width: float, tab_spacing: float) -> float:
    """
    Return the leading margin so that *num_tabs* tabs are centred on the edge.
    """
    total = num_tabs * tab_width + (num_tabs - 1) * tab_spacing
    return (edge_length - total) / 2.0


def compute_tab_centers(p1: Vec2, p2: Vec2, params: TabParams) -> list[Vec2]:
    """
    Return the 2-D centre of each tab along the edge [p1 → p2].

    Args:
        p1: Start point of the edge in sketch-local coordinates.
        p2: End point of the edge in sketch-local coordinates.
        params: Tab parameters.

    Returns:
        List of Vec2 centres, one per tab.
    """
    length = (p2 - p1).length()
    n = compute_tab_count(length, params.tab_width, params.tab_spacing)
    offset = compute_tab_offset(length, n, params.tab_width, params.tab_spacing)
    dir_vec = (p2 - p1).normalize()

    centers: list[Vec2] = []
    for i in range(n):
        dist = offset + i * (params.tab_width + params.tab_spacing) + params.tab_width / 2.0
        centers.append(p1 + dir_vec * dist)
    return centers


def compute_hole_rect(tab_rect: TabRect, params: TabParams,
                      dir_vec: Vec2, horiz_is_width: bool) -> tuple[Vec2, float, float]:
    """
    Return (center, hole_width, hole_height) for the slot matching *tab_rect*.

    Clearance is applied on the dimension that corresponds to tab_width.
    """
    if horiz_is_width:
        hole_w = params.tab_width - params.hole_clearance
        hole_h = params.tab_height
    else:
        hole_w = params.tab_height
        hole_h = params.tab_width - params.hole_clearance
    return tab_rect.center, hole_w, hole_h


# ---------------------------------------------------------------------------
# SVG path helpers (geometry-only, no FreeCAD)
# ---------------------------------------------------------------------------

def rect_to_svg_path(x: float, y: float, w: float, h: float,
                     stroke: str = "#000000",
                     stroke_width: float = 0.35) -> str:
    """Return an SVG ``<rect>`` element for a laser-cut slot."""
    return (
        f'<rect x="{x:.4f}" y="{y:.4f}" width="{w:.4f}" height="{h:.4f}" '
        f'fill="none" stroke="{stroke}" stroke-width="{stroke_width}"/>'
    )


def wire_to_svg_path(points: list[Vec2],
                     closed: bool = True,
                     stroke: str = "#000000",
                     stroke_width: float = 0.35) -> str:
    """
    Convert a list of 2-D points to an SVG ``<path>`` element.

    The Y axis is flipped (SVG Y grows downward, FreeCAD Y grows upward).
    """
    if not points:
        return ""
    cmds = [f"M {points[0].x:.4f} {-points[0].y:.4f}"]
    for p in points[1:]:
        cmds.append(f"L {p.x:.4f} {-p.y:.4f}")
    if closed:
        cmds.append("Z")
    d = " ".join(cmds)
    return (
        f'<path fill="none" stroke="{stroke}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round" d="{d}"/>'
    )


def build_svg(paths: list[str], width_mm: float, height_mm: float,
              vb_x: float = 0.0, vb_y: float = 0.0) -> str:
    """Wrap SVG path strings in a minimal SVG document."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vb_x:.4f} {vb_y:.4f} {width_mm:.4f} {height_mm:.4f}" '
        f'width="{width_mm:.2f}mm" height="{height_mm:.2f}mm">',
        *paths,
        "</svg>",
    ]
    return "\n".join(lines)
