import { app } from "/scripts/app.js";
import { createBoxEditor } from "./editorUI.js";

// Box editor for 创建边界框 (Node 1.0) / MoyouMossBoxesLayout.
//
// The panel is the same stacked layout the built-in node shows under Nodes 2.0
// (see editorUI.js): toolbar -> canvas -> obj|文本 -> 文本 -> 描述 -> 调色板.
//
// Data and output rules follow the built-in CreateBoundingBoxes:
//   internal: {x, y, width, height, metadata: {type, text, desc, palette}}   (pixels)
//   elements: {type, bbox: [ymin, xmin, ymax, xmax], text, desc, color_palette}  (0-1000)

const NODE_TYPES = new Set(["MoyouMossBoxesLayout"]);
const VIS_TYPE = "MoyouMossBoxesVisNode10";

// Display names only: the internal `name` stays as-is, so existing workflows and
// the prompt payload keep working. The classic renderer prefers `label`, then
// `localized_name`, then `name`.
const INPUT_LABELS = {
    background: "背景图",
    bboxes: "边界框输入",
    width: "宽度",
    height: "高度",
};

const OUTPUT_LABELS = {
    preview: "预览图",
    bboxes: "边界框",
    elements: "元素",
};

// The visualizer labels inputs, outputs and widgets by hand because its names are
// the ones the backend uses (image / mode / line_width / ...).
const VIS_INPUT_LABELS = {
    image: "图像",
    mode: "模式",
    line_width: "线宽",
    canvas_width: "画布宽度",
    canvas_height: "画布高度",
    bbox_text: "边界框文本",
    elements: "边界框输入",
};

const VIS_OUTPUT_LABELS = {
    IMAGE: "图像",
};

// Dropdown text only; the widget value stays the raw mode string.
const VIS_MODE_LABELS = {
    moss: "moss（结构化提示词）",
    yxyx: "yxyx（y1 x1 y2 x2）",
    xyxy: "xyxy（x1 y1 x2 y2）",
};

function localizeSlots(node) {
    const inputs = node.comfyClass === VIS_TYPE ? VIS_INPUT_LABELS : INPUT_LABELS;
    const outputs = node.comfyClass === VIS_TYPE ? VIS_OUTPUT_LABELS : OUTPUT_LABELS;
    let changed = false;
    for (const input of node.inputs ?? []) {
        const label = inputs[input.name];
        if (label && input.localized_name !== label) {
            input.localized_name = label;
            changed = true;
        }
    }
    for (const output of node.outputs ?? []) {
        const label = outputs[output.name] ?? inputs[output.name];
        if (label && output.localized_name !== label) {
            output.localized_name = label;
            changed = true;
        }
    }
    // Widgets (width / height) are drawn from their own `label`.
    for (const widget of node.widgets ?? []) {
        const label = inputs[widget.name];
        if (label && widget.label !== label) {
            widget.label = label;
            changed = true;
        }
    }
    // The mode dropdown is drawn on the canvas, so its option text cannot be
    // relabelled; show the Chinese meaning next to it instead.
    if (node.comfyClass === VIS_TYPE) {
        const mode = node.widgets?.find((w) => w.name === "mode");
        if (mode && mode.value) {
            const hint = VIS_MODE_LABELS[mode.value];
            if (hint && mode.label !== `模式：${hint}`) {
                mode.label = `模式：${hint}`;
                changed = true;
            }
        }
    }
    if (changed) app.graph?.setDirtyCanvas?.(true, true);
    return changed;
}
const DOM_WIDGET = "moyou_bbox_canvas";
const EDITORS = new WeakMap();
window.__moyou10Editors = EDITORS;

function layoutWidget(node) {
    return node.widgets?.find((w) => w.name === "layout");
}

// width / height are widgets that may also be driven by a link. The canvas has to
// draw in the size the node will actually run with, so read through the link.
function sizeOf(node, name, fallback) {
    // A node that is being cloned or serialised is briefly detached from its graph,
    // and reading a link throws then. Use the plain values for that window.
    const index = node.graph ? (node.inputs ?? []).findIndex((slot) => slot.name === name) : -1;
    const linked = index < 0 ? null : upstreamValue(node, index);
    if (linked) return linked;
    if (index >= 0 && isLinked(node, index)) {
        // A source the client cannot read (e.g. 图像尺寸 without widgets): use the
        // size the backend reported on the last run.
        const reported = node.__moyouRealDims;
        if (reported) return name === "width" ? reported[0] : reported[1];
    }
    const value = Number(node.widgets?.find((w) => w.name === name)?.value);
    return Number.isFinite(value) && value > 0 ? value : fallback;
}

function isLinked(node, index) {
    return node.isInputConnected ? node.isInputConnected(index) : node.inputs[index].link != null;
}

// The frontend never resolves a link to a value; only the origin node knows it.
// A literal INT source keeps the number in its only numeric widget, which is what
// a Primitive dragged off 宽度 looks like.
function upstreamValue(node, index) {
    const graph = node.graph ?? app.graph;
    const link = node.getInputLink ? node.getInputLink(index) : null;
    const origin = graph.getNodeById?.((link ?? graph.links?.get?.(node.inputs[index].link))?.origin_id);
    if (!origin) return null;
    const numbers = (origin.widgets ?? [])
        .map((w) => [w.name, Number(w.value)])
        .filter(([, value]) => Number.isFinite(value) && value > 0);
    if (numbers.length === 1) return numbers[0][1];
    const named = numbers.find(([name]) => name === "value" || name === "int");
    return named ? named[1] : null;
}

// The canvas size the boxes are written in, remembered in the workflow: a linked
// width/height the client cannot evaluate only becomes known after a run, and the
// boxes must not be rescaled a second time when the workflow is reopened.
function savedDims(node) {
    const raw = String(node.widgets?.find((w) => w.name === "last_dims")?.value ?? "");
    const [w, h] = raw.split(/[x*,\s]+/).map(Number);
    return w > 0 && h > 0 ? [w, h] : null;
}

function ensureEditor(node) {
    const existing = EDITORS.get(node);
    if (existing) return existing;
    if (!layoutWidget(node)) return null;

    const editor = createBoxEditor({
        getBoxes: () => layoutWidget(node)?.value,
        setBoxes: (boxes) => {
            const w = layoutWidget(node);
            if (!w) return;
            w.value = JSON.stringify(boxes);
            app.graph?.setDirtyCanvas?.(true, true);
        },
        getDims: () => [
            sizeOf(node, "width", 1024),
            sizeOf(node, "height", 1024),
        ],
        onChange: () => {
            app.graph?.setDirtyCanvas?.(true, true);
        },
    });

    // layout / last_incoming / last_dims stay serialised but are hidden from the node.
    for (const name of ["layout", "last_incoming", "last_dims"]) {
        const w = node.widgets.find((x) => x.name === name);
        if (w) {
            w.hidden = true;
            w.computeSize = () => [0, -4];
        }
    }

    let widget = node.widgets.find((w) => w.isMoyouCanvas);
    if (!widget) {
        widget = node.addDOMWidget(DOM_WIDGET, "MoyouBBoxCanvas", editor.container, {
            hideOnZoom: false,
            serialize: false,
            getMinHeight: () => 560,
            getValue: () => String(layoutWidget(node)?.value ?? "[]"),
            setValue: (v) => {
                const w = layoutWidget(node);
                if (w) w.value = typeof v === "string" ? v : JSON.stringify(v ?? []);
                editor.reload();
            },
        });
        widget.serialize = false;
        widget.isMoyouCanvas = true;
    } else {
        widget.element = editor.container;
    }

    node.size[0] = Math.max(node.size[0] || 0, 430);
    node.size[1] = Math.max(node.size[1] || 0, 700);
    EDITORS.set(node, editor);
    editor.reload();
    requestAnimationFrame(() => editor.draw());
    return editor;
}

// The visualizer has no canvas editor, it only needs the Chinese labels.
app.registerExtension({
    name: "Moyou.BuiltinVisLabels",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== VIS_TYPE) return;

        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = created ? created.apply(this, arguments) : undefined;
            localizeSlots(this);
            return r;
        };

        const configured = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = configured ? configured.apply(this, arguments) : undefined;
            localizeSlots(this);
            return r;
        };

        const drawn = nodeType.prototype.onDrawBackground;
        nodeType.prototype.onDrawBackground = function () {
            const r = drawn ? drawn.apply(this, arguments) : undefined;
            localizeSlots(this);
            return r;
        };
    },
});

app.registerExtension({
    name: "Moyou.MossBoxesNode10",

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!NODE_TYPES.has(nodeData.name)) return;

        // The definition is already available here, so the labels can be applied
        // before the first paint.
        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = originalOnNodeCreated ? originalOnNodeCreated.apply(this, arguments) : undefined;
            localizeSlots(this);
            return r;
        };

        const mount = (node) => {
            if (!layoutWidget(node)) return;
            // A reopened workflow knows the size its boxes are written in.
            const dims = savedDims(node);
            if (dims) node.__moyouRealDims = dims;
            localizeSlots(node);
            ensureEditor(node);
            requestAnimationFrame(() => EDITORS.get(node)?.draw());
        };

        const onAdded = nodeType.prototype.onAdded;
        nodeType.prototype.onAdded = function () {
            const r = onAdded ? onAdded.apply(this, arguments) : undefined;
            mount(this);
            return r;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            mount(this);
            return r;
        };

        const onDrawBackground = nodeType.prototype.onDrawBackground;
        nodeType.prototype.onDrawBackground = function () {
            const r = onDrawBackground ? onDrawBackground.apply(this, arguments) : undefined;
            localizeSlots(this);
            if (!ensureEditor(this)) return r;
            const editor = EDITORS.get(this);
            if (editor && !editor.container.isConnected) {
                const host = this.widgets?.find((w) => w.isMoyouCanvas);
                if (host) host.element = editor.container;
            }
            // The canvas size is the coordinate frame: when it changes (typed, or
            // switched by a link), the stored pixel values scale with it, so every box
            // keeps its place and size relative to the canvas.
            if (editor) {
                const dims = [sizeOf(this, "width", 1024), sizeOf(this, "height", 1024)]
                    .map((v) => Math.max(16, Math.round(v)));
                const size = `${dims[0]}x${dims[1]}`;
                if (this.__moyouDims !== size) {
                    const previous = this.__moyouDims ? this.__moyouDims.split("x").map(Number) : null;
                    this.__moyouDims = size;
                    requestAnimationFrame(() => {
                        if (EDITORS.get(this) !== editor) return;
                        // The first sighting only records the baseline: a workflow loads
                        // with its boxes already written in that space.
                        if (previous) editor.rescale(previous, dims);
                        else editor.refresh();
                        // The boxes are written for this canvas now, so the backend must
                        // not scale them again.
                        const stored = this.widgets?.find((w) => w.name === "last_dims");
                        if (stored && (previous || !stored.value)) stored.value = size;
                        editor.draw();
                    });
                }
            }
            return r;
        };

        const onResize = nodeType.prototype.onResize;
        nodeType.prototype.onResize = function () {
            const r = onResize ? onResize.apply(this, arguments) : undefined;
            requestAnimationFrame(() => EDITORS.get(this)?.draw());
            return r;
        };

        const onWidgetChanged = nodeType.prototype.onWidgetChanged;
        nodeType.prototype.onWidgetChanged = function () {
            const r = onWidgetChanged ? onWidgetChanged.apply(this, arguments) : undefined;
            const editor = EDITORS.get(this);
            if (editor) requestAnimationFrame(() => editor.refresh());
            return r;
        };

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const r = onExecuted ? onExecuted.apply(this, arguments) : undefined;
            const editor = EDITORS.get(this);
            const payload = message || {};
            // The backend knows the size it really ran with; a linked width/height that
            // cannot be read on the client is applied from here, and stored so the boxes
            // are not rescaled again next time the workflow is opened.
            if (Array.isArray(payload.dims) && payload.dims.length >= 2) {
                const w = Number(payload.dims[0]) || 0;
                const h = Number(payload.dims[1]) || 0;
                if (w > 0 && h > 0) {
                    // The boxes arrived written for `before`; when that is another canvas
                    // the backend already scaled them, so the editor must not repeat it.
                    const before = savedDims(this);
                    this.__moyouRealDims = [w, h];
                    const stored = this.widgets?.find((x) => x.name === "last_dims");
                    if (stored) stored.value = `${w}x${h}`;
                    if (before && (before[0] !== w || before[1] !== h)) this.__moyouDims = `${w}x${h}`;
                }
            }
            if (editor) {
                // ComfyUI flattens every ui value into a list, so a string arrives as [str].
                const layout = Array.isArray(payload.layout) ? payload.layout[0] : payload.layout;
                if (typeof layout === "string") {
                    const w = layoutWidget(this);
                    if (w) w.value = layout;
                    editor.reload();
                }
                const incoming = Array.isArray(payload.last_incoming)
                    ? payload.last_incoming[0] : payload.last_incoming;
                const last = this.widgets?.find((w) => w.name === "last_incoming");
                if (last && typeof incoming === "string") last.value = incoming;
            }
            return r;
        };

        const onRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            const editor = EDITORS.get(this);
            if (editor) {
                editor.destroy();
                EDITORS.delete(this);
            }
            return onRemoved ? onRemoved.apply(this, arguments) : undefined;
        };
    },
});
