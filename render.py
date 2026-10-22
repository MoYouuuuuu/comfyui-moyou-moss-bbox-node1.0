"""Preview renderer for moyou-moss-bbox-node1.0.

The Node 2.0 canvas preview style is what users are used to, so when the
built-in `comfy_extras.nodes_bounding_boxes` module is importable we reuse its
renderer (identical pixels); the ported copy below is the fallback for builds
where that module cannot be imported.
"""

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

PREVIEW_LONG_EDGE = 1024
PREVIEW_DIM = 0.25
DEFAULT_COLOR = (140, 140, 140)


def _native():
    try:
        from comfy_extras import nodes_bounding_boxes as native
        return native
    except Exception:
        return None


def render(boxes, width, height, background=None):
    """boxes (canonical pixel layout) -> float32 IMAGE tensor (1, H, W, 3)."""
    native = _native()
    if native is not None:
        def to_fraction(item):
            meta = item["metadata"]
            return {
                "x": item["x"] / (width or 1),
                "y": item["y"] / (height or 1),
                "w": item["width"] / (width or 1),
                "h": item["height"] / (height or 1),
                "type": meta["type"],
                "text": meta["text"],
                "desc": meta["desc"],
                "palette": meta["palette"],
            }

        regions = [to_fraction(item) for item in boxes]
        return native.render_preview(regions, width, height, _background(background))
    return _render_portable(boxes, width, height, background)


def _font(size):
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def hex_to_rgb(value):
    try:
        value = value.lstrip("#")
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except (AttributeError, ValueError):
        return DEFAULT_COLOR


def readable_color(rgb):
    # Same lift-to-readable rule as comfy_extras.color_util.readable_color
    r, g, b = rgb
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum >= 130:
        return (r, g, b)
    t = (130 - lum) / (255 - lum)
    return (round(r + (255 - r) * t), round(g + (255 - g) * t), round(b + (255 - b) * t))


def _wrap(draw, text, font, max_w):
    lines = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            test = word if not line else line + " " + word
            if line and draw.textlength(test, font=font) > max_w:
                lines.append(line)
                line = word
            else:
                line = test
        lines.append(line)
    return lines


def _background(image):
    if image is None:
        return None
    arr = (image[0].detach().cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def _render_portable(boxes, width, height, background):
    bg = _background(background)
    if bg is not None:
        iw, ih = bg.size
        scale = min(1.0, PREVIEW_LONG_EDGE / max(iw, ih))
        rw, rh = max(1, round(iw * scale)), max(1, round(ih * scale))
        base = bg.convert("RGB").resize((rw, rh), Image.LANCZOS)
        img = ImageEnhance.Brightness(base).enhance(PREVIEW_DIM).convert("RGBA")
    else:
        scale = min(1.0, PREVIEW_LONG_EDGE / max(width, height))
        rw, rh = max(1, round(width * scale)), max(1, round(height * scale))
        grey = round(PREVIEW_DIM * 128)
        img = Image.new("RGBA", (rw, rh), (grey, grey, grey, 255))

    overlay = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    fs = max(10, round(rh / 64))
    font = _font(fs)
    tag_font = _font(max(9, fs - 2))
    line_h = fs + 2

    for index, box in enumerate(boxes):
        meta = box["metadata"]
        palette = meta["palette"]
        rgb = hex_to_rgb(palette[0]) if palette else DEFAULT_COLOR
        x1 = max(0, min(rw, round(box["x"] / width * rw)))
        y1 = max(0, min(rh, round(box["y"] / height * rh)))
        x2 = max(0, min(rw, round((box["x"] + box["width"]) / width * rw)))
        y2 = max(0, min(rh, round((box["y"] + box["height"]) / height * rh)))
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1

        draw.rectangle([x1, y1, x2, y2], outline=rgb + (255,), width=2)

        swatches = palette[:5]
        if swatches and (x2 - x1) > 2:
            sh = max(5, fs // 2)
            seg = (x2 - x1) / len(swatches)
            for p, color in enumerate(swatches):
                sx = x1 + round(p * seg)
                draw.rectangle([sx, y1, x1 + round((p + 1) * seg), y1 + sh], fill=hex_to_rgb(color))

        tag = str(index + 1).zfill(2)
        tw = draw.textlength(tag, font=tag_font)
        draw.rectangle([x1, y1, x1 + tw + 6, y1 + fs + 2], fill=rgb + (255,))
        tag_fill = (0, 0, 0, 255) if (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) > 140 else (255, 255, 255, 255)
        draw.text((x1 + 3, y1 + 1), tag, fill=tag_fill, font=tag_font)

        body = meta["desc"] or ""
        if meta["type"] == "text" and meta["text"]:
            body = '"%s"%s' % (meta["text"], " — " + body if body else "")
        if body and (x2 - x1) > 8:
            ty = y1 + fs + 5
            for line in _wrap(draw, body, font, x2 - x1 - 8):
                if ty > y2:
                    break
                draw.text((x1 + 4, ty), line, fill=readable_color(rgb) + (255,), font=font)
                ty += line_h

    composed = Image.alpha_composite(img, overlay).convert("RGB")
    arr = np.asarray(composed, dtype=np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)
