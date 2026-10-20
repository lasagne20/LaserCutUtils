"""
init_gui.py — Registers the LaserCutUtils workbench and its commands with FreeCAD.
"""
import os
import FreeCADGui


class LaserCutUtilsWorkbench(Workbench):
    """Tab-and-slot joinery and SVG export for laser cutting."""

    MenuText = "Laser Cut Utils"
    ToolTip  = "Tab-and-slot joinery and SVG export for laser cutting"
    Icon     = os.path.join(os.path.dirname(__file__), "resources", "icons", "LaserCutUtils.svg")

    def Initialize(self):
        """Called once when the workbench is first activated."""
        from freecad.LaserCutUtils import commands  # registers FreeCAD commands as a side effect
        self.list = [
            "LaserCutUtils_GenerateTabs",
            "LaserCutUtils_ExportSVG",
        ]
        self.appendToolbar("Laser Cut Utils", self.list)
        self.appendMenu("Laser Cut Utils", self.list)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(LaserCutUtilsWorkbench())
