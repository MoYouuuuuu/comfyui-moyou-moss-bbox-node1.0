"""Round-trip check for the MOSS layout prompt support."""

import json
import sys

sys.path.insert(0, ".")

from bbox_data import boxes_to_moss, is_moss_layout, moss_to_boxes, parse_text, to_boxes

# The document from the screenshot: 1024x1024 canvas, abs_centralized, yxyx.
PROMPT = {
    "summary": {"caption": ""},
    "items": [
        {"label": "text", "caption": "大写艺术字绿色", "text": "moss", "bbox": [-624, -416, -371, 416]},
        {"label": "object", "caption": "身着白色蕾丝旗袍的女性", "bbox": [-522, -32, 401, 416]},
        {"label": "text", "caption": "白色隶书书法艺术字大字标题", "text": "半生缘", "bbox": [32, -392, 194, -65]},
        {"label": "text", "caption": "白色小字", "text": "摄影：comfyui", "bbox": [197, -390, 245, -107]},
        {"label": "text", "caption": "白色小字", "text": "出境：moyou", "bbox": [245, -387, 294, -102]},
    ],
    "bbox_coord_space": "abs_centralized",
    "bbox_format": "yxyx",
}

W = H = 1024
ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (("  " + str(extra)) if extra else ""))


check("is_moss_layout", is_moss_layout(PROMPT))

boxes = moss_to_boxes(PROMPT, W, H)
check("item count", len(boxes) == 5, len(boxes))
# item 0: y[-624,-371] x[-416,416] + centre(512,512) -> y[-112,141] x[96,928].
# The top edge is above the canvas, so it is clamped to 0 (same as the upstream
# editor: off-canvas edges are clamped into the canvas).
b0 = boxes[0]
check("item0 pixels", (b0["x"], b0["y"], b0["width"], b0["height"]) == (96, 0, 832, 141),
      (b0["x"], b0["y"], b0["width"], b0["height"]))
check("item0 type text", b0["metadata"]["type"] == "text")
check("item0 text", b0["metadata"]["text"] == "moss")
check("item0 desc <- caption", b0["metadata"]["desc"] == "大写艺术字绿色")
check("item1 type obj", boxes[1]["metadata"]["type"] == "obj")
check("item1 text dropped for obj", boxes[1]["metadata"]["text"] == "")
check("item1 caption kept", boxes[1]["metadata"]["desc"] == "身着白色蕾丝旗袍的女性")

# round trip: in-canvas boxes must come back byte-identical. Item 0 is clamped
# (its original top was off-canvas), so only the in-canvas edges are compared.
doc = boxes_to_moss(boxes, W, H, template=PROMPT)
check("round-trip summary kept", doc["summary"] == PROMPT["summary"])
check("round-trip space/format", (doc["bbox_coord_space"], doc["bbox_format"]) == ("abs_centralized", "yxyx"))
check("round-trip label", [i["label"] for i in doc["items"]] == [i["label"] for i in PROMPT["items"]])
check("round-trip text", [i.get("text") for i in doc["items"]] == [i.get("text") for i in PROMPT["items"]])
check("round-trip caption", [i["caption"] for i in doc["items"]] == [i["caption"] for i in PROMPT["items"]])
# items 2..4 sit fully inside the canvas: they must survive untouched
check("round-trip bbox identical (in-canvas items)",
      [i["bbox"] for i in doc["items"][2:]] == [i["bbox"] for i in PROMPT["items"][2:]],
      [(a["bbox"], b["bbox"]) for a, b in zip(doc["items"][2:], PROMPT["items"][2:])])
# items 0 and 1 stick out past the top / left edge: those edges clamp to the canvas
check("clamped items round-trip as clamped",
      doc["items"][0]["bbox"] == [-512, -416, -371, 416] and doc["items"][1]["bbox"] == [-512, -32, 401, 416],
      [doc["items"][0]["bbox"], doc["items"][1]["bbox"]])

# all in-canvas round trip must be exact
inside = {"summary": {"caption": "c"}, "bbox_coord_space": "abs_centralized", "bbox_format": "yxyx",
          "items": [{"label": "text", "caption": "cap", "text": "T", "bbox": [-100, -50, 120, 300]},
                    {"label": "object", "caption": "o", "bbox": [10, -400, 400, 400]}]}
inside_boxes = moss_to_boxes(inside, W, H)
doc2 = boxes_to_moss(inside_boxes, W, H, template=inside)
check("exact round trip (in-canvas)",
      [i["bbox"] for i in doc2["items"]] == [i["bbox"] for i in inside["items"]],
      [i["bbox"] for i in doc2["items"]])

# xyxy spelling of the same layout
xy = json.loads(json.dumps(PROMPT))
xy["bbox_format"] = "xyxy"
xy["items"] = [{"label": it["label"], "caption": it["caption"],
                "bbox": [it["bbox"][1], it["bbox"][0], it["bbox"][3], it["bbox"][2]],
                **({"text": it["text"]} if "text" in it else {})} for it in PROMPT["items"]]
xy_boxes = moss_to_boxes(xy, W, H)
check("xyxy parses to the same boxes",
      [(b["x"], b["y"], b["width"], b["height"]) for b in xy_boxes] ==
      [(b["x"], b["y"], b["width"], b["height"]) for b in boxes])

# top-left pixel space (no centre offset)
tl = {"summary": {"caption": ""}, "bbox_coord_space": "abs_topleft", "bbox_format": "yxyx",
      "items": [{"label": "object", "caption": "x", "bbox": [100, 200, 300, 400]}]}
tlb = moss_to_boxes(tl, W, H)[0]
check("abs_topleft", (tlb["x"], tlb["y"], tlb["width"], tlb["height"]) == (200, 100, 200, 200),
      (tlb["x"], tlb["y"], tlb["width"], tlb["height"]))

# a plain element list must still go through the old path
elements = [{"type": "text", "bbox": [55, 0, 380, 1000], "text": "MOSS", "desc": "banner"}]
check("plain element list unaffected", to_boxes(elements)[0]["metadata"]["text"] == "MOSS")
check("json string of moss doc", len(parse_text(json.dumps(PROMPT))) == 0,
      "parse_text only handles list-shaped JSON")

print("\nALL PASS" if ok else "\nFAILURES")
sys.exit(0 if ok else 1)
