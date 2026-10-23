"""Node-level checks for the visualizer modes and MOSS layout prompts."""

import json
import sys
import types

sys.path.insert(0, ".")

import torch

# The node module only needs numpy/PIL/torch; stub the ComfyUI import surface it
# does not touch so this runs outside the ComfyUI process.
sys.modules.setdefault("nodes", types.SimpleNamespace())

import importlib.util
from pathlib import Path

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("moyou_bbox", BASE / "__init__.py",
                                             submodule_search_locations=[str(BASE)])
mod = importlib.util.module_from_spec(spec)
sys.modules["moyou_bbox"] = mod
spec.loader.exec_module(mod)

Visualizer = mod.NODE_CLASS_MAPPINGS["MoyouMossBoxesVisNode10"]
Layout = mod.NODE_CLASS_MAPPINGS["MoyouMossBoxesLayout"]

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

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (("  " + str(extra)) if extra else ""))


img = torch.zeros(1, 1024, 1024, 3)
vis = Visualizer()

# --- mode options exposed to the UI ---
required = Visualizer.INPUT_TYPES()["required"]
check("mode option present", "mode" in required, list(required))
check("mode values", required["mode"][0] == ["moss", "yxyx", "xyxy"], required["mode"][0])
check("mode defaults to moss", required["mode"][1]["default"] == "moss")

# --- oss: MOSS layout prompt as a JSON string (what PreviewAny prints) ---
out = vis.run("moss", 3, img, bbox_text=json.dumps(PROMPT, ensure_ascii=False))
check("moss mode draws", tuple(out[0].shape) == (1, 1024, 1024, 3) and not torch.equal(out[0], img))

# as a parsed object on the elements socket
out2 = vis.run("moss", 3, img, elements=PROMPT)
check("moss mode via socket", torch.equal(out[0], out2[0]))

# wrapped as {__value__: ...} like an array widget value
out3 = vis.run("moss", 3, img, elements={"__value__": PROMPT})
check("moss mode unwraps __value__", torch.equal(out[0], out3[0]))

# --- yxyx: the node's own elements output, 0-1000 ---
elements = [{"type": "text", "bbox": [55, 0, 380, 1000], "text": "MOSS", "desc": "banner"}]
o_yx = vis.run("yxyx", 3, img, elements=elements)
check("yxyx mode draws", not torch.equal(o_yx[0], img))

# same box written x-first must land in the same place
elements_xy = [{"type": "text", "bbox": [0, 55, 1000, 380], "text": "MOSS", "desc": "banner"}]
o_xy = vis.run("xyxy", 3, img, elements=elements_xy)
check("xyxy matches yxyx for the transposed box", torch.equal(o_yx[0], o_xy[0]))

# --- wrong mode on the wrong data yields an unmodified image, not a crash ---
o_none = vis.run("moss", 3, img, elements=elements)
check("moss mode ignores element lists", torch.equal(o_none[0], img))
o_none2 = vis.run("xyxy", 3, img, bbox_text=json.dumps(PROMPT))
check("grid mode ignores a layout prompt", torch.equal(o_none2[0], img))

# --- the layout node accepts a MOSS prompt through bboxes ---
lay = Layout()
res = lay.run(1024, 1024, bboxes=json.dumps(PROMPT, ensure_ascii=False))
elements_out = res["result"][2]
check("layout node reads moss prompt", len(elements_out) == 5, len(elements_out))
check("layout node maps caption -> desc",
      elements_out[1]["desc"] == "身着白色蕾丝旗袍的女性", elements_out[1])
check("layout node maps text", elements_out[0]["text"] == "moss")
check("layout node type mapping", [e["type"] for e in elements_out] == ["text", "obj", "text", "text", "text"])
check("layout node ui carries elements", len(res["ui"]["elements"]) == 5)

# --- canvas width / height: the prompt's canvas may differ from the image ---
opt = Visualizer.INPUT_TYPES()["optional"]
check("canvas width/height inputs", "canvas_width" in opt and "canvas_height" in opt, list(opt))
check("canvas size defaults to the image", opt["canvas_width"][1]["default"] == 0
      and opt["canvas_height"][1]["default"] == 0)

widescreen = torch.zeros(1, 1024, 586, 3)          # 586 wide, 1024 tall
prompt_json = json.dumps(PROMPT, ensure_ascii=False)
by_image = vis.run("moss", 3, widescreen, bbox_text=prompt_json)
by_canvas = vis.run("moss", 3, widescreen, canvas_width=1024, canvas_height=1024, bbox_text=prompt_json)
check("width/height change placement", not torch.equal(by_image[0], by_canvas[0]))

# declaring the prompt's own canvas is the same as drawing on an image of that size
square = vis.run("moss", 3, torch.zeros(1, 1024, 1024, 3),
                 canvas_width=1024, canvas_height=1024, bbox_text=prompt_json)
check("explicit canvas matches a same-size image",
      torch.equal(vis.run("moss", 3, img, canvas_width=1024, canvas_height=1024,
                          bbox_text=prompt_json)[0], square[0]))
check("0 keeps the image size", torch.equal(by_image[0], vis.run(
    "moss", 3, widescreen, canvas_width=0, canvas_height=0, bbox_text=prompt_json)[0]))

# --- no image: the boxes still come out, on a grey canvas ---
opt = Visualizer.INPUT_TYPES()["optional"]
check("image is optional", "image" in opt and "image" not in Visualizer.INPUT_TYPES()["required"])

bare = vis.run("moss", 3, bbox_text=prompt_json)[0]
check("no image still returns an IMAGE", bare.shape == (1, 1024, 1024, 3), tuple(bare.shape))
check("no image draws on grey, not black",
      abs(float(bare.min()) - 32 / 255) < 0.01 and float(bare.max()) > 0.5,
      (float(bare.min()), float(bare.max())))
centred = {"summary": {"caption": ""},
           "items": [{"label": "object", "caption": "满画布", "bbox": [-512, -512, 512, 512]}],
           "bbox_coord_space": "abs_centralized", "bbox_format": "yxyx"}
edge = vis.run("moss", 3, bbox_text=json.dumps(centred, ensure_ascii=False))[0]
check("no image: a centred full-canvas box lands on the edges",
      float(edge[0, 0, 0].max()) > 0.4 and float(edge[0, -1, -1].max()) > 0.4)
check("no image, nothing to draw is still an IMAGE",
      vis.run("moss", 3, bbox_text="[]")[0].shape == (1, 1024, 1024, 3))
check("canvas size drives the grey canvas", vis.run(
    "moss", 3, canvas_width=512, canvas_height=256, bbox_text=prompt_json)[0].shape == (1, 256, 512, 3))

# --- line width reaches the renderer ---
plain = {"summary": {"caption": ""},
         "items": [{"label": "object", "bbox": [-512, -512, 512, 512]}],
         "bbox_coord_space": "abs_centralized", "bbox_format": "yxyx"}


def outline(out):
    return int((out[0] > 0.4).sum())


thin = vis.run("moss", 1, bbox_text=json.dumps(plain))[0]
thick = vis.run("moss", 9, bbox_text=json.dumps(plain))[0]
check("line width reaches the renderer", outline(thick) > outline(thin) * 2,
      (outline(thin), outline(thick)))

print("\nALL PASS" if ok else "\nFAILURES PRESENT")
sys.exit(0 if ok else 1)



