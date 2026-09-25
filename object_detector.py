"""
object_detector.py
------------------
Find objects of interest inside a DXF document.
"""

from typing import Optional, List, Dict, Any


def find_objects(
    doc,
    target_layer: Optional[str] = None,
    target_block: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Find INSERT/MINSERT entities matching layer and/or block name.
    """

    msp = doc.modelspace()

    results: List[Dict[str, Any]] = []

    layer_filter = (
        target_layer.upper()
        if target_layer
        else None
    )

    block_filter = (
        target_block.upper()
        if target_block
        else None
    )

    for entity in msp:

        entity_type = entity.dxftype()

        if entity_type not in (
            "INSERT",
            "MINSERT",
        ):
            continue

        try:

            block_name = str(
                entity.dxf.name
            )

            layer_name = str(
                entity.dxf.layer
            )

        except Exception:

            continue

        if (
            block_filter
            and block_name.upper()
            != block_filter
        ):
            continue

        if (
            layer_filter
            and layer_name.upper()
            != layer_filter
        ):
            continue

        try:

            position = entity.dxf.insert

            rotation = float(
                getattr(
                    entity.dxf,
                    "rotation",
                    0.0,
                )
            )

            scale_x = float(
                getattr(
                    entity.dxf,
                    "xscale",
                    1.0,
                )
            )

            scale_y = float(
                getattr(
                    entity.dxf,
                    "yscale",
                    1.0,
                )
            )

            scale_z = float(
                getattr(
                    entity.dxf,
                    "zscale",
                    1.0,
                )
            )

            results.append({
                "id": getattr(
                    entity.dxf,
                    "handle",
                    None,
                ),

                "entity_type": entity_type,

                "block_name": block_name,

                "position": [
                    round(position.x, 4),
                    round(position.y, 4),
                ],

                "layer": layer_name,

                "rotation": round(
                    rotation,
                    3,
                ),

                "scale": [
                    round(scale_x, 4),
                    round(scale_y, 4),
                    round(scale_z, 4),
                ],
            })

        except Exception:
            continue

    return results


def find_objects_by_layer_only(
    doc,
    target_layer: str,
) -> List[Dict[str, Any]]:
    """
    Find every modelspace entity on a given layer.
    """

    msp = doc.modelspace()

    results: List[Dict[str, Any]] = []

    target = target_layer.upper()

    for entity in msp:

        try:
            layer_name = str(
                entity.dxf.layer
            )
        except Exception:
            continue

        if layer_name.upper() != target:
            continue

        position = _representative_point(
            entity
        )

        if position is None:
            continue

        results.append({
            "id": getattr(
                entity.dxf,
                "handle",
                None,
            ),

            "block_name": entity.dxftype(),

            "position": [
                round(position[0], 4),
                round(position[1], 4),
            ],

            "layer": layer_name,

            "rotation": round(
                float(
                    getattr(
                        entity.dxf,
                        "rotation",
                        0.0,
                    )
                ),
                3,
            ),
        })

    return results


def _representative_point(entity):
    """
    Return one representative 2D point.
    """

    entity_type = entity.dxftype()

    try:

        # ---------------------------------------------------------------
        # POINT
        # ---------------------------------------------------------------

        if entity_type == "POINT":

            p = entity.dxf.location

            return (
                p.x,
                p.y,
            )

        # ---------------------------------------------------------------
        # CIRCLE
        # ---------------------------------------------------------------

        if entity_type == "CIRCLE":

            p = entity.dxf.center

            return (
                p.x,
                p.y,
            )

        # ---------------------------------------------------------------
        # ARC
        # ---------------------------------------------------------------

        if entity_type == "ARC":

            p = entity.dxf.center

            return (
                p.x,
                p.y,
            )

        # ---------------------------------------------------------------
        # LINE
        # ---------------------------------------------------------------

        if entity_type == "LINE":

            p = entity.dxf.start

            return (
                p.x,
                p.y,
            )

        # ---------------------------------------------------------------
        # ELLIPSE
        # ---------------------------------------------------------------

        if entity_type == "ELLIPSE":

            p = entity.dxf.center

            return (
                p.x,
                p.y,
            )

        # ---------------------------------------------------------------
        # LWPOLYLINE
        # ---------------------------------------------------------------

        if entity_type == "LWPOLYLINE":

            points = list(
                entity.get_points(
                    "xy"
                )
            )

            if points:

                return (
                    points[0][0],
                    points[0][1],
                )

        # ---------------------------------------------------------------
        # POLYLINE
        # ---------------------------------------------------------------

        if entity_type == "POLYLINE":

            for vertex in entity.vertices:

                p = vertex.dxf.location

                return (
                    p.x,
                    p.y,
                )

        # ---------------------------------------------------------------
        # TEXT / MTEXT
        # ---------------------------------------------------------------

        if entity_type in (
            "TEXT",
            "MTEXT",
        ):

            p = entity.dxf.insert

            return (
                p.x,
                p.y,
            )

        # ---------------------------------------------------------------
        # INSERT
        # ---------------------------------------------------------------

        if entity_type in (
            "INSERT",
            "MINSERT",
        ):

            p = entity.dxf.insert

            return (
                p.x,
                p.y,
            )

    except Exception:

        return None

    return None
