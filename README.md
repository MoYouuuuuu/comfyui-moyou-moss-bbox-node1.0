# comfyui-moyou-moss-bbox-node1.0

**在 ComfyUI 的 Node 1.0（经典画布）上画 MOSS 边界框。**

ComfyUI 内置的「创建边界框 / Create Bounding Boxes」是 Node 2.0 节点——它的画布只由 Nodes 2.0 渲染器提供，
在经典画布下只剩一行 `Bounding Boxes：仅限 Node 2.0`，无法画框。

本插件把**同一套数据规则**（相同的 `editor_state` 结构、相同的 `elements` 输出格式）搬到一个经典节点里，
配上完整的可视化编辑器。数据与内置节点逐位兼容，可以互相替换。

![Node 1.0 节点与内置节点对照](_shots/node10_semi_life.jpg)

---

## 特性

- **MOSS / Ideogram 元素输出**：`elements` 的 `bbox` 为 `[ymin, xmin, ymax, xmax]`，0–1000 归一化，与内置节点逐位相同
- **完整画布编辑器**：拖拽新建 / 移动 / 8 手柄缩放，框内实时显示文本与描述
- **元数据编辑**：类型（物体 / 文本）、文本、描述、最多 5 个调色板颜色
- **实时预览**：`preview` 输出画布渲染图（压暗背景 + 编号 + 描述文字），可直接接「预览图像」
- **上游初始化**：`bboxes` 输入可接像素框、`bbox_2d`、`elements` 或 JSON，上游变化时画布自动同步
- **全中文界面**：输入、输出、面板均为中文，内部字段名保持不变，旧工作流兼容
- **零额外依赖**：只用 ComfyUI 自带的 torch / PIL / numpy

## 安装

### 方式一：ComfyUI-Manager

搜索 `comfyui-moyou-moss-bbox-node1.0` 安装，或使用「通过 Git URL 安装」填入本仓库地址。

### 方式二：手动

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/MoYouuuuuu/comfyui-moyou-moss-bbox-node1.0.git
```

然后**重启 ComfyUI**（新的 Python 节点与 `object_info` 只在启动时加载），刷新浏览器页面。

### 环境要求

| 项目 | 要求 |
| --- | --- |
| ComfyUI | 带有 `editor_state` / `elements` 内置节点（约 0.3.x 之后），本插件在 **0.42.0** 上验证 |
| Python | 3.10+（无第三方依赖） |
| 前端 | 需要支持 DOM widget 的版本（经典画布 / Nodes 2.0 均可），本插件在 **frontend 1.57.1** 上验证 |

## 使用

1. 双击画布空白处，搜索 **moyou** 或 `Node 1.0`，添加 **moyou bbox moss-image layout (Node 1.0)**（分类 `moyou`）
2. 设置 `宽度` / `高度`（默认 1024×1024）
3. 在画布上拖拽画框；选中框后，在下方编辑类型、文本、描述、调色板
4. 把 `元素` 接到 MOSS 图像节点的元素输入，或把 `预览图` 接到「预览图像 / 保存图像」

仓库内附带完整示例工作流：
[`moss_image_区域控制-node1.0适配-t2i工作流.json`](moss_image_%E5%8C%BA%E5%9F%9F%E6%8E%A7%E5%88%B6-node1.0%E9%80%82%E9%85%8D-t2i%E5%B7%A5%E4%BD%9C%E6%B5%81.json)
（`MOSSImageLayoutPrompt` + 本插件 + Flux sampling），可直接拖入 ComfyUI 打开。

### 操作速查

| 操作 | 说明 |
| --- | --- |
| 空白处拖拽 | 新建框 |
| 拖框内部 | 移动 |
| 拖四角 / 四边中点 | 缩放（8 个手柄） |
| 方向键 / Shift + 方向键 | 微移 1px / 10px |
| Delete / Backspace | 删除选中框 |
| 工具栏 `＋` / `－` / `⟲ 全部清除` | 居中加框 / 删选中 / 清空 |
| 工具栏「网格」 | 显示 / 隐藏点阵网格 |

页面左上角的状态栏实时显示：`框数量 · 选中编号 · 宽×高 @ (x, y) · 网格坐标`。

## 节点

### moyou bbox moss-image layout (Node 1.0)

节点 ID：`MoyouMossBoxesNode10` / `MoyouMossBoxesLayout`（同一节点的两个别名，便于搜索）

| 输入 | 类型 | 说明 |
| --- | --- | --- |
| `宽度` / `高度` | INT | 画布与输出图尺寸，默认 1024×1024 |
| `背景图`（可选） | IMAGE | 画布与预览的背景图 |
| `边界框输入`（可选） | BOUNDING_BOX / ARRAY / STRING | 初始化画布；上游值变化一次则重置画布，不变时画布编辑优先 |

| 输出 | 类型 | 内容 |
| --- | --- | --- |
| `预览图` | IMAGE | 画布渲染图（压暗背景、编号、描述文字） |
| `边界框` | BOUNDING_BOX | 像素框帧 `[[{x, y, width, height}, ...]]` |
| `元素` | ARRAY | MOSS elements：`{"type", "bbox", "text", "desc", "color_palette"}` |

### 边界框可视化

节点 ID：`MoyouMossBoxesVisNode10`

把 `elements` / `bbox_2d` / 像素框 JSON 画回一张图片上，用于快速核对结果。

## 数据格式

画布内部数据结构与内置节点的 `editor_state` **完全一致**，单位为像素：

```json
{
  "x": 143, "y": 184, "width": 778, "height": 840,
  "metadata": { "type": "obj", "text": "", "desc": "knight", "palette": ["#FF8800"] }
}
```

输出的 `elements` 中，`bbox` 为 **0–1000 归一化、y 在前** 的 `[ymin, xmin, ymax, xmax]`：

```json
{ "type": "text", "bbox": [55, 0, 380, 1000], "text": "MOSS", "desc": "top banner" }
```

> ⚠️ 与 `MoyouBBoxVis` 的 `bbox_2d`（`[x1, y1, x2, y2]`，0–1000）是两种不同的坐标排列：
> `bbox_2d` 的第三、四值是右下角坐标。直接喂给 `边界框输入` 时会按画布尺寸换算成像素。

## 兼容性说明

- 本插件**只注册自己的节点**，不修改、不接管任何 ComfyUI 内置节点
- 界面上的中文只是**显示名**（`localized_name` / `label`），内部字段名保持 `background` / `bboxes` / `width` / `height`，
  因此已有工作流与 API 调用完全兼容
- 与内置的同款节点可以在同一工作流中混用，两者的 `elements` 输出格式一致

## 已知限制

- 每个框最多 5 个调色板颜色（与内置节点一致）
- 画布最多按 0–1000 网格交互，超长边（>16384px）的框会按比例取整
- `layout` / `last_incoming` 两个内部 widget 已隐藏，用于保存画布状态，请勿手动修改

## 致谢

- 编辑器交互参考 ComfyUI-MoyouBBoxVis 的 "moyou bbox editor"
- 布局与数据规则对齐 ComfyUI 内置的 `CreateBoundingBoxes`（Node 2.0）

## 许可

[MIT](LICENSE)
