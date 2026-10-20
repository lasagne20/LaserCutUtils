# LaserCutUtils

FreeCAD workbench for **laser-cut tab-and-slot joinery** and **SVG projection export**.

[License: LGPL-2.1-or-later](LICENSE) | Requires **FreeCAD ≥ 1.0** (uses `AttachmentSupport` and `App::VarSet`).

## Features

- **Generate Tabs** — select a face, the workbench finds the opposite face on an adjacent
  body (same assembly) and generates parametric tabs (Pad) plus matching slots (Pocket)
  with configurable width, spacing, and clearance. Optional VarSet-backed parameters for
  fully parametric editing via expressions.
- **Export SVG** — projects a Part/PartDesign solid along its largest face normal
  (lines, arcs, and splines supported) and writes a clean, mm-accurate SVG file ready
  for laser cutting, with optional colored sketch overlays.
- **Pure-Python core** — geometry helpers in `utils.py` have no FreeCAD dependency and
  are fully unit-tested with pytest.

## Installation

### From the FreeCAD Add-on Manager

1. FreeCAD → **Tools → Add-on Manager**
2. Search for **LaserCutUtils** and install.

### Manual

Copy (or clone) this folder into your FreeCAD user modules directory:

- Windows: `%APPDATA%/FreeCAD/Mod/LaserCutUtils`
- Linux: `~/.local/share/FreeCAD/Mod/LaserCutUtils`
- macOS: `~/Library/Application Support/FreeCAD/Mod/LaserCutUtils`

Restart FreeCAD and select the **Laser Cut Utils** workbench.

## Usage

### Generate Tabs

1. Select a face on a PartDesign feature that sits inside a PartDesign Body,
   opposite another body of the same assembly.
2. **Laser Cut Utils → Generate Tabs**
3. Adjust the parameters in the dialog:

| Parameter | Default | Description |
|---|---|---|
| Material thickness | 5 mm | Height of each tab (= material thickness) |
| Tab width | 10 mm | Width of each tab |
| Tab spacing | 20 mm | Gap between consecutive tabs |
| Hole clearance | 0.6 mm | Clearance subtracted from the slot width |
| Use variables (VarSet) | off | Store the parameters in a VarSet for parametric editing |

Tabs (Pad) are created on the selected body; matching slots (Pocket) are cut into the
opposite body.

### Export SVG

1. Select one or more objects with a `Shape`.
2. **Laser Cut Utils → Export SVG**, choose the output folder.

Each object is written as `<Label>.svg`. `export_projection_to_svg()` can also be called
from a macro for scripted use:

```python
import sys
sys.path.insert(0, r"C:\path\to\Mod")  # folder containing LaserCutUtils

from LaserCutUtils.svg_export import export_projection_to_svg
export_projection_to_svg(obj, r"C:\out\piece.svg")
```

Tabs can be generated programmatically as well:

```python
from LaserCutUtils.freecad_ops import generate_tabs_and_holes

pad, pocket = generate_tabs_and_holes(
    obj, face, body,
    tab_width=10, tab_height=5, tab_spacing=20, tab_hole_clearance=0.6,
)
```

## Project layout

```
LaserCutUtils/
├── Init.py               # Workbench init (called by FreeCAD)
├── InitGui.py            # Workbench + toolbar registration
├── commands.py           # FreeCAD command classes
├── gui.py                # PySide parameter dialog
├── freecad_ops.py        # PartDesign/Sketcher tab-and-slot operations
├── svg_export.py         # Draft projection → SVG file
├── utils.py              # Pure-Python geometry (no FreeCAD import)
├── icons/
├── tests/
│   ├── conftest.py       # FreeCAD stub modules for pytest
│   └── test_core.py      # Unit tests (no FreeCAD required)
└── package.xml           # FreeCAD Add-on Manager metadata
```

## Development

Tests run without a FreeCAD installation — stub modules are injected by `tests/conftest.py`:

```bash
python -m pip install pytest
python -m pytest
```

## License

[GNU LGPL-2.1-or-later](LICENSE) — the same license as FreeCAD itself.
