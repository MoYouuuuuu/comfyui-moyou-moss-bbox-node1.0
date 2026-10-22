# 冒烟脚本

- `e2e.js`：Playwright 打开 `127.0.0.1:8188`，加载含本节点的工作流，校验
  画布挂载 → `+` 加框 → 拖动/选中 → 描述写回 → 执行后 `ui.elements` 回传，并截图 `editor.png`。
- `wf10.json`：脚本使用的工作流（2 个框：text + obj）。
- `editor.png`：编辑器实际外观。

运行（需要 playwright-core + chromium）：

```bash
node e2e.js "G:/ComfyUI-aki-v1.6/ComfyUI/custom_nodes/comfyui-moyou-moss-bbox-node1.0/_smoke"
```
