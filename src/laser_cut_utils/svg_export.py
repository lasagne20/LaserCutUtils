"""
svg_export.py — Export a FreeCAD Part shape projection to an SVG file.

Requires FreeCAD GUI (Draft, importSVG) to be available.
"""
from __future__ import annotations

import math
import os
import re

import FreeCAD
import FreeCADGui
import Draft
import importSVG
from PySide import QtGui

from .core import build_svg, wire_to_svg_path, Vec2


# ---------------------------------------------------------------------------
# Low-level shape → SVG path conversion (no GUI needed)
# ---------------------------------------------------------------------------

def _arc_path(edge, x0, y0, x1, y1) -> list[str]:
    """Return SVG arc command strings for a circular edge."""
    curve = edge.Curve
    r = curve.Radius
    cx = curve.Center.x
    cy = -curve.Center.y

    # Full circle → two half-arcs
    if abs(x0 - x1) < 1e-6 and abs(y0 - y1) < 1e-6:
        t_mid = (edge.FirstParameter + edge.LastParameter) / 2
        pm = edge.valueAt(t_mid)
        xm, ym = pm.x, -pm.y
        return [
            f"A {r:.4f} {r:.4f} 0 1 1 {xm:.4f} {ym:.4f}",
            f"A {r:.4f} {r:.4f} 0 1 1 {x1:.4f} {y1:.4f}",
        ]

    t_mid = (edge.FirstParameter + edge.LastParameter) / 2
    pm = edge.valueAt(t_mid)
    xm, ym = pm.x, -pm.y

    def ccw_span(start: float, end: float) -> float:
        return (end - start) % (2 * math.pi)

    a0 = math.atan2(y0 - cy, x0 - cx)
    am = math.atan2(ym - cy, xm - cx)
    a1 = math.atan2(y1 - cy, x1 - cx)
    span_end = ccw_span(a0, a1)
    span_mid = ccw_span(a0, am)
    is_ccw = span_mid < span_end
    sweep = 1 if is_ccw else 0
    arc_span = span_end if is_ccw else (2 * math.pi - span_end)
    large_arc = 1 if arc_span > math.pi else 0
    return [f"A {r:.4f} {r:.4f} 0 {large_arc} {sweep} {x1:.4f} {y1:.4f}"]


def _edge_to_d(edge, is_first: bool) -> list[str]:
    """Return SVG path command strings for a single FreeCAD edge."""
    v0 = edge.Vertexes[0]
    v1 = edge.Vertexes[-1]
    x0, y0 = v0.X, -v0.Y
    x1, y1 = v1.X, -v1.Y

    parts: list[str] = []
    if is_first:
        parts.append(f"M {x0:.4f} {y0:.4f}")

    ctype = type(edge.Curve).__name__
    if ctype == "Circle":
        parts.extend(_arc_path(edge, x0, y0, x1, y1))
    elif ctype in ("BSplineCurve", "BezierCurve", "OffsetCurve",
                   "BSplineSurface", "SurfaceOfRevolution", "Ellipse"):
        n = max(32, int(edge.Length / 0.5))
        pts = edge.discretize(n)
        for p in pts[1:]:
            parts.append(f"L {p.x:.4f} {-p.y:.4f}")
    else:
        parts.append(f"L {x1:.4f} {y1:.4f}")
    return parts


def shape_to_svg_paths(shape, fill: str = "none", stroke: str = "#000000",
                       stroke_width: float = 0.35) -> list[str]:
    """
    Convert a 2-D FreeCAD Shape to a list of SVG ``<path>`` strings.

    Each wire becomes one ``<path>`` element.
    """
    import Part as _Part

    wires = shape.Wires or []
    if not wires and shape.Edges:
        try:
            groups = _Part.sortEdges(shape.Edges)
            wires = [_Part.Wire(g) for g in groups]
        except Exception:
            wires = []

    paths: list[str] = []
    for wire in wires:
        d_parts: list[str] = []
        for i, edge in enumerate(wire.Edges):
            d_parts.extend(_edge_to_d(edge, is_first=(i == 0)))
        if wire.isClosed():
            d_parts.append("Z")
        d = " ".join(d_parts)
        paths.append(
            f'<path style="fill:{fill};stroke:{stroke};stroke-width:{stroke_width};'
            f'stroke-linecap:round;stroke-linejoin:round;" d="{d}"/>'
        )
    return paths


# ---------------------------------------------------------------------------
# High-level export
# ---------------------------------------------------------------------------

def export_projection_to_svg(obj, output_path: str, rotate: bool = False,
                              sketch_colors: dict | None = None) -> None:
    """
    Project *obj* along its largest face normal and write an SVG file.

    Args:
        obj:            FreeCAD Part/PartDesign object with a Shape.
        output_path:    Absolute path for the output ``.svg`` file.
        rotate:         If True, rotate the projection 90°.
        sketch_colors:  Mapping ``{sketch_obj: (R, G, B)}`` for coloured
                        sketch overlays.  Pass ``None`` for no overlays.
    """
    doc = FreeCAD.ActiveDocument
    sketch_colors = sketch_colors or {}

    if not hasattr(obj, "Shape") or obj.Shape.isNull():
        raise ValueError(f"Object {obj.Label!r} has no valid Shape.")

    # Determine projection normal (largest face)
    faces_sorted = sorted(obj.Shape.Faces, key=lambda f: f.Area, reverse=True)
    normal = faces_sorted[0].normalAt(0.5, 0.5)

    projection = Draft.makeShape2DView(obj, normal)
    doc.recompute()
    if rotate:
        Draft.rotate(projection, 90, FreeCAD.Vector(0, 0, 0))
        doc.recompute()

    export_objs = [projection]
    color_map: dict = {}

    for sketch, rgb in sketch_colors.items():
        body = (sketch.getParentGeoFeatureGroup()
                if hasattr(sketch, "getParentGeoFeatureGroup") else None)
        if sketch.TypeId == "Part::Part2DObjectPython":
            sk_proj = Draft.makeShape2DView(sketch, normal)
        else:
            global_shape = sketch.Shape.copy()
            if body and hasattr(body, "getGlobalPlacement"):
                global_shape.Placement = (
                    body.getGlobalPlacement().multiply(sketch.Shape.Placement)
                )
            import Part as _Part
            tmp = doc.addObject("Part::Feature", "_TmpSketchProj")
            tmp.Shape = global_shape
            doc.recompute()
            sk_proj = Draft.makeShape2DView(tmp, normal)
            doc.recompute()
            doc.removeObject(tmp.Name)
        doc.recompute()
        if rotate:
            Draft.rotate(sk_proj, 90, FreeCAD.Vector(0, 0, 0))
            doc.recompute()
        export_objs.append(sk_proj)
        color_map[sk_proj] = rgb

    # Compute viewBox from bounding box of all projected shapes
    import Part as _Part
    all_shapes = [o.Shape for o in export_objs
                  if hasattr(o, "Shape") and not o.Shape.isNull()]
    if all_shapes:
        combined = _Part.makeCompound(all_shapes)
        bb = combined.BoundBox
        margin = 5.0
        vb_x = bb.XMin - margin
        vb_y = -(bb.YMax + margin)
        vb_w = bb.XLength + 2 * margin
        vb_h = bb.YLength + 2 * margin
    else:
        vb_x, vb_y, vb_w, vb_h = 0.0, 0.0, 200.0, 200.0

    safe_label = re.sub(r"[^A-Za-z0-9_-]", "_", obj.Label)
    svg_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (f'<svg xmlns="http://www.w3.org/2000/svg" '
         f'viewBox="{vb_x:.4f} {vb_y:.4f} {vb_w:.4f} {vb_h:.4f}" '
         f'width="{vb_w:.2f}mm" height="{vb_h:.2f}mm">'),
        f'<g id="{safe_label}">',
    ]

    proj_shape = export_objs[0].Shape if hasattr(export_objs[0], "Shape") else None
    if proj_shape and not proj_shape.isNull():
        svg_parts.append(f'<g id="{safe_label}_projection">')
        svg_parts.extend(shape_to_svg_paths(proj_shape, fill="none",
                                            stroke="#000000", stroke_width=0.35))
        svg_parts.append("</g>")

    for sk_proj_obj, rgb in color_map.items():
        if not hasattr(sk_proj_obj, "Shape") or sk_proj_obj.Shape.isNull():
            continue
        hex_color = "#{:02x}{:02x}{:02x}".format(*rgb)
        sk_id = re.sub(r"[^A-Za-z0-9_-]", "_", sk_proj_obj.Label)
        svg_parts.append(
            f'<g id="{safe_label}_{sk_id}" fill="{hex_color}" stroke="{hex_color}">'
        )
        svg_parts.extend(
            shape_to_svg_paths(sk_proj_obj.Shape,
                               fill=hex_color, stroke=hex_color, stroke_width=0.2)
        )
        svg_parts.append("</g>")

    svg_parts += ["</g>", "</svg>"]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(svg_parts))

    # Store path on object
    if not hasattr(obj, "SVGPath"):
        obj.addProperty("App::PropertyString", "SVGPath", "Base",
                        "Path to exported SVG file")
    obj.SVGPath = output_path

    # Clean up temporary projection objects
    for o in export_objs:
        doc.removeObject(o.Name)
    doc.recompute()
