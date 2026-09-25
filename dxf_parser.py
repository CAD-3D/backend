"""
dxf_parser.py
-------------
Robust DXF parser for the CAD web application.

Goals:
- Convert DXF modelspace entities into JSON-safe dictionaries.
- Calculate accurate 2D drawing bounds.
- Preserve LWPOLYLINE bulge information.
- Handle common CAD entities safely.
- Track parsing statistics and warnings instead of silently dropping data.
- Optionally expand INSERT block references.
- Keep the JSON structure lightweight for browser rendering.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

import ezdxf
from ezdxf.math import Vec3


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MAX_ENTITIES = 500_000
DEFAULT_MAX_BLOCK_ENTITIES = 100_000

ROUND_COORDS = 4
ROUND_ANGLE = 3


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class DxfParseError(Exception):
    """Raised when a DXF file cannot be opened or parsed."""
    pass


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_dxf(
    file_path: str,
    *,
    expand_blocks: bool = False,
    max_entities: int = DEFAULT_MAX_ENTITIES,
) -> Dict[str, Any]:
    """
    Parse a DXF file.

    Returns:

    {
        "bounds": {
            "minX": ...,
            "minY": ...,
            "maxX": ...,
            "maxY": ...
        },

        "entities": [...],

        "stats": {
            "total_entities": ...,
            "parsed_entities": ...,
            "skipped_entities": ...,
            "entity_types": {...},
            "layers": {...}
        },

        "warnings": [...]
    }

    Parameters
    ----------
    file_path:
        Path to DXF file.

    expand_blocks:
        If True, INSERT block geometry is expanded using virtual entities.
        Default False because expanding large blocks can be expensive.

    max_entities:
        Safety limit for the number of modelspace entities processed.
    """

    doc = get_doc(file_path)

    msp = doc.modelspace()

    entities: List[Dict[str, Any]] = []

    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    total_entities = 0
    parsed_entities = 0
    skipped_entities = 0

    entity_type_counter: Counter[str] = Counter()
    layer_counter: Counter[str] = Counter()
    skipped_counter: Counter[str] = Counter()

    warnings: List[Dict[str, Any]] = []

    def update_bounds(x: float, y: float):
        nonlocal min_x, min_y, max_x, max_y

        if not math.isfinite(x) or not math.isfinite(y):
            return

        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x)
        max_y = max(max_y, y)

    for index, entity in enumerate(msp):

        if index >= max_entities:
            warnings.append({
                "type": "ENTITY_LIMIT_REACHED",
                "message": (
                    f"Parsing stopped after {max_entities:,} "
                    f"modelspace entities."
                ),
            })
            break

        total_entities += 1

        try:
            entity_type = entity.dxftype()
        except Exception:
            entity_type = "UNKNOWN"

        entity_type_counter[entity_type] += 1

        try:
            layer_name = entity.dxf.layer
            layer_counter[layer_name] += 1
        except Exception:
            layer_name = "UNKNOWN"

        try:
            result = _entity_to_dict(
                entity,
                update_bounds,
                expand_blocks=expand_blocks,
            )

        except Exception as exc:
            skipped_entities += 1
            skipped_counter[entity_type] += 1

            warnings.append({
                "type": "ENTITY_PARSE_ERROR",
                "entity_type": entity_type,
                "handle": _safe_handle(entity),
                "message": str(exc)[:500],
            })

            continue

        if result is None:
            skipped_entities += 1
            skipped_counter[entity_type] += 1
            continue

        entities.append(result)
        parsed_entities += 1

    # -----------------------------------------------------------------------
    # Empty drawing fallback
    # -----------------------------------------------------------------------

    if min_x == float("inf"):
        min_x = 0.0
        min_y = 0.0
        max_x = 100.0
        max_y = 100.0

        warnings.append({
            "type": "EMPTY_GEOMETRY",
            "message": "No drawable geometry contributed to the bounds."
        })

    # -----------------------------------------------------------------------
    # Final result
    # -----------------------------------------------------------------------

    return {
        "bounds": {
            "minX": _round(min_x),
            "minY": _round(min_y),
            "maxX": _round(max_x),
            "maxY": _round(max_y),
        },

        "entities": entities,

        "stats": {
            "total_entities": total_entities,
            "parsed_entities": parsed_entities,
            "skipped_entities": skipped_entities,

            "entity_types": dict(
                sorted(entity_type_counter.items())
            ),

            "skipped_by_type": dict(
                sorted(skipped_counter.items())
            ),

            "layers": dict(
                sorted(layer_counter.items())
            ),
        },

        "warnings": warnings[:500],
    }


# ---------------------------------------------------------------------------
# DXF document loading
# ---------------------------------------------------------------------------

def get_doc(file_path: str):
    """
    Load an ezdxf Drawing object.
    """

    try:
        return ezdxf.readfile(file_path)

    except IOError as exc:
        raise DxfParseError(
            f"Could not open DXF file: {exc}"
        ) from exc

    except ezdxf.DXFStructureError as exc:
        raise DxfParseError(
            f"Invalid or corrupted DXF structure: {exc}"
        ) from exc

    except Exception as exc:
        raise DxfParseError(
            f"Unexpected DXF loading error: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Entity dispatcher
# ---------------------------------------------------------------------------

def _entity_to_dict(
    entity,
    update_bounds: Callable[[float, float], None],
    *,
    expand_blocks: bool = False,
) -> Optional[Dict[str, Any]]:

    entity_type = entity.dxftype()

    layer = _safe_layer(entity)

    # -----------------------------------------------------------------------
    # LINE
    # -----------------------------------------------------------------------

    if entity_type == "LINE":

        start: Vec3 = entity.dxf.start
        end: Vec3 = entity.dxf.end

        update_bounds(start.x, start.y)
        update_bounds(end.x, end.y)

        return {
            "type": "LINE",
            "layer": layer,

            "start": [
                _round(start.x),
                _round(start.y),
            ],

            "end": [
                _round(end.x),
                _round(end.y),
            ],
        }

    # -----------------------------------------------------------------------
    # POINT
    # -----------------------------------------------------------------------

    if entity_type == "POINT":

        p: Vec3 = entity.dxf.location

        update_bounds(p.x, p.y)

        return {
            "type": "POINT",
            "layer": layer,

            "position": [
                _round(p.x),
                _round(p.y),
            ],
        }

    # -----------------------------------------------------------------------
    # CIRCLE
    # -----------------------------------------------------------------------

    if entity_type == "CIRCLE":

        center: Vec3 = entity.dxf.center
        radius = float(entity.dxf.radius)

        _update_circle_bounds(
            center.x,
            center.y,
            radius,
            update_bounds,
        )

        return {
            "type": "CIRCLE",
            "layer": layer,

            "center": [
                _round(center.x),
                _round(center.y),
            ],

            "radius": _round(radius),
        }

    # -----------------------------------------------------------------------
    # ARC
    # -----------------------------------------------------------------------

    if entity_type == "ARC":

        center: Vec3 = entity.dxf.center
        radius = float(entity.dxf.radius)

        start_angle = float(entity.dxf.start_angle)
        end_angle = float(entity.dxf.end_angle)

        _update_arc_bounds(
            center.x,
            center.y,
            radius,
            start_angle,
            end_angle,
            update_bounds,
        )

        return {
            "type": "ARC",
            "layer": layer,

            "center": [
                _round(center.x),
                _round(center.y),
            ],

            "radius": _round(radius),

            "start_angle": _round_angle(start_angle),
            "end_angle": _round_angle(end_angle),
        }

    # -----------------------------------------------------------------------
    # ELLIPSE
    # -----------------------------------------------------------------------

    if entity_type == "ELLIPSE":

        center: Vec3 = entity.dxf.center
        major_axis: Vec3 = entity.dxf.major_axis

        ratio = float(entity.dxf.ratio)

        _update_ellipse_bounds(
            center.x,
            center.y,
            major_axis.x,
            major_axis.y,
            ratio,
            entity.dxf.start_param,
            entity.dxf.end_param,
            update_bounds,
        )

        return {
            "type": "ELLIPSE",
            "layer": layer,

            "center": [
                _round(center.x),
                _round(center.y),
            ],

            "major_axis": [
                _round(major_axis.x),
                _round(major_axis.y),
            ],

            "ratio": _round(ratio),

            "start_param": _round(
                float(entity.dxf.start_param)
            ),

            "end_param": _round(
                float(entity.dxf.end_param)
            ),
        }

    # -----------------------------------------------------------------------
    # LWPOLYLINE
    # -----------------------------------------------------------------------

    if entity_type == "LWPOLYLINE":

        points = []

        for point in entity.get_points(
            "xyb"
        ):
            x = float(point[0])
            y = float(point[1])
            bulge = float(point[2])

            update_bounds(x, y)

            points.append({
                "x": _round(x),
                "y": _round(y),
                "bulge": _round(bulge),
            })

        if not points:
            return None

        closed = bool(entity.closed)

        return {
            "type": "LWPOLYLINE",
            "layer": layer,
            "points": points,
            "closed": closed,
        }

    # -----------------------------------------------------------------------
    # Legacy POLYLINE
    # -----------------------------------------------------------------------

    if entity_type == "POLYLINE":

        points = []

        for vertex in entity.vertices:

            p = vertex.dxf.location

            x = float(p.x)
            y = float(p.y)

            update_bounds(x, y)

            bulge = float(
                getattr(vertex.dxf, "bulge", 0.0)
            )

            points.append({
                "x": _round(x),
                "y": _round(y),
                "bulge": _round(bulge),
            })

        if not points:
            return None

        return {
            "type": "POLYLINE",
            "layer": layer,
            "points": points,
            "closed": bool(
                getattr(entity, "is_closed", False)
            ),
        }

    # -----------------------------------------------------------------------
    # TEXT
    # -----------------------------------------------------------------------

    if entity_type == "TEXT":

        p: Vec3 = entity.dxf.insert

        update_bounds(p.x, p.y)

        return {
            "type": "TEXT",
            "layer": layer,

            "position": [
                _round(p.x),
                _round(p.y),
            ],

            "text": str(
                getattr(entity.dxf, "text", "")
            )[:500],

            "height": _round(
                float(
                    getattr(
                        entity.dxf,
                        "height",
                        0.0
                    )
                )
            ),

            "rotation": _round_angle(
                float(
                    getattr(
                        entity.dxf,
                        "rotation",
                        0.0
                    )
                )
            ),
        }

    # -----------------------------------------------------------------------
    # MTEXT
    # -----------------------------------------------------------------------

    if entity_type == "MTEXT":

        p: Vec3 = entity.dxf.insert

        update_bounds(p.x, p.y)

        try:
            text_value = entity.plain_text()
        except Exception:
            text_value = str(
                getattr(entity, "text", "")
            )

        return {
            "type": "MTEXT",
            "layer": layer,

            "position": [
                _round(p.x),
                _round(p.y),
            ],

            "text": str(text_value)[:1000],

            "height": _round(
                float(
                    getattr(
                        entity.dxf,
                        "char_height",
                        0.0
                    )
                )
            ),

            "rotation": _round_angle(
                float(
                    getattr(
                        entity.dxf,
                        "rotation",
                        0.0
                    )
                )
            ),
        }

    # -----------------------------------------------------------------------
    # INSERT / BLOCK REFERENCE
    # -----------------------------------------------------------------------

    if entity_type == "INSERT":

        p: Vec3 = entity.dxf.insert

        update_bounds(p.x, p.y)

        block_name = str(
            getattr(entity.dxf, "name", "")
        )

        rotation = float(
            getattr(
                entity.dxf,
                "rotation",
                0.0
            )
        )

        scale_x = float(
            getattr(
                entity.dxf,
                "xscale",
                1.0
            )
        )

        scale_y = float(
            getattr(
                entity.dxf,
                "yscale",
                1.0
            )
        )

        scale_z = float(
            getattr(
                entity.dxf,
                "zscale",
                1.0
            )
        )

        result = {
            "type": "INSERT",
            "layer": layer,

            "id": _safe_handle(entity),

            "block_name": block_name,

            "position": [
                _round(p.x),
                _round(p.y),
            ],

            "rotation": _round_angle(rotation),

            "scale": [
                _round(scale_x),
                _round(scale_y),
                _round(scale_z),
            ],
        }

        # Optional block expansion
        if expand_blocks:
            result["block_entities"] = []

            try:
                for virtual_entity in entity.virtual_entities():

                    virtual_dict = _entity_to_dict(
                        virtual_entity,
                        update_bounds,
                        expand_blocks=False,
                    )

                    if virtual_dict is not None:
                        result["block_entities"].append(
                            virtual_dict
                        )

            except Exception as exc:

                result["block_expand_warning"] = str(
                    exc
                )[:500]

        return result

    # -----------------------------------------------------------------------
    # Unsupported entity
    # -----------------------------------------------------------------------

    return None


# ---------------------------------------------------------------------------
# Bounding box helpers
# ---------------------------------------------------------------------------

def _update_circle_bounds(
    cx: float,
    cy: float,
    radius: float,
    update_bounds,
):
    if radius < 0:
        return

    update_bounds(
        cx - radius,
        cy - radius,
    )

    update_bounds(
        cx + radius,
        cy + radius,
    )


def _update_arc_bounds(
    cx: float,
    cy: float,
    radius: float,
    start_angle_deg: float,
    end_angle_deg: float,
    update_bounds,
):
    """
    Calculate a tighter 2D bounding box for an ARC.

    Unlike the old implementation, this does not simply use
    center +/- radius in both directions.
    """

    if radius <= 0:
        update_bounds(cx, cy)
        return

    start = math.radians(start_angle_deg)
    end = math.radians(end_angle_deg)

    # DXF ARC angles normally run counter-clockwise.
    # Normalize to [0, 2*pi).
    start = start % (2 * math.pi)
    end = end % (2 * math.pi)

    update_bounds(
        cx + radius * math.cos(start),
        cy + radius * math.sin(start),
    )

    update_bounds(
        cx + radius * math.cos(end),
        cy + radius * math.sin(end),
    )

    # Cardinal angles.
    cardinal_angles = [
        0.0,
        math.pi / 2.0,
        math.pi,
        3.0 * math.pi / 2.0,
    ]

    for angle in cardinal_angles:
        if _angle_on_ccw_arc(
            angle,
            start,
            end,
        ):
            update_bounds(
                cx + radius * math.cos(angle),
                cy + radius * math.sin(angle),
            )


def _angle_on_ccw_arc(
    angle: float,
    start: float,
    end: float,
) -> bool:
    """
    Return True if angle is located on the CCW arc
    from start to end.
    """

    angle %= 2 * math.pi
    start %= 2 * math.pi
    end %= 2 * math.pi

    if end < start:
        end += 2 * math.pi

    if angle < start:
        angle += 2 * math.pi

    return start <= angle <= end


def _update_ellipse_bounds(
    cx: float,
    cy: float,
    major_x: float,
    major_y: float,
    ratio: float,
    start_param: float,
    end_param: float,
    update_bounds,
):
    """
    Approximate ellipse/elliptical-arc bounds using parametric sampling.

    This is intentionally lightweight and safe for web rendering.
    """

    major_len = math.sqrt(
        major_x * major_x +
        major_y * major_y
    )

    if major_len <= 0:
        update_bounds(cx, cy)
        return

    minor_len = major_len * abs(ratio)

    ux = major_x / major_len
    uy = major_y / major_len

    vx = -uy
    vy = ux

    start = float(start_param)
    end = float(end_param)

    if end < start:
        end += 2 * math.pi

    # Include enough samples for a stable visual bounding box.
    sample_count = max(
        32,
        min(
            720,
            int((end - start) / (math.pi / 90))
        )
    )

    for i in range(sample_count + 1):

        t = start + (
            (end - start) *
            i /
            sample_count
        )

        cos_t = math.cos(t)
        sin_t = math.sin(t)

        x = (
            cx
            + major_len * cos_t * ux
            + minor_len * sin_t * vx
        )

        y = (
            cy
            + major_len * cos_t * uy
            + minor_len * sin_t * vy
        )

        update_bounds(x, y)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _round(value: float) -> float:
    return round(float(value), ROUND_COORDS)


def _round_angle(value: float) -> float:
    return round(float(value), ROUND_ANGLE)


def _safe_layer(entity) -> str:
    try:
        return str(entity.dxf.layer)
    except Exception:
        return "0"


def _safe_handle(entity) -> Optional[str]:
    try:
        return entity.dxf.handle
    except Exception:
        return None
