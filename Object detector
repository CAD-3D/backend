"""
object_detector.py
-------------------
Logic to find "objects" of interest inside a parsed DXF document.

An "object" here is any INSERT entity (a block reference placed in the
drawing) that matches a given block name and/or layer name. You can also
match plain entities (e.g. a CIRCLE on a specific layer) if you don't use
blocks in your drawings — see `find_objects_by_layer_only` below.
"""

from typing import Optional, List, Dict, Any


def find_objects(
    doc,
    target_layer: Optional[str] = None,
    target_block: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Scan the modelspace of an ezdxf document and return every INSERT
    (block reference) entity that matches the given filters.

    Args:
        doc: an ezdxf Drawing object (already opened with ezdxf.readfile)
        target_layer: if given, only INSERTs on this layer are returned
        target_block: if given, only INSERTs of this block name are returned
                      (case-insensitive match)

    Returns:
        A list of dicts, each describing one matched object:
        {
            "id": "<dxf handle>",
            "block_name": "<block name>",
            "position": [x, y],
            "layer": "<layer name>",
            "rotation": <degrees>
        }
    """
    msp = doc.modelspace()
    results = []

    for e in msp:
        if e.dxftype() != "INSERT":
            continue

        block_name = e.dxf.name
        layer_name = e.dxf.layer

        if target_block and block_name.upper() != target_block.upper():
            continue
        if target_layer and layer_name.upper() != target_layer.upper():
            continue

        insert_point = e.dxf.insert  # ezdxf Vec3
        results.append({
            "id": e.dxf.handle,
            "block_name": block_name,
            "position": [round(insert_point.x, 4), round(insert_point.y, 4)],
            "layer": layer_name,
            "rotation": round(getattr(e.dxf, "rotation", 0.0), 2),
        })

    return results


def find_objects_by_layer_only(doc, target_layer: str) -> List[Dict[str, Any]]:
    """
    Alternative matcher: returns EVERY entity (not just INSERT/blocks) that
    sits on a given layer, along with a representative "position" for it.
    Useful if your drawings mark objects with plain geometry + a dedicated
    layer, rather than with named blocks.

    Returns a list shaped like find_objects()'s output, but "block_name"
    is replaced by the raw DXF entity type (LINE, CIRCLE, etc).
    """
    msp = doc.modelspace()
    results = []

    for e in msp:
        if e.dxf.layer.upper() != target_layer.upper():
            continue

        pos = _representative_point(e)
        if pos is None:
            continue

        results.append({
            "id": e.dxf.handle,
            "block_name": e.dxftype(),  # entity type, since there's no block
            "position": [round(pos[0], 4), round(pos[1], 4)],
            "layer": e.dxf.layer,
            "rotation": 0.0,
        })

    return results


def _representative_point(entity):
    """Best-effort single (x, y) point to represent any entity type."""
    t = entity.dxftype()
    try:
        if t == "CIRCLE":
            c = entity.dxf.center
            return (c.x, c.y)
        if t == "ARC":
            c = entity.dxf.center
            return (c.x, c.y)
        if t == "LINE":
            s = entity.dxf.start
            return (s.x, s.y)
        if t in ("LWPOLYLINE", "POLYLINE"):
            points = list(entity.get_points()) if t == "LWPOLYLINE" else list(entity.points())
            if points:
                p = points[0]
                return (p[0], p[1])
        if t == "TEXT" or t == "MTEXT":
            p = entity.dxf.insert
            return (p.x, p.y)
        if t == "INSERT":
            p = entity.dxf.insert
            return (p.x, p.y)
    except Exception:
        return None
    return None
