"""Box data of moyou-moss-bbox-node1.0.

Canonical layout, identical to the classic (Node 1.0) fields of the Node 2.0
CreateBoundingBoxes editor state:

    {"x": int, "y": int, "width": int, "height": int,
     "metadata": {"type": "text"|"obj", "text": str, "desc": str, "palette": [hex, ...]}}

x/y/width/height are pixels of the canvas (the width/height widgets). The node
outputs Node 2.0 elements instead:

    {"type": ..., "bbox": [ymin, xmin, ymax, xmax], "text": ..., "desc": ..., "color_palette": ...}

bbox is 0-1000 with y first, the format MOSS/Ideogram element inputs expect.

Incoming values are kept exactly as received. Elements are grained to the
0-1000 grid, so re-deriving pixels from them would shift boxes slightly and
makes an unchanged upstream value look new; the node stores the incoming tuple
verbatim and only re-reads it when it actually differs.
"""

import json
import math
import re

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _num(value):
    """Score/canvas numbers -> int when whole, float otherwise."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else float(value)
    if isinstance(value, str):
        try:
            return _num(float(value.strip()))
        except ValueError:
            return 0
    return 0


def _is_pixel_box(item):
    return all(k in item for k in ("x", "y", "width", "height"))


def _is_bbox_box(item):
    return "x" not in item and isinstance(item.get("bbox_2d"), (list, tuple)) and len(item["bbox_2d"]) >= 4


def _is_element(item):
    return "x" not in item and isinstance(item.get("bbox"), (list, tuple)) and len(item["bbox"]) == 4


def normalize_palette(palette):
    """Keep at most five valid #rrggbb strings, uppercased."""
    if not isinstance(palette, (list, tuple)):
        return []
    out = []
    for color in palette:
        if isinstance(color, str) and HEX_RE.match(color.strip()):
            out.append(color.strip().upper())
        if len(out) >= 5:
            break
    return out


def _metadata_from_element(element):
    etype = "text" if element.get("type") == "text" else "obj"
    return {
        "type": etype,
        "text": str(element.get("text", "")) if etype == "text" else "",
        "desc": str(element.get("desc", "")),
        "palette": normalize_palette(element.get("color_palette", [])),
    }


def to_box(item):
    """Pixel box / bbox_2d box / element -> canonical box, or None."""
    if not isinstance(item, dict):
        return None

    if _is_pixel_box(item):
        x, y, w, h = (_num(item[k]) for k in ("x", "y", "width", "height"))
        meta = item.get("metadata")
    elif _is_bbox_box(item):
        x1, y1, x2, y2 = (_num(v) for v in item["bbox_2d"][:4])
        x, y, w, h = x1, y1, x2 - x1, y2 - y1
        label = item.get("label", "")
        meta = {"type": "text", "text": "" if label is None else str(label), "desc": "",
                "palette": item.get("palette", [])}
    elif _is_element(item):
        # Frames are pixels over width/height; elements are the same but on a 0-1000 grid,
        # so width=height=1000 makes to_elements return the numbers that came in.
        ymin, xmin, ymax, xmax = (_num(v) for v in item["bbox"])
        x, y, w, h = xmin, ymin, xmax - xmin, ymax - ymin
        meta = _metadata_from_element(item)
    else:
        return None

    if w < 0:
        x, w = x + w, -w
    if h < 0:
        y, h = y + h, -h

    meta = meta if isinstance(meta, dict) else {}
    etype = "text" if meta.get("type") == "text" else "obj"
    return {
        "x": x, "y": y, "width": w, "height": h,
        "metadata": {
            "type": etype,
            "text": str(meta.get("text", "")) if etype == "text" else "",
            "desc": str(meta.get("desc", "")),
            "palette": normalize_palette(meta.get("palette")),
        },
    }


def parse_text(text):
    """Layout JSON string (list, single box, or {"boxes": [...]})-> canonical boxes. Never raises."""
    if not isinstance(text, str) or not text.strip():
        return []
    text = text.lstrip("\ufeff").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    try:
        data = json.loads(text)
    except ValueError:
        return []
    return to_boxes(data)


def to_boxes(data):
    if data is None or isinstance(data, str):
        return parse_text(data) if isinstance(data, str) else []
    if isinstance(data, dict):
        data = data["boxes"] if isinstance(data.get("boxes"), list) else [data]
    if not isinstance(data, list):
        return []
    if data and isinstance(data[0], list) and data[0] and isinstance(data[0][0], dict):
        data = data[0]
    boxes = []
    for item in data:
        box = to_box(item)
        if box is not None:
            boxes.append(box)
    return boxes


def canonical_json(boxes):
    return json.dumps(boxes, ensure_ascii=False, separators=(",", ":"))


def to_elements(boxes, width, height):
    """Canonical boxes -> Node 2.0 elements (bbox = [ymin, xmin, ymax, xmax], 0-1000)."""
    def grid(value, total):
        return max(0, min(1000, round(value / (total or 1) * 1000)))

    elements = []
    for box in boxes:
        x, y, w, h = (_num(box.get(k)) for k in ("x", "y", "width", "height"))
        xmin, xmax = sorted((grid(x, width), grid(x + w, width)))
        ymin, ymax = sorted((grid(y, height), grid(y + h, height)))
        meta = box.get("metadata") or {}
        etype = "text" if meta.get("type") == "text" else "obj"
        element = {"type": etype, "bbox": [ymin, xmin, ymax, xmax]}
        if etype == "text":
            element["text"] = str(meta.get("text", ""))
        element["desc"] = str(meta.get("desc", ""))
        palette = normalize_palette(meta.get("palette"))
        if palette:
            element["color_palette"] = palette
        elements.append(element)
    return elements


def to_bbox_frame(boxes):
    """Canonical boxes -> pixel frame [[{x, y, width, height}, ...]] (V3 bboxes output shape)."""
    frame = [{"x": b["x"], "y": b["y"], "width": b["width"], "height": b["height"]} for b in boxes]
    return [frame] if frame else []


def frame_to_boxes(data, width, height):
    """V3 pixel frame [[{x, y, width, height}]] -> canonical boxes (no metadata, as V3 has none)."""
    frame = data[0] if data and isinstance(data[0], list) else data
    boxes = []
    for item in frame or []:
        if isinstance(item, dict) and _is_pixel_box(item):
            boxes.append({
                "x": _num(item["x"]), "y": _num(item["y"]),
                "width": _num(item["width"]), "height": _num(item["height"]),
                "metadata": {"type": "obj", "text": "", "desc": "", "palette": []},
            })
    return boxes


# ---------- MOSS layout prompt ----------
#
# The official MOSS-Image layout prompt (and the KJNodes / comfy_extras builders that
# emit it) packs the same boxes as a JSON document instead of a bare list:
#
#   {"summary": {"caption": "...", "palette": [...], "canvas": "single"},
#    "items": [{"label": "object"|"character"|"text", "caption": "...", "text": "...",
#               "bbox": [y_min, x_min, y_max, x_max], "palette": [...], "tags": [...]}],
#    "bbox_coord_space": "abs_centralized", "bbox_format": "yxyx"}
#
# The bbox is in absolute pixels with the origin at the canvas centre, so converting
# needs the canvas size. `bbox_format: "yxyx"` names the axis order; the older
# "xyxy" spelling of the same document keeps x first. Everything else in the
# document (summary, canvas, tags) is metadata this node does not edit, so it is
# carried through untouched.

MOSS_SPACES = ("abs_centralized", "abs_topleft")
MOSS_FORMATS = ("yxyx", "xyxy")


def _moss_axes(values, order):
    """[a, b, c, d] + axis order -> (lo1, lo2, hi1, hi2) as (x1, y1, x2, y2)."""
    a, b, c, d = (_num(v) for v in values[:4])
    if order == "xyxy":
        return a, b, c, d
    return b, a, d, c


def _moss_pixel_box(bbox, order, space, width, height):
    """MOSS item bbox -> (x1, y1, x2, y2) canvas pixels, or None."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    x1, y1, x2, y2 = _moss_axes(bbox, order)
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    if "central" in str(space or "abs_centralized"):
        x1, x2 = x1 + width // 2, x2 + width // 2
        y1, y2 = y1 + height // 2, y2 + height // 2
    x1, x2 = (max(0.0, min(float(width), v)) for v in (x1, x2))
    y1, y2 = (max(0.0, min(float(height), v)) for v in (y1, y2))
    return x1, y1, x2, y2


def is_moss_layout(data):
    """True when the parsed JSON is a MOSS layout document (dict with items + bbox fields)."""
    return isinstance(data, dict) and isinstance(data.get("items"), list)


def moss_to_boxes(data, width, height):
    """MOSS layout prompt -> canonical boxes. Returns [] for a document without items."""
    if not is_moss_layout(data):
        return []
    space = data.get("bbox_coord_space") or "abs_centralized"
    order = "xyxy" if str(data.get("bbox_format") or "yxyx").strip().lower() == "xyxy" else "yxyx"
    boxes = []
    for item in data["items"]:
        if not isinstance(item, dict):
            continue
        box = _moss_pixel_box(item.get("bbox"), order, space, width, height)
        if box is None:
            continue
        x1, y1, x2, y2 = box
        etype = "text" if item.get("label") == "text" else "obj"
        boxes.append({
            "x": round(x1), "y": round(y1),
            "width": max(1, round(x2 - x1)), "height": max(1, round(y2 - y1)),
            "metadata": {
                "type": etype,
                "text": str(item.get("text") or "") if etype == "text" else "",
                "desc": str(item.get("caption") or ""),
                "palette": normalize_palette(item.get("palette") or []),
            },
        })
    return boxes


def boxes_to_moss(boxes, width, height, template=None, canvas="single"):
    """Canonical boxes -> MOSS layout prompt.

    `template` is the document the boxes came from: its summary, canvas and any
    per-item extras (tags) survive, so re-emitting an unedited prompt is lossless.
    """
    template = template if isinstance(template, dict) else {}
    old_items = template.get("items") if isinstance(template.get("items"), list) else []
    space = template.get("bbox_coord_space") or "abs_centralized"
    order = "xyxy" if str(template.get("bbox_format") or "yxyx").strip().lower() == "xyxy" else "yxyx"
    centered = "central" in str(space)
    hx, hy = width // 2, height // 2

    items = []
    for index, box in enumerate(boxes):
        x, y = _num(box.get("x")), _num(box.get("y"))
        w, h = _num(box.get("width")), _num(box.get("height"))
        x1, y1, x2, y2 = min(x, x + w), min(y, y + h), max(x, x + w), max(y, y + h)
        if centered:
            x1, x2, y1, y2 = x1 - hx, x2 - hx, y1 - hy, y2 - hy
        # floor/ceil the min/max edge like the official builder, so a box never shrinks
        if order == "xyxy":
            bbox = [math.floor(round(x1, 9)), math.floor(round(y1, 9)),
                    math.ceil(round(x2, 9)), math.ceil(round(y2, 9))]
        else:
            bbox = [math.floor(round(y1, 9)), math.floor(round(x1, 9)),
                    math.ceil(round(y2, 9)), math.ceil(round(x2, 9))]

        meta = box.get("metadata") or {}
        etype = "text" if meta.get("type") == "text" else "obj"
        item = {"label": "text" if etype == "text" else "object", "caption": str(meta.get("desc") or "")}
        if etype == "text":
            item["text"] = str(meta.get("text") or "")
        old = old_items[index] if index < len(old_items) and isinstance(old_items[index], dict) else {}
        if isinstance(old.get("tags"), list) and old["tags"]:
            item["tags"] = list(old["tags"])
        palette = normalize_palette(meta.get("palette"))
        if palette:
            item["palette"] = palette
        item["bbox"] = bbox
        items.append(item)

    summary = template.get("summary")
    summary = dict(summary) if isinstance(summary, dict) else {"caption": ""}
    if canvas and "canvas" not in summary and canvas != "single":
        summary["canvas"] = canvas

    doc = {"summary": summary, "items": items,
           "bbox_coord_space": space, "bbox_format": order}
    for key in ("canvas", "palette"):
        if key in template and key not in doc:
            doc[key] = template[key]
    return doc
