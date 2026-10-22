import { app } from "/scripts/app.js";
import { createBoxEditor } from "./editorUI.js";

// Box editor for 创建边界框 (Node 1.0) / MoyouMossBoxesNode10.
//
// The panel is the same stacked layout the built-in node shows under Nodes 2.0
// (see editorUI.js): toolbar -> canvas -> obj|文本 -> 文本 -> 描述 -> 调色板.
//
// Data and output rules follow the built-in CreateBoundingBoxes:
//   internal: {x, y, width, height, metadata: {type, text, desc, palette}}   (pixels)
//   elements: {type, bbox: [ymin, xmin, ymax, xmax], text, desc, color_palette}  (0-1000)

const NODE_TYPES = new Set(["MoyouMossBoxesNode10", "MoyouMossBoxesLayout"]);

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

function localizeSlots(node) {
    let changed = false;
    for (const input of node.inputs ?? []) {
        const label = INPUT_LABELS[input.name];
        if (label && input.localized_name !== label) {
            input.localized_name = label;
            changed = true;
        }
    }
    for (const output of node.outputs ?? []) {
        const label = OUTPUT_LABELS[output.name];
        if (label && output.localized_name !== label) {
            output.localized_name = label;
            changed = true;
        }
    }
    // Widgets (width / height) are drawn from their own `label`.
    for (const widget of node.widgets ?? []) {
        const label = INPUT_LABELS[widget.name];
        if (label && widget.label !== label) {
            widget.label = label;
            changed = true;
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
            Number(node.widgets?.find((w) => w.name === "width")?.value) || 1024,
            Number(node.widgets?.find((w) => w.name === "height")?.value) || 1024,
        ],
        onChange: () => {
            app.graph?.setDirtyCanvas?.(true, true);
        },
    });

    // layout / last_incoming stay serialised but are hidden from the node body.
    for (const name of ["layout", "last_incoming"]) {
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
            if (editor) {
                if (typeof payload.layout === "string") {
                    const w = layoutWidget(this);
                    if (w) w.value = payload.layout;
                    editor.reload();
                }
                const last = this.widgets?.find((w) => w.name === "last_incoming");
                if (last && typeof payload.last_incoming === "string") last.value = payload.last_incoming;
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
