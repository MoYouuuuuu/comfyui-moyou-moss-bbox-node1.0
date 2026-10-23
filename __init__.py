"""moyou-moss-bbox-node1.0: MOSS/Ideogram bounding boxes on classic (Node 1.0) nodes.

Two nodes, all inputs/outputs plain built-in types:

- 创建边界框 (Node 1.0): canvas editor. Stores/accepts the classic pixel box
  layout {x, y, width, height, metadata}, outputs MOSS `elements`
  (bbox = [ymin, xmin, ymax, xmax], 0-1000) plus a pixel preview.
- moyou边界框可视化: draws boxes from a MOSS layout prompt, elements, bbox_2d or
  pixel boxes back onto an image.

Requires the ComfyUI frontend (>= 1.16) for the editor widget; the nodes
register on any ComfyUI build because nothing depends on the V3 API.
"""

import json

from .bbox_data import (canonical_json, frame_to_boxes, is_moss_layout, moss_to_boxes, parse_text,
                        to_bbox_frame, to_boxes, to_elements)
from .render import render

CATEGORY = "moyou"

# How the visualizer reads an incoming box list. "moss" is the MOSS-Image layout
# prompt (absolute pixels from the canvas centre); the other two are the 0-1000
# element grids, named after their axis order.
INPUT_MODES = ("moss", "yxyx", "xyxy")

def read_boxes(data, width, height, mode):
    """Box list in the shape `mode` names -> canonical boxes."""
    if data is None:
        return []
    parsed = _loads(data) if isinstance(data, str) else data
    if parsed is None:
        return []
    if isinstance(parsed, dict) and "__value__" in parsed:
        parsed = parsed["__value__"]
    if mode == "moss":
        return moss_to_boxes(parsed, width, height) if is_moss_layout(parsed) else []
    return _grid_to_boxes(parsed, width, height, "xyxy" if mode == "xyxy" else "yxyx")


def _loads(text):
    try:
        return json.loads(text.lstrip("\ufeff").strip() or "null")
    except ValueError:
        return None


def canvas_dims(text):
    """Frontend "WxH" bookkeeping -> (w, h), or None."""
    parts = str(text or "").replace("*", "x").replace(",", "x").split("x")
    try:
        w, h = int(float(parts[0])), int(float(parts[1]))
    except (IndexError, ValueError):
        return None
    return (w, h) if w > 0 and h > 0 else None


def scale_boxes(boxes, width, height, from_width, from_height):
    """Scale pixel boxes written for another canvas onto this one."""
    sx, sy = width / from_width, height / from_height
    return [{
        "x": round(b["x"] * sx), "y": round(b["y"] * sy),
        "width": max(1, round(b["width"] * sx)), "height": max(1, round(b["height"] * sy)),
        "metadata": b["metadata"],
    } for b in boxes]


def _grid_to_boxes(data, width, height, order):
    """0-1000 [a, b, c, d] in the given axis order -> canonical boxes."""
    if is_moss_layout(data):
        # A MOSS layout prompt is absolute pixels from the canvas centre; reading it
        # as a 0-1000 grid would put the boxes in the wrong place.
        return []
    if isinstance(data, dict):
        data = data.get("items") or [data]
    if not isinstance(data, list):
        return []
    boxes = []
    for item in data:
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox") or item.get("bbox_2d")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        a, b, c, d = (float(v) for v in bbox)
        x1, y1, x2, y2 = (a, b, c, d) if order == "xyxy" else (b, a, d, c)
        x1, x2 = sorted((max(0.0, min(1000.0, x1)), max(0.0, min(1000.0, x2))))
        y1, y2 = sorted((max(0.0, min(1000.0, y1)), max(0.0, min(1000.0, y2))))
        etype = "text" if item.get("label") == "text" or item.get("type") == "text" else "obj"
        boxes.append({
            "x": round(x1 / 1000 * width), "y": round(y1 / 1000 * height),
            "width": max(1, round((x2 - x1) / 1000 * width)),
            "height": max(1, round((y2 - y1) / 1000 * height)),
            "metadata": {"type": etype,
                         "text": str(item.get("text") or "") if etype == "text" else "",
                         "desc": str(item.get("caption") or item.get("desc") or ""),
                         "palette": []},
        })
    return boxes


def is_moss_document(data):
    """True when `data` (or the JSON string holding it) is a MOSS layout prompt."""
    parsed = _loads(data) if isinstance(data, str) else data
    if isinstance(parsed, dict) and "__value__" in parsed:
        parsed = parsed["__value__"]
    return is_moss_layout(parsed)


class MoyouBoxesLayout:
    """Draw boxes on a pixel canvas and output MOSS elements."""

    CATEGORY = CATEGORY
    DESCRIPTION = (
        "在画布上画像素级边界框（字段规则与内置的 Node 2.0「创建边界框」一致，任何前端都能用）。"
        "输出 MOSS/Ideogram 元素：bbox 为 0-1000 归一化的 [ymin, xmin, ymax, xmax]。"
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "width": ("INT", {"default": 1024, "min": 64, "max": 16384, "step": 16,
                                  "tooltip": "画布与输出图宽度（像素）。可改成输入并连线。"}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 16384, "step": 16,
                                   "tooltip": "画布与输出图高度（像素）。可改成输入并连线。"}),
            },
            "optional": {
                "background": ("IMAGE", {"tooltip": "画在框后面的背景图。"}),
                "bboxes": ("BOUNDING_BOX,ARRAY,STRING", {
                    "forceInput": True,
                    "tooltip": "用来初始化画布的框 / 元素 / JSON。上游值变化一次则重置画布，"
                               "不变时画布编辑优先。",
                }),
                "layout": ("STRING", {
                    "default": "[]",
                    "multiline": False,
                    "tooltip": "画布状态（内部字段，勿手动修改）。",
                }),
                "last_incoming": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "内部状态：上一次用来初始化画布的 bboxes 值。",
                }),
                "last_dims": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "内部状态：上一次运行实际用到的画布宽高。宽度/高度接了计算型节点时"
                               "前端读不到值，靠它记住这些框是按哪个画布画的。",
                }),
            },
        }

    FUNCTION = "run"
    RETURN_TYPES = ("IMAGE", "BOUNDING_BOX", "ARRAY")
    RETURN_NAMES = ("preview", "bboxes", "elements")
    OUTPUT_TOOLTIPS = (
        "画布渲染图（压暗背景、编号、描述文字）。",
        "像素框帧：[[{x, y, width, height}, ...]]。",
        "MOSS 元素：{type, bbox:[ymin, xmin, ymax, xmax], text, desc, color_palette}。",
    )
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")

    def run(self, width, height, background=None, bboxes=None, layout="[]", last_incoming="",
            last_dims=""):
        # last_dims is canvas bookkeeping the editor writes back: the size the boxes in
        # layout are written in.
        canvas_boxes = parse_text(layout)
        # A linked width/height the editor cannot evaluate only becomes known when this
        # node runs, so it could not rescale the boxes yet. Do it here and this very run
        # already reports the right elements; the returned layout carries the new values,
        # so the editor never scales them a second time.
        stored = canvas_dims(last_dims)
        if canvas_boxes and stored and stored != (width, height):
            canvas_boxes = scale_boxes(canvas_boxes, width, height, *stored)
            layout = canonical_json(canvas_boxes)
        # Store the exact tuple that arrived: elements are grained to 1000ths, so
        # re-deriving pixels from them would make an unchanged value look new.
        if isinstance(bboxes, list) and bboxes and isinstance(bboxes[0], list) and bboxes[0] and "height" in bboxes[0][0]:
            incoming = frame_to_boxes(bboxes, width, height)
            incoming_is_elements = False
        elif is_moss_document(bboxes):
            # A MOSS layout prompt: absolute pixels from the canvas centre, so it
            # needs this node's canvas size to become boxes.
            incoming = moss_to_boxes(_loads(bboxes) if isinstance(bboxes, str) else bboxes, width, height)
            incoming_is_elements = False
        else:
            incoming = to_boxes(bboxes)
            incoming_is_elements = any(isinstance(i, dict) and "x" not in i and "bbox" in i for i in (bboxes or []))
        applied_text = last_incoming or ""
        incoming_text = canonical_json(incoming) if incoming else ""
        if incoming and applied_text != incoming_text:
            boxes = incoming
            layout_out, incoming_out = incoming_text, incoming_text
        else:
            boxes = canvas_boxes
            layout_out, incoming_out = layout, applied_text

        # Incoming elements live on a 0-1000 grid; converting them with the real
        # canvas size would shrink them, so they keep the 1000-unit frame.
        ew, eh = (1000, 1000) if incoming and incoming_is_elements else (width, height)
        elements = to_elements(boxes, ew, eh)
        preview = render(boxes, width, height, background)
        return {
            # ComfyUI flattens ui values into lists, so text goes in as a one-item list.
            "ui": {"layout": [layout_out], "last_incoming": [incoming_out], "dims": [width, height],
                   "elements": elements},
            "result": (preview, to_bbox_frame(boxes), elements),
        }


class MoyouBoxesVisualizer:
    """Draw boxes described as JSON onto an image (BBoxVisualizer for MOSS elements)."""

    CATEGORY = CATEGORY
    DESCRIPTION = (
        "把边界框画到图上。支持 MOSS 结构化提示词（summary/items，abs_centralized 坐标）、"
        "MOSS elements、编辑器同款 JSON，以及 {bbox_2d: [x1, y1, x2, y2]} 的 0-1000 写法。"
        "不接图像时输出灰底图，只用来核对框位。"
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (list(INPUT_MODES), {
                    "default": INPUT_MODES[0],
                    "tooltip": "如何解读输入：moss = MOSS 结构化提示词（绝对像素、原点在画布中心）；"
                               "yxyx = 0-1000 归一化的 [y1, x1, y2, x2]；xyxy = 0-1000 归一化的 [x1, y1, x2, y2]。",
                }),
                "line_width": ("INT", {"default": 3, "min": 1, "max": 40,
                                       "tooltip": "框线宽度（像素）。"}),
            },
            "optional": {
                # Optional, so the node also works as a pure box checker: without an
                # image the boxes are drawn on a grey canvas of the declared size.
                "image": ("IMAGE", {"tooltip": "底图。不接则输出灰底图，尺寸取画布宽度 / 画布高度。"}),
                "canvas_width": ("INT", {"default": 0, "min": 0, "max": 16384, "step": 16,
                                         "tooltip": "制作提示词时的画布宽度；0 = 用输入图自身的宽度，"
                                                    "没有图像时为 1024。仅 moss 模式需要：它的 bbox 是"
                                                    "相对于该画布中心的绝对像素。"}),
                "canvas_height": ("INT", {"default": 0, "min": 0, "max": 16384, "step": 16,
                                          "tooltip": "制作提示词时的画布高度；0 = 用输入图自身的高度，"
                                                     "没有图像时为 1024。"}),
                "bbox_text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "边界框 JSON：MOSS 结构化提示词、elements、bbox_2d 或像素框均可。",
                }),
                "elements": ("BOUNDING_BOX,ARRAY,STRING", {
                    "forceInput": True,
                    "tooltip": "把边界框接到这里；连线时优先于上方的文本。",
                }),
            },
        }

    FUNCTION = "run"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("IMAGE",)

    def run(self, mode, line_width, image=None, canvas_width=0, canvas_height=0,
            bbox_text="", elements=None):
        # ComfyUI IMAGE is (batch, height, width, channels). Without one the output is
        # a grey canvas, so the box positions can still be checked on their own.
        height = int(image.shape[-3]) if image is not None else (int(canvas_height) or 1024)
        width = int(image.shape[-2]) if image is not None else (int(canvas_width) or 1024)
        data = elements if elements else bbox_text
        # The layout is authored on a specific canvas; 0 means "same as the image".
        cw = int(canvas_width) or width
        ch = int(canvas_height) or height
        boxes = read_boxes(data, cw, ch, mode)
        if not boxes:
            return (image if image is not None else render([], cw, ch),)
        # The boxes are in canvas space; the image may differ, so scale them onto it.
        if (cw, ch) != (width, height):
            sx, sy = width / cw, height / ch
            boxes = [{
                "x": round(b["x"] * sx), "y": round(b["y"] * sy),
                "width": max(1, round(b["width"] * sx)), "height": max(1, round(b["height"] * sy)),
                "metadata": b["metadata"],
            } for b in boxes]
        return (render(boxes, width, height, image, line_width),)


NODE_CLASS_MAPPINGS = {
    "MoyouMossBoxesLayout": MoyouBoxesLayout,
    "MoyouMossBoxesVisNode10": MoyouBoxesVisualizer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoyouMossBoxesLayout": "moyou bbox moss-image layout (Node 1.0)",
    "MoyouMossBoxesVisNode10": "moyou边界框可视化",
}

WEB_DIRECTORY = "./web"
