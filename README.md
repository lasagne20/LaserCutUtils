# LaserCutUtils

FreeCAD utilities for **laser-cut tab-and-slot joinery** and SVG projection export.

## Features

- **Tab generation** — selects a face, finds the opposite face on an adjacent body, and generates parametric tabs (Pad) + matching slots (Pocket) with configurable width, spacing, and clearance.
- **SVG export** — projects a Part/PartDesign solid along its largest face normal and writes a clean SVG file ready for laser-cutting.
- **Pure-Python core** — geometry helpers in `core.py` have no FreeCAD dependency and are fully unit-tested with pytest.

## Project layout

```
LaserCutUtils/
├── src/
│   └── laser_cut_utils/
│       ├── __init__.py
│       ├── core.py          # Pure-Python geometry (Vec2, tab layout, SVG primitives)
│       ├── freecad_ops.py   # FreeCAD Sketcher/PartDesign operations
│       ├── svg_export.py    # Draft projection → SVG file
│       └── gui.py           # PySide dialog + entry point
├── tests/
│   ├── conftest.py          # FreeCAD stub modules for pytest
│   └── test_core.py         # Unit tests (no FreeCAD required)
├── pyproject.toml
└── .gitignore
```

## Installation (development)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
```

## Running tests

```bash
pytest
```

All tests in `tests/test_core.py` run without FreeCAD — stubs are injected by `conftest.py`.

## Usage from a FreeCAD macro

```python
import sys
sys.path.insert(0, r"C:\path\to\LaserCutUtils\src")

from laser_cut_utils.gui import add_tabs_on_selected_face
add_tabs_on_selected_face()
```

Or call `generate_tabs_and_holes()` directly for scripted use:

```python
from laser_cut_utils.freecad_ops import generate_tabs_and_holes

pad, pocket = generate_tabs_and_holes(
    obj, face, body,
    tab_width=10, tab_height=5, tab_spacing=20, tab_hole_clearance=0.6
)
```

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `tab_width` | 10 mm | Width of each tab |
| `tab_height` | 5 mm | Height of each tab (= material thickness) |
| `tab_spacing` | 20 mm | Gap between consecutive tabs |
| `tab_hole_clearance` | 0.6 mm | Clearance subtracted from slot width |
| `use_variables` | False | Store params in a FreeCAD VarSet |
