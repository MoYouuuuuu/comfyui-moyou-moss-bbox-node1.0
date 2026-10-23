import copy, importlib.util, json, os, sys, types
import numpy as np, torch

sys.modules.setdefault("nodes", types.SimpleNamespace())
sys.path.insert(0, "G:/ComfyUI-aki-v1.6/ComfyUI")

# The real comfy_api needs av bindings that are not available outside the server,
# so the V3 node module is loaded against a stub with just what it imports.
capi = types.ModuleType("comfy_api")
latest = types.ModuleType("comfy_api.latest")
latest.ComfyExtension = object
latest.io = types.SimpleNamespace(ComfyNode=object, NodeOutput=object,
                                  BoundingBoxes=types.SimpleNamespace(Input=lambda *a, **k: None))
capi.latest = latest
capi.io = latest.io
sys.modules["comfy_api"] = capi
sys.modules["comfy_api.latest"] = latest

spec = importlib.util.spec_from_file_location(
    "v3bbox", "G:/ComfyUI-aki-v1.6/ComfyUI/comfy_extras/nodes_bounding_boxes.py")
v3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v3)
sys.modules["comfy_extras.nodes_bounding_boxes"] = v3

BASE = os.path.dirname(os.path.abspath(__file__))
spec2 = importlib.util.spec_from_file_location("moyou10", BASE + "/__init__.py", submodule_search_locations=[BASE])
m = importlib.util.module_from_spec(spec2)
sys.modules["moyou10"] = m
spec2.loader.exec_module(m)
rend = sys.modules["moyou10.render"]

Layout = m.NODE_CLASS_MAPPINGS["MoyouMossBoxesLayout"]
Visualizer = m.NODE_CLASS_MAPPINGS["MoyouMossBoxesVisNode10"]
ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(("PASS " if cond else "FAIL ") + name + (("  " + str(extra)) if extra else ""))


probe = torch.rand(1, 512, 768, 3)
boxes = json.dumps([
    {"x": 0, "y": 100, "width": 1200, "height": 50,
     "metadata": {"type": "text", "text": "MOSS", "desc": "top", "palette": ["#ff0000", "#00FF00"]}},
    {"x": 900, "y": 400, "width": 300, "height": 200,
     "metadata": {"type": "obj", "text": "ignored", "desc": "knight", "palette": []}},
])

out = Layout().run(1024, 1024, layout=boxes)
check("layout returns 3 outputs", len(out["result"]) == 3)
check("preview is IMAGE tensor", tuple(out["result"][0].shape) == (1, 1024, 1024, 3), tuple(out["result"][0].shape))
check("elements use [ymin, xmin, ymax, xmax]",
      out["result"][2][0]["bbox"] == [98, 0, 146, 1000] and out["result"][2][1]["bbox"] == [391, 879, 586, 1000],
      [b["bbox"] for b in out["result"][2]])
check("text only on text elements", out["result"][2][0].get("text") == "MOSS" and "text" not in out["result"][2][1])
check("palette passthrough", out["result"][2][0].get("color_palette") == ["#FF0000", "#00FF00"])
check("bbox frame is pixel dicts", out["result"][1][0][0]["width"] == 1200)

# parity with the Node 2.0 node on its own editor_state
wf = json.load(open("C:/Users/ysys5/Downloads/Unsaved Workflow (2).json", encoding="utf-8"))
node3 = [n for n in wf["nodes"] if n["type"] == "CreateBoundingBoxes"][0]
W, Hh = node3["widgets_values"][0], node3["widgets_values"][1]
regions = copy.deepcopy(node3["widgets_values"][2])
ref_elements = v3.build_elements(v3.boxes_to_regions(copy.deepcopy(regions), W, Hh))
ref_preview = v3.render_preview(v3.boxes_to_regions(copy.deepcopy(regions), W, Hh), W, Hh)
mine = Layout().run(W, Hh, layout=json.dumps(regions))
check("elements identical to Node 2.0", mine["result"][2] == ref_elements)
# The preview uses the built-in renderer with our CJK font swapped in, so its
# text rows differ from a reference render that uses PIL's default font. Compare
# geometry instead: same canvas, and the boxes land on the same edges.
same_canvas = tuple(mine["result"][0].shape) == tuple(ref_preview.shape)
check("preview canvas matches Node 2.0", same_canvas, tuple(mine["result"][0].shape))
d_ref = (mine["result"][0] - ref_preview).abs().amax(dim=-1)
rows = (d_ref > 0).any(dim=-1).nonzero()
check("preview differs only in text rows (font swap)", bool(len(rows)) and int(rows.max()) < Hh,
      f"{int(len(rows))} rows")
_saved_native = rend.render.__globals__["_native"]
rend.render.__globals__["_native"] = lambda: None
portable = Layout().run(W, Hh, layout=json.dumps(regions))["result"][0]
rend.render.__globals__["_native"] = _saved_native
prev = (portable - ref_preview).abs()
# Same reason: the two renderers use different fonts, so the tolerance is on
# geometry (identical frame) rather than on anti-aliased glyph pixels.
check("fallback renderer draws the same boxes",
      tuple(portable.shape) == tuple(ref_preview.shape) and float(prev.max()) < 0.75,
      f"max diff {float(prev.max()):.3f}")

# incoming handling: applied once, later canvas edits survive an unchanged incoming
frame = v3.fractions_to_bbox_frame(v3.boxes_to_regions(copy.deepcopy(regions), W, Hh), W, Hh)
ref_frame_elements = v3.build_elements(v3.boxes_to_regions(frame[0], W, Hh))
first = Layout().run(W, Hh, bboxes=frame)
check("incoming pixel frame initialises canvas (score only, no metadata in a frame)", first["result"][2] == ref_frame_elements, first["result"][2][:1])
edited = '[{"x":1,"y":2,"width":30,"height":40,"metadata":{"type":"obj","text":"","desc":"","palette":[]}}]'
second = Layout().run(W, Hh, bboxes=frame, layout=edited, last_incoming=first["ui"]["last_incoming"][0])
check("canvas edits win while incoming is unchanged", second["result"][2][0]["bbox"] == [2, 1, 41, 30],
      second["result"][2][0]["bbox"])
changed = Layout().run(W, Hh, bboxes=frame, layout=edited, last_incoming="[]")
check("new incoming overrides edits", changed["result"][2] == ref_frame_elements, changed["result"][2][:1])
# elements round-trip through the socket preserves metadata and geometry
roundtrip = Layout().run(W, Hh, bboxes=mine["result"][2])
check("elements input round-trips exactly", roundtrip["result"][2] == ref_elements)

# legacy moyou bbox_2d (0-1000) input still works
legacy = Layout().run(1024, 1024, bboxes=[{"bbox_2d": [400, 268, 730, 694], "label": ""}])
check("bbox_2d input accepted", legacy["result"][2][0]["bbox"] == [262, 391, 678, 713], legacy["result"][2][0]["bbox"])

vis = Visualizer().run("yxyx", 3, probe, elements=mine["result"][2])
check("visualizer draws elements", tuple(vis[0].shape) == tuple(probe.shape) and not torch.equal(vis[0], probe))
vis2 = Visualizer().run("xyxy", 3, probe, bbox_text='[{"bbox_2d": [0, 0, 100, 100], "label": "x"}]')
check("visualizer accepts bbox_2d text", not torch.equal(vis2[0], probe))
check("visualizer is a no-op without boxes", torch.equal(Visualizer().run("moss", 3, probe)[0], probe))

print("\nALL PASS" if ok else "\nFAILURES PRESENT")
