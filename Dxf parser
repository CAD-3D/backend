"""
dxf_parser.py
-------------
Reads a .dxf file with ezdxf and converts its modelspace entities into
plain JSON-serializable dicts, plus the overall bounding box of the
drawing (needed by the frontend to auto-fit the drawing into the canvas).
"""

import ezdxf
from ezdxf.math import Vec3
from typing import Dict, Any, List, Tuple


class DxfParseError(Exception):
    """Raised when a DXF file can't be read or parsed."""
    pass


def parse_dxf(file_path: str) -> Dict[str, Any]:
    """
    Parse a DXF file and return a dict with:
        {
            "bounds": {"minX":.., "minY":.., "maxX":.., "maxY":..},
            "entities": [ ... ]
        }
    """
    try:
        doc = ezdxf.readfile(file_path)
    except IOError as e:
        raise DxfParseError(f"Could not open file: {e}")
    except ezdxf.DXFStructureError as e:
        raise DxfParseError(f"Invalid or corrupted DXF structure: {e}")

    msp = doc.modelspace()
    entities: List[Dict[str, Any]] = []

    # Track bounds manually while we walk the entities (cheap + reliable,
    # works even for DXF files where the HEADER extents are stale/missing).
    min_x, min_y = float("inf"), float("inf")
    max_x, max_y = float("-inf"), float("-inf")

    def _update_bounds(x: float, y: float):
        nonlocal min_x, min_y, max_x, max_y
        if x < min_x: min_x = x
        if y < min_y: min_y = y
        if x > max_x: max_x = x
        if y > max_y: max_y = y

    for e in msp:
        try:
            entity_dict = _entity_to_dict(e, _update_bounds)
        except Exception:
            # Skip any single entity that fails to convert rather than
            # aborting the whole file — DXF files can contain edge cases.
            continue
        if entity_dict is not None:
            entities.append(entity_dict)

    # Fallback if the drawing was empty or nothing contributed to bounds
    if min_x == float("inf"):
        min_x = min_y = 0
        max_x = max_y = 100

    return {
        "bounds": {
            "minX": round(min_x, 4),
            "minY": round(min_y, 4),
            "maxX": round(max_x, 4),
            "maxY": round(max_y, 4),
        },
        "entities": entities,
    }


def get_doc(file_path: str):
    """Return the raw ezdxf Drawing object (used by object_detector.py)."""
    try:
        return ezdxf.readfile(file_path)
    except IOError as e:
        raise DxfParseError(f"Could not open file: {e}")
    except ezdxf.DXFStructureError as e:
        raise DxfParseError(f"Invalid or corrupted DXF structure: {e}")


def _entity_to_dict(e, update_bounds) -> Dict[str, Any]:
    """Convert one ezdxf entity into a plain dict, or None if unsupported."""
    t = e.dxftype()
    layer = e.dxf.layer

    if t == "LINE":
        s: Vec3 = e.dxf.start
        end: Vec3 = e.dxf.end
        update_bounds(s.x, s.y)
        update_bounds(end.x, end.y)
        return {"type": "LINE", "layer": layer,
                "start": [round(s.x, 4), round(s.y, 4)],
                "end": [round(end.x, 4), round(end.y, 4)]}

    if t == "CIRCLE":
        c: Vec3 = e.dxf.center
        r = e.dxf.radius
        update_bounds(c.x - r, c.y - r)
        update_bounds(c.x + r, c.y + r)
        return {"type": "CIRCLE", "layer": layer,
                "center": [round(c.x, 4), round(c.y, 4)],
                "radius": round(r, 4)}

    if t == "ARC":
        c: Vec3 = e.dxf.center
        r = e.dxf.radius
        update_bounds(c.x - r, c.y - r)
        update_bounds(c.x + r, c.y + r)
        return {"type": "ARC", "layer": layer,
                "center": [round(c.x, 4), round(c.y, 4)],
                "radius": round(r, 4),
                "start_angle": round(e.dxf.start_angle, 2),
                "end_angle": round(e.dxf.end_angle, 2)}

    if t in ("LWPOLYLINE", "POLYLINE"):
        if t == "LWPOLYLINE":
            raw_points = [(p[0], p[1]) for p in e.get_points()]
        else:  # legacy POLYLINE
            raw_points = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
        points = []
        for (x, y) in raw_points:
            x, y = float(x), float(y)  # cast away numpy scalar types
            update_bounds(x, y)
            points.append([round(x, 4), round(y, 4)])
        if not points:
            return None
        return {"type": "LWPOLYLINE", "layer": layer,
                "points": points,
                "closed": bool(getattr(e, "closed", False) or getattr(e.dxf, "flags", 0) & 1)}

    if t in ("TEXT", "MTEXT"):
        p: Vec3 = e.dxf.insert
        update_bounds(p.x, p.y)
        text_value = e.dxf.text if t == "TEXT" else e.text
        return {"type": t, "layer": layer,
                "position": [round(p.x, 4), round(p.y, 4)],
                "text": str(text_value)[:200]}  # cap length for safety

    if t == "INSERT":
        p: Vec3 = e.dxf.insert
        update_bounds(p.x, p.y)
        return {"type": "INSERT", "layer": layer,
                "block_name": e.dxf.name,
                "position": [round(p.x, 4), round(p.y, 4)],
                "rotation": round(getattr(e.dxf, "rotation", 0.0), 2)}

    # Entity type not handled yet (SPLINE, HATCH, DIMENSION, etc.) — skip.
    return None
