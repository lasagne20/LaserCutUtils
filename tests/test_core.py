"""
test_core.py — Unit tests for laser_cut_utils.core (pure Python, no FreeCAD).
"""
from __future__ import annotations

import math
import pytest

from laser_cut_utils.core import (
    Vec2,
    TabParams,
    TabRect,
    compute_tab_count,
    compute_tab_offset,
    compute_tab_centers,
    compute_hole_rect,
    wire_to_svg_path,
    build_svg,
)


# ---------------------------------------------------------------------------
# Vec2
# ---------------------------------------------------------------------------

class TestVec2:
    def test_add(self):
        assert Vec2(1, 2) + Vec2(3, 4) == Vec2(4, 6)

    def test_sub(self):
        assert Vec2(5, 3) - Vec2(2, 1) == Vec2(3, 2)

    def test_mul_scalar(self):
        assert Vec2(2, 3) * 2 == Vec2(4, 6)

    def test_rmul_scalar(self):
        assert 3 * Vec2(1, 2) == Vec2(3, 6)

    def test_div(self):
        assert Vec2(4, 6) / 2 == Vec2(2, 3)

    def test_length(self):
        assert math.isclose(Vec2(3, 4).length(), 5.0)

    def test_normalize(self):
        n = Vec2(3, 4).normalize()
        assert math.isclose(n.length(), 1.0)

    def test_normalize_zero_raises(self):
        with pytest.raises(ValueError):
            Vec2(0, 0).normalize()

    def test_perpendicular(self):
        p = Vec2(1, 0).perpendicular()
        assert p == Vec2(0, 1)
        # CCW rotation: (0,1) → (-1,0)
        assert Vec2(0, 1).perpendicular() == Vec2(-1, 0)

    def test_dot(self):
        assert Vec2(1, 0).dot(Vec2(0, 1)) == 0.0
        assert Vec2(1, 0).dot(Vec2(1, 0)) == 1.0


# ---------------------------------------------------------------------------
# compute_tab_count
# ---------------------------------------------------------------------------

class TestComputeTabCount:
    def test_basic(self):
        # 290 / (5 + 45) = 5.8 → round = 6
        assert compute_tab_count(290.0, 5.0, 45.0) == 6

    def test_exact(self):
        # 100 / (10 + 15) = 4.0 → 4
        assert compute_tab_count(100.0, 10.0, 15.0) == 4

    def test_minimum_one_tab(self):
        # Very short edge → at least 1 tab
        assert compute_tab_count(1.0, 10.0, 20.0) == 1

    def test_round_up(self):
        # 55 / (10 + 20) = 1.833 → round = 2
        assert compute_tab_count(55.0, 10.0, 20.0) == 2

    def test_zero_pitch_raises(self):
        with pytest.raises(ValueError):
            compute_tab_count(100.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# compute_tab_offset
# ---------------------------------------------------------------------------

class TestComputeTabOffset:
    def test_centred(self):
        # 4 tabs of 10mm with 15mm spacing on 100mm edge
        # total = 4*10 + 3*15 = 85 → offset = (100-85)/2 = 7.5
        assert math.isclose(compute_tab_offset(100.0, 4, 10.0, 15.0), 7.5)

    def test_zero_offset(self):
        # 2 tabs of 10mm, 0mm spacing on 20mm edge → offset = 0
        assert math.isclose(compute_tab_offset(20.0, 2, 10.0, 0.0), 0.0)

    def test_negative_offset_is_allowed(self):
        # edge shorter than total → negative offset (caller's problem)
        offset = compute_tab_offset(10.0, 5, 5.0, 5.0)
        assert offset < 0


# ---------------------------------------------------------------------------
# compute_tab_centers
# ---------------------------------------------------------------------------

class TestComputeTabCenters:
    def _params(self, **kw):
        defaults = dict(tab_width=10.0, tab_height=5.0,
                        tab_spacing=15.0, hole_clearance=0.6)
        defaults.update(kw)
        return TabParams(**defaults)

    def test_count_matches_compute_tab_count(self):
        p = self._params(tab_width=10.0, tab_spacing=15.0)
        centers = compute_tab_centers(Vec2(0, 0), Vec2(100, 0), p)
        assert len(centers) == compute_tab_count(100.0, 10.0, 15.0)

    def test_centers_on_edge_direction(self):
        p = self._params(tab_width=10.0, tab_spacing=15.0)
        centers = compute_tab_centers(Vec2(0, 0), Vec2(100, 0), p)
        # All centres should have y ≈ 0 (horizontal edge)
        for c in centers:
            assert math.isclose(c.y, 0.0, abs_tol=1e-9)

    def test_centers_symmetric(self):
        p = self._params(tab_width=10.0, tab_spacing=15.0)
        centers = compute_tab_centers(Vec2(0, 0), Vec2(100, 0), p)
        # First and last centre should be equidistant from the ends
        dist_first = centers[0].x
        dist_last  = 100.0 - centers[-1].x
        assert math.isclose(dist_first, dist_last, abs_tol=1e-9)

    def test_spacing_between_centers(self):
        p = self._params(tab_width=10.0, tab_spacing=15.0)
        centers = compute_tab_centers(Vec2(0, 0), Vec2(100, 0), p)
        if len(centers) >= 2:
            gap = (centers[1] - centers[0]).length()
            assert math.isclose(gap, p.tab_width + p.tab_spacing, abs_tol=1e-9)

    def test_vertical_edge(self):
        p = self._params(tab_width=10.0, tab_spacing=20.0)
        centers = compute_tab_centers(Vec2(0, 0), Vec2(0, 200), p)
        # All centres on x ≈ 0
        for c in centers:
            assert math.isclose(c.x, 0.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# compute_hole_rect
# ---------------------------------------------------------------------------

class TestComputeHoleRect:
    def _tab_rect(self):
        return TabRect(center=Vec2(50.0, 0.0), corners=[])

    def test_clearance_applied_on_width_when_horiz(self):
        p = TabParams(tab_width=10.0, tab_height=5.0,
                      tab_spacing=15.0, hole_clearance=0.6)
        tr = self._tab_rect()
        _, hw, hh = compute_hole_rect(tr, p, Vec2(1, 0), horiz_is_width=True)
        assert math.isclose(hw, 10.0 - 0.6)
        assert math.isclose(hh, 5.0)

    def test_clearance_applied_on_height_when_vert(self):
        p = TabParams(tab_width=10.0, tab_height=5.0,
                      tab_spacing=15.0, hole_clearance=0.6)
        tr = self._tab_rect()
        _, hw, hh = compute_hole_rect(tr, p, Vec2(0, 1), horiz_is_width=False)
        assert math.isclose(hw, 5.0)
        assert math.isclose(hh, 10.0 - 0.6)

    def test_center_preserved(self):
        p = TabParams(tab_width=10.0, tab_height=5.0,
                      tab_spacing=15.0, hole_clearance=0.0)
        tr = TabRect(center=Vec2(7.0, 3.0), corners=[])
        center, _, _ = compute_hole_rect(tr, p, Vec2(1, 0), horiz_is_width=True)
        assert center == Vec2(7.0, 3.0)


# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------

class TestWireToSvgPath:
    def test_open_wire(self):
        pts = [Vec2(0, 0), Vec2(10, 0), Vec2(10, 5)]
        svg = wire_to_svg_path(pts, closed=False)
        assert svg.startswith("<path")
        assert "Z" not in svg
        assert "M 0.0000 0.0000" in svg
        # Y is flipped
        assert "L 10.0000 0.0000" in svg

    def test_closed_wire(self):
        pts = [Vec2(0, 0), Vec2(10, 0), Vec2(10, 10), Vec2(0, 10)]
        svg = wire_to_svg_path(pts, closed=True)
        assert svg.endswith('"/>') or "Z" in svg

    def test_y_axis_flip(self):
        # A point at y=5 should become y=-5 in SVG output
        pts = [Vec2(0, 5), Vec2(10, 5)]
        svg = wire_to_svg_path(pts, closed=False)
        assert "-5.0000" in svg

    def test_empty_returns_empty_string(self):
        assert wire_to_svg_path([], closed=True) == ""


class TestBuildSvg:
    def test_contains_paths(self):
        paths = ['<path d="M 0 0 L 10 0 Z"/>']
        svg = build_svg(paths, width_mm=100.0, height_mm=50.0)
        assert "<svg" in svg
        assert "</svg>" in svg
        assert paths[0] in svg

    def test_dimensions_in_header(self):
        svg = build_svg([], width_mm=200.0, height_mm=100.0)
        assert "200.00mm" in svg
        assert "100.00mm" in svg

    def test_xml_declaration(self):
        svg = build_svg([], width_mm=10.0, height_mm=10.0)
        assert svg.startswith("<?xml")
