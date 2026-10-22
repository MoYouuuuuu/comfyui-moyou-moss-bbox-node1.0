"""moyou-moss-bbox-node1.0: MOSS/Ideogram bounding boxes on classic (Node 1.0) nodes.

Two nodes, all inputs/outputs plain built-in types:

- 创建边界框 (Node 1.0): canvas editor. Stores/accepts the classic pixel box
  layout {x, y, width, height, metadata}, outputs MOSS `elements`
  (bbox = [ymin, xmin, ymax, xmax], 0-1000) plus a pixel preview.
- moyou bbox 可视化: draws an elements / bbox_2d / pixel-box JSON back onto an image.

Requires the ComfyUI frontend (>= 1.16) for the editor widget; the nodes
register on any ComfyUI build because nothing depends on the V3 API.
"""

import json

from .bbox_data import canonical_json, frame_to_boxes, parse_text, to_bbox_frame, to_boxes, to_elements
from .render import render

CATEGORY = "moyou"
PLACEHOLDER = "Bounding Boxes (Node 1.0)"


class MoyouBoxesLayout:
    """Draw boxes on a pixel canvas and output MOSS elements."""

    CATEGORY = CATEGORY
    DESCRIPTION = (
        "Draw pixel-space bounding boxes on a canvas (same field rules as the Node 2.0 "
        "Create Bounding Boxes, usable on any frontend). Outputs MOSS/Ideogram elements "
        "with bbox [ymin, xmin, ymax, xmax] in 0-1000."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "width": ("INT", {"default": 1024, "min": 64, "max": 16384, "step": 16,
                                  "tooltip": "Canvas / output image width in pixels."}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 16384, "step": 16,
                                   "tooltip": "Canvas / output image height in pixels."}),
            },
            "optional": {
                "background": ("IMAGE", {"tooltip": "Optional image drawn behind the boxes."}),
                "bboxes": ("BOUNDING_BOX,ARRAY,STRING", {
                    "forceInput": True,
                    "tooltip": "Boxes, elements or JSON used to initialise the canvas. A new upstream "
                               "value initialises it; canvas edits win until that value changes again.",
                }),
                "layout": ("STRING", {
                    "default": "[]",
                    "multiline": False,
                    "tooltip": PLACEHOLDER,
                }),
                "last_incoming": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "Internal canvas state: the bboxes value last used to initialise it.",
                }),
            },
        }

    FUNCTION = "run"
    RETURN_TYPES = ("IMAGE", "BOUNDING_BOX", "ARRAY")
    RETURN_NAMES = ("preview", "bboxes", "elements")
    OUTPUT_TOOLTIPS = (
        "Canvas rendering of the boxes (dimmed background, numbered tags).",
        "Pixel box frame: [[{x, y, width, height}, ...]].",
        "MOSS elements: {type, bbox:[ymin, xmin, ymax, xmax], text, desc, color_palette}.",
    )
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")

    def run(self, width, height, background=None, bboxes=None, layout="[]", last_incoming=""):
        canvas_boxes = parse_text(layout)
        # Store the exact tuple that arrived: elements are grained to 1000ths, so
        # re-deriving pixels from them would make an unchanged value look new.
        if isinstance(bboxes, list) and bboxes and isinstance(bboxes[0], list) and bboxes[0] and "height" in bboxes[0][0]:
            incoming = frame_to_boxes(bboxes, width, height)
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
            "ui": {"layout": layout_out, "last_incoming": incoming_out, "dims": [width, height],
                   "elements": elements},
            "result": (preview, to_bbox_frame(boxes), elements),
        }


class MoyouBoxesVisualizer:
    """Draw boxes described as JSON onto an image (BBoxVisualizer for MOSS elements)."""

    CATEGORY = CATEGORY
    DESCRIPTION = (
        "Draw boxes onto an image. Accepts MOSS elements, boxes in the same JSON text as "
        "the editor, or the legacy {bbox_2d: [x1, y1, x2, y2]} 0-1000 format."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "line_width": ("INT", {"default": 3, "min": 1, "max": 40}),
            },
            "optional": {
                "bbox_text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Elements, bbox_2d boxes or pixel boxes as JSON. Line breaks are welcome.",
                }),
                "elements": ("BOUNDING_BOX,ARRAY,STRING", {
                    "forceInput": True,
                    "tooltip": "Wire the elements output here; overrides bbox_text when connected.",
                }),
            },
        }

    FUNCTION = "run"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("IMAGE",)

    def run(self, image, line_width, bbox_text="", elements=None):
        width, height = image.shape[-2], image.shape[-1]
        boxes = to_boxes(elements) if elements else parse_text(bbox_text)
        if not boxes:
            return (image,)
        return (render(boxes, width, height, image),)


NODE_CLASS_MAPPINGS = {
    "MoyouMossBoxesLayout": MoyouBoxesLayout,
    "MoyouMossBoxesNode10": MoyouBoxesLayout,
    "MoyouMossBoxesVisNode10": MoyouBoxesVisualizer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MoyouMossBoxesLayout": "moyou bbox moss-image layout (Node 1.0)",
    "MoyouMossBoxesNode10": "moyou bbox moss-image layout (Node 1.0)",
    "MoyouMossBoxesVisNode10": "边界框可视化",
}

WEB_DIRECTORY = "./web"
