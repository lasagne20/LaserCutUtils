"""
commands.py — FreeCAD command classes for the LaserCutUtils workbench.

Each class is registered via FreeCADGui.addCommand() and maps to one
toolbar/menu entry.
"""
import os
import FreeCAD
import FreeCADGui

_ICONS = os.path.join(os.path.dirname(__file__), "icons")


class _CmdGenerateTabs:
    """Generate tab-and-slot joints on the selected face."""

    def GetResources(self):
        return {
            "MenuText": "Generate Tabs",
            "ToolTip":  "Generate tab-and-slot joints on the selected face",
            "Pixmap":   os.path.join(_ICONS, "GenerateTabs.svg"),
        }

    def Activated(self):
        from gui import add_tabs_on_selected_face
        add_tabs_on_selected_face()

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


class _CmdExportSVG:
    """Export the selected object as an SVG projection."""

    def GetResources(self):
        return {
            "MenuText": "Export SVG",
            "ToolTip":  "Export the selected object as a flat SVG projection",
            "Pixmap":   os.path.join(_ICONS, "ExportSVG.svg"),
        }

    def Activated(self):
        from svg_export import export_projection_to_svg
        from PySide import QtGui

        sel = FreeCADGui.Selection.getSelection()
        if not sel:
            FreeCAD.Console.PrintError("Please select an object to export.\n")
            return

        output_dir = QtGui.QFileDialog.getExistingDirectory(
            None, "Select output folder"
        )
        if not output_dir:
            return

        for obj in sel:
            if not hasattr(obj, "Shape"):
                continue
            output_path = os.path.join(output_dir, f"{obj.Label}.svg")
            export_projection_to_svg(obj, output_path)
            FreeCAD.Console.PrintMessage(f"Exported: {output_path}\n")

    def IsActive(self):
        return (FreeCAD.ActiveDocument is not None and
                bool(FreeCADGui.Selection.getSelection()))


FreeCADGui.addCommand("LaserCutUtils_GenerateTabs", _CmdGenerateTabs())
FreeCADGui.addCommand("LaserCutUtils_ExportSVG",    _CmdExportSVG())
