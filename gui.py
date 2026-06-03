"""
gui.py — PySide dialog for the tab-and-slot tool.
"""
from __future__ import annotations

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui

from freecad_ops import generate_tabs_and_holes


# ---------------------------------------------------------------------------
# Shared widget helpers
# ---------------------------------------------------------------------------

def _make_spinbox(value: float, minimum: float, maximum: float,
                  suffix: str) -> QtGui.QDoubleSpinBox:
    spin = QtGui.QDoubleSpinBox()
    spin.setValue(value)
    spin.setMinimum(minimum)
    spin.setMaximum(maximum)
    spin.setSuffix(suffix)
    spin.setLocale(QtCore.QLocale(QtCore.QLocale.C))
    return spin


# ---------------------------------------------------------------------------
# Tab parameters dialog
# ---------------------------------------------------------------------------

def show_tabs_dialog(face, default_width: float = 10.0, default_height: float = 5.0,
                     default_spacing: float = 20.0, default_clearance: float = 0.6
                     ) -> tuple[float, float, float, float, bool] | None:
    """
    Show the tab configuration dialog.

    Returns ``(tab_width, tab_height, tab_spacing, hole_clearance, use_variables)``
    or ``None`` if cancelled.
    """
    dialog = QtGui.QDialog()
    dialog.setWindowTitle("Tab Parameters")
    layout = QtGui.QFormLayout(dialog)

    max_edge = max((e.Length for e in face.Edges), default=0.0)
    layout.addRow(QtGui.QLabel(f"Selected face length: {max_edge:.2f} mm"))

    thickness_input = _make_spinbox(default_height,  0.1, 100.0, " mm")
    width_input     = _make_spinbox(default_width,   0.1, 100.0, " mm")
    spacing_input   = _make_spinbox(default_spacing, 1.0, 500.0, " mm")
    clearance_input = _make_spinbox(default_clearance, 0.0, 10.0, " mm")

    layout.addRow("Material thickness:", thickness_input)
    layout.addRow("Tab width:",          width_input)
    layout.addRow("Tab spacing:",        spacing_input)
    layout.addRow("Hole clearance:",     clearance_input)

    use_vars = QtGui.QCheckBox()
    use_vars.setChecked(False)
    layout.addRow("Use variables (VarSet):", use_vars)

    buttons = QtGui.QDialogButtonBox(
        QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel
    )
    layout.addRow(buttons)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)

    if not dialog.exec_():
        return None

    return (
        width_input.value(),
        thickness_input.value(),
        spacing_input.value(),
        clearance_input.value(),
        use_vars.isChecked(),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def add_tabs_on_selected_face(tab_width: float = 5.0, tab_height: float = 5.0,
                               tab_spacing: float = 20.0,
                               tab_hole_clearance: float = 0.6) -> None:
    """
    Read the current FreeCAD face selection, show the dialog, and generate tabs.
    """
    sel = FreeCADGui.Selection.getSelectionEx()
    if not sel or not sel[0].HasSubObjects:
        FreeCAD.Console.PrintError("Please select a face on an object.\n")
        return

    obj  = sel[0].Object
    face = sel[0].SubObjects[0]

    body = obj.getParentGeoFeatureGroup()
    if body is None or body.TypeId != "PartDesign::Body":
        FreeCAD.Console.PrintError(
            "The selected object must be inside a PartDesign Body.\n"
        )
        return

    result = show_tabs_dialog(face, tab_width, tab_height, tab_spacing, tab_hole_clearance)
    if result is None:
        FreeCAD.Console.PrintMessage("Operation cancelled by user.\n")
        return

    tab_width, tab_height, tab_spacing, tab_hole_clearance, use_variables = result

    pad, pocket = generate_tabs_and_holes(
        obj, face, body,
        face_name=sel[0].SubElementNames[0],
        tab_width=tab_width,
        tab_height=tab_height,
        tab_spacing=tab_spacing,
        tab_hole_clearance=tab_hole_clearance,
        use_variables=use_variables,
    )

    if pad and pocket:
        FreeCAD.Console.PrintMessage(f"Tabs generated: {pad.Label}, {pocket.Label}\n")
    else:
        FreeCAD.Console.PrintError("Failed to generate tabs.\n")
