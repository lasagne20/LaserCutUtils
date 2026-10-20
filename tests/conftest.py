"""
conftest.py — Pytest fixtures and FreeCAD stub modules.

All tests in this suite run without a FreeCAD installation.  The stubs below
provide just enough surface area to exercise the pure-Python logic in
freecad.LaserCutUtils.utils and the lightweight geometry helpers tested here.
"""
from __future__ import annotations

import math
import sys
import types
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Minimal Vector stub
# ---------------------------------------------------------------------------

class _Vector:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    def __add__(self, other):
        return _Vector(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other):
        return _Vector(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar):
        return _Vector(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar):
        return self.__mul__(scalar)

    def __truediv__(self, scalar):
        return _Vector(self.x / scalar, self.y / scalar, self.z / scalar)

    def __repr__(self):
        return f"Vector({self.x}, {self.y}, {self.z})"

    def Length(self):
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def distanceToPoint(self, other):
        return (self - other).Length()

    def dot(self, other):
        return self.x * other.x + self.y * other.y + self.z * other.z

    def normalize(self):
        n = self.Length()
        return _Vector(self.x / n, self.y / n, self.z / n)

    def sub(self, other):
        return self - other


# ---------------------------------------------------------------------------
# Inject stub modules before any laser_cut_utils import
# ---------------------------------------------------------------------------

def _make_freecad_stub() -> types.ModuleType:
    fc = types.ModuleType("FreeCAD")
    fc.Vector = _Vector
    fc.Console = MagicMock()
    fc.ActiveDocument = None
    fc.BoundBox = MagicMock
    fc.Placement = MagicMock
    fc.Rotation = MagicMock
    return fc


def _inject_stubs():
    stubs = {
        "FreeCAD":     _make_freecad_stub(),
        "FreeCADGui":  MagicMock(),
        "Part":        MagicMock(),
        "Sketcher":    MagicMock(),
        "PartDesign":  MagicMock(),
        "Draft":       MagicMock(),
        "importSVG":   MagicMock(),
        "PySide":      MagicMock(),
        "PySide.QtGui":  MagicMock(),
        "PySide.QtCore": MagicMock(),
    }
    for name, mod in stubs.items():
        if name not in sys.modules:
            sys.modules[name] = mod


_inject_stubs()
