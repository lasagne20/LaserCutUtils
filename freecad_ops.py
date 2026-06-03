"""
freecad_ops.py — FreeCAD-specific operations for tab-and-slot generation.

Requires a running FreeCAD environment (FreeCAD, Part, Sketcher, PartDesign).
"""
from __future__ import annotations

import FreeCAD
import Part
import Sketcher
from FreeCAD import Vector

from core import TabParams, Vec2, compute_tab_centers, compute_tab_count, compute_tab_offset


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def global_to_sketch_xy(sketch, p_global: Vector) -> Vector:
    """Convert a global FreeCAD Vector to sketch-local 2-D coordinates."""
    try:
        gpl = sketch.getGlobalPlacement()
    except AttributeError:
        gpl = sketch.Shape.Placement
    p_local = gpl.inverse().multVec(p_global)
    return Vector(p_local.x, p_local.y, 0.0)


# ---------------------------------------------------------------------------
# Opposite-face detection
# ---------------------------------------------------------------------------

def find_opposite_face(obj, face, body, tol: float = 0.5):
    """
    Find the face on an adjacent body that is directly opposite to *face*.

    Returns (opposite_obj, opposite_face) or (None, None) if nothing is found.
    The two bodies must share the same parent assembly.
    """
    global_face_center = body.getGlobalPlacement().multVec(face.CenterOfMass)
    global_normal = body.getGlobalPlacement().Rotation.multVec(face.normalAt(0, 0))

    test_offset = 0.1
    test_pt  = global_face_center + global_normal * test_offset
    test_pt2 = global_face_center - global_normal * test_offset

    candidate_objs = []
    for cand in FreeCAD.ActiveDocument.Objects:
        if not hasattr(cand, "Shape") or cand is obj:
            continue
        body_cand = (cand.getParentGeoFeatureGroup()
                     if hasattr(cand, "getParentGeoFeatureGroup") else None)
        if (body_cand is None
                or body_cand.TypeId != "PartDesign::Body"
                or body_cand is body):
            continue
        if body.getParentGeoFeatureGroup() != body_cand.getParentGeoFeatureGroup():
            continue

        _skip_prefixes = (
            "Sketcher::", "PartDesign::Datum", "PartDesign::CoordinateSystem",
            "PartDesign::Plane", "PartDesign::Line", "PartDesign::Point",
            "PartDesign::Axis", "App::Plane", "App::Line", "App::Link",
        )
        if any(cand.TypeId.startswith(p) for p in _skip_prefixes):
            continue
        if cand.Shape is None or cand.Shape.isNull():
            continue

        try:
            if hasattr(cand, "ViewObject") and cand.ViewObject:
                if not cand.ViewObject.Visibility:
                    continue
        except Exception:
            pass

        try:
            bbox = cand.Shape.BoundBox
            gp = body_cand.getGlobalPlacement()
            gb = FreeCAD.BoundBox()
            for xi in (bbox.XMin, bbox.XMax):
                for yi in (bbox.YMin, bbox.YMax):
                    for zi in (bbox.ZMin, bbox.ZMax):
                        gb.add(gp.multVec(Vector(xi, yi, zi)))

            inside1 = (gb.XMin <= test_pt.x <= gb.XMax and
                       gb.YMin <= test_pt.y <= gb.YMax and
                       gb.ZMin <= test_pt.z <= gb.ZMax)
            inside2 = (gb.XMin <= test_pt2.x <= gb.XMax and
                       gb.YMin <= test_pt2.y <= gb.YMax and
                       gb.ZMin <= test_pt2.z <= gb.ZMax)
            if inside1 or inside2:
                candidate_objs.append(cand)
        except Exception:
            continue

    if not candidate_objs:
        return None, None

    all_faces = [(c, f) for c in candidate_objs for f in c.Shape.Faces]
    top2 = sorted(all_faces, key=lambda x: x[1].Area, reverse=True)[:2]
    best = min(top2, key=lambda x: x[1].distToShape(face)[0])
    return best


# ---------------------------------------------------------------------------
# VarSet helpers
# ---------------------------------------------------------------------------

def add_or_update_var(varset, name: str, value: float) -> str:
    """
    Add a length property to *varset*, renaming if one with that name already exists.

    Returns the expression string ``"VarSetName.PropertyName"``.
    """
    if hasattr(varset, name):
        idx = 1
        new_name = f"{name}_{idx}"
        while hasattr(varset, new_name):
            idx += 1
            new_name = f"{name}_{idx}"
        varset.addProperty("App::PropertyLength", new_name,
                           f"Tabs_{idx}", f"{name} (index {idx})")
        setattr(varset, new_name, f"{value}mm")
        return f"{varset.Name}.{new_name}"
    else:
        varset.addProperty("App::PropertyLength", name, "Tabs", f"{name} parameter")
        setattr(varset, name, f"{value}mm")
        return f"{varset.Name}.{name}"


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------

def _edges_are_equal(e1, e2, tol: float = 1e-6) -> bool:
    v = e1.Vertexes
    w = e2.Vertexes
    return (
        (v[0].Point.distanceToPoint(w[0].Point) < tol and
         v[1].Point.distanceToPoint(w[1].Point) < tol) or
        (v[0].Point.distanceToPoint(w[1].Point) < tol and
         v[1].Point.distanceToPoint(w[0].Point) < tol)
    )


def generate_tabs_and_holes(obj, face, body, face_name: str | None = None,
                             tab_width: float = 10.0, tab_height: float = 5.0,
                             tab_spacing: float = 20.0, tab_hole_clearance: float = 0.6,
                             use_variables: bool = False):
    """
    Generate tabs on *face* and matching slots on the opposite face.

    Args:
        obj:               FreeCAD feature containing the selected face.
        face:              The face on which to generate tabs.
        body:              PartDesign Body that owns *obj*.
        face_name:         Face name string (e.g. ``"Face6"``), optional.
        tab_width:         Width of each tab in mm.
        tab_height:        Height of each tab (= material thickness) in mm.
        tab_spacing:       Gap between consecutive tabs in mm.
        tab_hole_clearance: Clearance applied to slot width in mm.
        use_variables:     Store parameters in a VarSet for parametric editing.

    Returns:
        ``(pad, pocket)`` on success, ``(None, None)`` on failure.
    """
    params = TabParams(
        tab_width=tab_width,
        tab_height=tab_height,
        tab_spacing=tab_spacing,
        hole_clearance=tab_hole_clearance,
        use_variables=use_variables,
    )

    other_obj, other_face = find_opposite_face(obj, face, body)
    if other_obj is None:
        FreeCAD.Console.PrintError("Cannot find the opposite face in the same assembly.\n")
        return None, None

    other_body = other_obj.getParentGeoFeatureGroup()
    FreeCAD.Console.PrintMessage(
        f"Opposite face found in: {other_body.Label} / {other_obj.Label}\n"
    )

    doc = FreeCAD.ActiveDocument
    doc.openTransaction("Generate Tabs")

    try:
        width_var = height_var = spacing_var = clearance_var = None
        if use_variables:
            varset = body.newObject("App::VarSet", "TabsParameters")
            width_var    = add_or_update_var(varset, "Width",         tab_width)
            height_var   = add_or_update_var(varset, "Height",        tab_height)
            spacing_var  = add_or_update_var(varset, "Spacing",       tab_spacing)
            clearance_var = add_or_update_var(varset, "HoleClearance", tab_hole_clearance)

        sketch = body.newObject("Sketcher::SketchObject", "TabSketch")
        if face_name:
            sketch.AttachmentSupport = (obj, [face_name])
        else:
            for idx, f in enumerate(obj.Shape.Faces):
                if (f.CenterOfMass.sub(face.CenterOfMass).Length < 1e-6 and
                        f.normalAt(0, 0).sub(face.normalAt(0, 0)).Length < 1e-6):
                    sketch.AttachmentSupport = (obj, [f"Face{idx + 1}"])
                    break
        sketch.MapMode = "FlatFace"
        body.recompute()

        edges_sorted = sorted(face.Edges, key=lambda e: e.Length, reverse=True)
        ref1, ref2 = edges_sorted[0], edges_sorted[1]

        external_added = False
        for ref in (ref1, ref2):
            for i, obj_edge in enumerate(obj.Shape.Edges):
                if _edges_are_equal(obj_edge, ref):
                    sketch.addExternal(obj.Name, f"Edge{i + 1}")
                    body.recompute()
                    external_added = True
                    break

        if not external_added:
            FreeCAD.Console.PrintError("No external edges could be added to the sketch.\n")
            doc.abortTransaction()
            return None, None

        body.recompute()

        try:
            p1 = sketch.getPoint(-3, 1)
            p2 = sketch.getPoint(-3, 2)
            if (p1 - p2).Length < 1e-3:
                p1 = sketch.getPoint(-4, 1)
                p2 = sketch.getPoint(-4, 2)
        except Exception:
            edge = ref1
            p1 = global_to_sketch_xy(sketch, edge.Vertexes[0].Point)
            p2 = global_to_sketch_xy(sketch, edge.Vertexes[-1].Point)
            if (p1 - p2).Length < 1e-3:
                edge = ref2
                p1 = global_to_sketch_xy(sketch, edge.Vertexes[0].Point)
                p2 = global_to_sketch_xy(sketch, edge.Vertexes[-1].Point)

        geom_pt1 = sketch.getPoint(-3, 1)
        geom_pt2 = sketch.getPoint(-3, 2)
        p1_is_point1 = (geom_pt1 - p1).Length < (geom_pt2 - p1).Length

        p1_2d = Vec2(p1.x, p1.y)
        p2_2d = Vec2(p2.x, p2.y)
        tab_centers_2d = compute_tab_centers(p1_2d, p2_2d, params)
        num_tabs = len(tab_centers_2d)

        length = (p2_2d - p1_2d).length()
        dir_vec_2d = (p2_2d - p1_2d).normalize()
        perp_vec_2d = dir_vec_2d.perpendicular()

        dir_vec = Vector(dir_vec_2d.x, dir_vec_2d.y, 0)
        perp_vec = Vector(perp_vec_2d.x, perp_vec_2d.y, 0)

        l1_direction_positive = None
        edge_start_point = None

        for n in range(num_tabs):
            tc = tab_centers_2d[n]
            tab_center = Vector(tc.x, tc.y, 0)
            offset_v = tab_center - perp_vec * tab_height - dir_vec * (tab_width / 2)

            p1t = offset_v
            p2t = offset_v + dir_vec * tab_width
            p3t = p2t + perp_vec * tab_height
            p4t = p3t - dir_vec * tab_width

            l1 = sketch.addGeometry(Part.LineSegment(p1t, p2t), False)
            l2 = sketch.addGeometry(Part.LineSegment(p2t, p3t), False)
            l3 = sketch.addGeometry(Part.LineSegment(p3t, p4t), False)
            l4 = sketch.addGeometry(Part.LineSegment(p4t, p1t), False)

            if n == 0:
                l1_vec = (p2t - p1t).normalize()
                l1_direction_positive = (l1_vec.dot(dir_vec) > 0)

                tab_pt = p1t if l1_direction_positive else p2t
                vec_to_tab_p1 = (tab_pt - p1).dot(dir_vec)
                vec_to_tab_p2 = (tab_pt - p2).dot(dir_vec)
                offset_center = compute_tab_offset(length, num_tabs, tab_width, tab_spacing)
                use_p1 = abs(vec_to_tab_p1 - offset_center) < abs(vec_to_tab_p2 - offset_center)
                edge_start_point = (1 if p1_is_point1 else 2) if use_p1 else (2 if p1_is_point1 else 1)

            sketch.addConstraint(Sketcher.Constraint("Coincident", l1, 2, l2, 1))
            sketch.addConstraint(Sketcher.Constraint("Coincident", l2, 2, l3, 1))
            sketch.addConstraint(Sketcher.Constraint("Coincident", l3, 2, l4, 1))
            sketch.addConstraint(Sketcher.Constraint("Coincident", l4, 2, l1, 1))
            sketch.addConstraint(Sketcher.Constraint("Perpendicular", l1, l2))
            sketch.addConstraint(Sketcher.Constraint("Perpendicular", l1, l4))

            idx_w = sketch.addConstraint(Sketcher.Constraint("Distance", l1, 1, l1, 2, tab_width))
            if width_var:
                sketch.setExpression(f"Constraints[{idx_w}]", width_var)

            sketch.addConstraint(Sketcher.Constraint("PointOnObject", l1, 1, -3))
            sketch.addConstraint(Sketcher.Constraint("PointOnObject", l2, 1, -3))
            sketch.addConstraint(Sketcher.Constraint("PointOnObject", l3, 1, -4))
            sketch.addConstraint(Sketcher.Constraint("PointOnObject", l4, 1, -4))

            if n == 0:
                calculated_offset = compute_tab_offset(length, num_tabs, tab_width, tab_spacing)
                ref_pt = 1 if l1_direction_positive else 2
                if spacing_var:
                    expr = (
                        f"({length}mm - round({length}mm / ({width_var} + {spacing_var})) * {width_var}"
                        f" - (round({length}mm / ({width_var} + {spacing_var})) - 1) * {spacing_var}) / 2"
                    )
                    idx_s = sketch.addConstraint(
                        Sketcher.Constraint("Distance", -3, edge_start_point, l1, ref_pt, tab_spacing / 2)
                    )
                    sketch.setExpression(f"Constraints[{idx_s}]", expr)
                else:
                    sketch.addConstraint(
                        Sketcher.Constraint("Distance", -3, edge_start_point, l1, ref_pt, calculated_offset)
                    )
            else:
                ref_pt = 1 if l1_direction_positive else 2
                idx_s = sketch.addConstraint(
                    Sketcher.Constraint("Distance", l1 - 4, 2, l1, ref_pt, tab_spacing)
                )
                if spacing_var:
                    sketch.setExpression(f"Constraints[{idx_s}]", spacing_var)

        pad = body.newObject("PartDesign::Pad", "TabPad")
        pad.Profile = sketch
        pad.Length = tab_height
        body.recompute()

        face_index = None
        for idx, f in enumerate(other_obj.Shape.Faces):
            if (f.CenterOfMass.sub(other_face.CenterOfMass).Length < 1e-6 and
                    f.normalAt(0, 0).sub(other_face.normalAt(0, 0)).Length < 1e-6):
                face_index = idx + 1
                break
        if face_index is None:
            FreeCAD.Console.PrintError("Cannot locate the opposite face index.\n")
            doc.abortTransaction()
            return None, None

        FreeCAD.ActiveDocument.recompute()

        sketch_pl = sketch.getGlobalPlacement()
        pad_faces_to_bind = []
        for fi, f in enumerate(pad.Shape.Faces):
            fc_global = body.getGlobalPlacement().multVec(f.CenterOfMass)
            fc_sketch = sketch_pl.inverse().multVec(fc_global)
            if abs(fc_sketch.z - tab_height) < 0.1:
                near = any(
                    ((Vec2(fc_sketch.x, fc_sketch.y) - tc).length() < tab_width)
                    for tc in tab_centers_2d
                )
                if near:
                    pad_faces_to_bind.append(f"Face{fi + 1}")

        if not pad_faces_to_bind:
            FreeCAD.Console.PrintError("No pad face found at tab height.\n")
            return None, None

        binder = other_body.newObject("PartDesign::ShapeBinder", "TabBinder")
        binder.Support = [(pad, pad_faces_to_bind)]
        binder.TraceSupport = True
        other_body.recompute()

        sketch2 = other_body.newObject("Sketcher::SketchObject", "TabHoleSketch")
        sketch2.AttachmentSupport = (other_obj, [f"Face{face_index}"])
        sketch2.MapMode = "FlatFace"
        FreeCAD.ActiveDocument.recompute()

        for i, _ in enumerate(binder.Shape.Edges):
            sketch2.addExternal(binder.Name, f"Edge{i + 1}")
        FreeCAD.ActiveDocument.recompute()

        if not sketch2.ExternalGeometry or len(sketch2.ExternalGeometry[0]) < 2:
            FreeCAD.Console.PrintError("No valid external geometry for hole sketch.\n")
            doc.abortTransaction()
            return None, None

        dir_global = sketch.getGlobalPlacement().Rotation.multVec(Vector(dir_vec_2d.x, dir_vec_2d.y, 0))
        dir_in_sk2  = sketch2.getGlobalPlacement().Rotation.inverted().multVec(dir_global)
        horiz_is_width = abs(dir_in_sk2.x) > abs(dir_in_sk2.y)

        avg_edges_per_tab = len(binder.Shape.Edges) / num_tabs

        for n in range(num_tabs):
            ext_edge_index = int(n * avg_edges_per_tab)
            ext_start = -(ext_edge_index + 3)
            n_edges = (int(avg_edges_per_tab) if n < num_tabs - 1
                       else len(binder.Shape.Edges) - ext_edge_index)

            h_edges, v_edges = [], []
            for i in range(n_edges):
                ei = ext_start - i
                try:
                    pe1 = sketch2.getPoint(ei, 1)
                    pe2 = sketch2.getPoint(ei, 2)
                    ev = pe2 - pe1
                    (h_edges if abs(ev.x) > abs(ev.y) else v_edges).append((ei, pe1, pe2, ev))
                except Exception:
                    continue

            if len(h_edges) < 1 or len(v_edges) < 1 or len(h_edges) + len(v_edges) < 3:
                continue

            all_pts = [pt for e in h_edges + v_edges for pt in (e[1], e[2])]
            unique_pts: list = []
            for pt in all_pts:
                if not any((pt - up).Length < 0.001 for up in unique_pts):
                    unique_pts.append(pt)
            tab_center_v = sum(unique_pts, Vector(0, 0, 0)) / len(unique_pts)

            if horiz_is_width:
                hole_w = tab_width - tab_hole_clearance
                hole_h = tab_height
            else:
                hole_w = tab_height
                hole_h = tab_width - tab_hole_clearance

            hv = h_edges[0][3].normalize()
            vv = v_edges[0][3].normalize()

            p1h = tab_center_v - hv * (hole_w / 2) - vv * (hole_h / 2)
            p2h = p1h + hv * hole_w
            p3h = p2h + vv * hole_h
            p4h = p1h + vv * hole_h

            l1h = sketch2.addGeometry(Part.LineSegment(p1h, p2h), False)
            l2h = sketch2.addGeometry(Part.LineSegment(p2h, p3h), False)
            l3h = sketch2.addGeometry(Part.LineSegment(p3h, p4h), False)
            l4h = sketch2.addGeometry(Part.LineSegment(p4h, p1h), False)

            sketch2.addConstraint(Sketcher.Constraint("Coincident", l1h, 2, l2h, 1))
            sketch2.addConstraint(Sketcher.Constraint("Coincident", l2h, 2, l3h, 1))
            sketch2.addConstraint(Sketcher.Constraint("Coincident", l3h, 2, l4h, 1))
            sketch2.addConstraint(Sketcher.Constraint("Coincident", l4h, 2, l1h, 1))
            sketch2.addConstraint(Sketcher.Constraint("Perpendicular", l1h, l2h))
            sketch2.addConstraint(Sketcher.Constraint("Perpendicular", l2h, l3h))
            sketch2.addConstraint(Sketcher.Constraint("Perpendicular", l3h, l4h))
            sketch2.addConstraint(Sketcher.Constraint("Distance", l1h, 1, l1h, 2, hole_w))
            sketch2.addConstraint(Sketcher.Constraint("Distance", l2h, 1, l2h, 2, hole_h))

            hole_center = sketch2.addGeometry(Part.Point(tab_center_v), True)
            sketch2.addConstraint(Sketcher.Constraint("Symmetric", l1h, 1, l3h, 1, hole_center, 1))

            h_sorted = sorted(h_edges, key=lambda e: min(e[1].y, e[2].y))
            sketch2.addConstraint(
                Sketcher.Constraint("Symmetric", h_sorted[-1][0], 1, h_sorted[-2][0], 1, hole_center, 1)
            )

            if horiz_is_width:
                lock_edge = l1h if p1h.x > p2h.x else l2h
                sketch2.addConstraint(
                    Sketcher.Constraint("PointOnObject", lock_edge, 1, h_edges[0][0])
                )
            else:
                lock_edge = l1h if p2h.y > p3h.y else l4h
                sketch2.addConstraint(
                    Sketcher.Constraint("PointOnObject", lock_edge, 1, v_edges[0][0])
                )

        pocket = other_body.newObject("PartDesign::Pocket", "TabHolePocket")
        pocket.Profile = sketch2
        pocket.Length = tab_width

        sketch.Visibility  = False
        sketch2.Visibility = False
        binder.Visibility  = False

        FreeCAD.ActiveDocument.recompute()
        doc.commitTransaction()
        FreeCAD.Console.PrintMessage("Tabs and holes generated successfully.\n")
        return pad, pocket

    except Exception as exc:
        import traceback
        FreeCAD.Console.PrintError(f"Error generating tabs: {exc}\n")
        traceback.print_exc()
        doc.abortTransaction()
        return None, None
