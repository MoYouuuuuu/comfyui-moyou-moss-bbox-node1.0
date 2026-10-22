const { chromium } = require("playwright-core");
const fs = require("fs");
const EXE = "C:/Users/ysys5/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe";
const OUT = process.argv[2];

const layout = JSON.stringify([
  { x: 0, y: 56, width: 1024, height: 333, metadata: { type: "text", text: "MOSS", desc: "top banner", palette: [] } },
  { x: 143, y: 184, width: 778, height: 840, metadata: { type: "obj", text: "", desc: "knight", palette: ["#ff8800", "#44ff88"] } },
]);

const wf = {
  last_node_id: 1, last_link_id: 0,
  nodes: [{
    id: 1, type: "MoyouMossBoxesLayout", pos: [60, 80], size: [640, 760], flags: {}, order: 0, mode: 0,
    inputs: [
      { name: "background", shape: 7, type: "IMAGE", link: null },
      { name: "bboxes", shape: 7, type: "BOUNDING_BOX,ARRAY,STRING", link: null },
    ],
    outputs: [
      { name: "preview", type: "IMAGE", links: [] },
      { name: "bboxes", type: "BOUNDING_BOX", links: [] },
      { name: "elements", type: "ARRAY", links: [] },
    ],
    properties: { "Node name for S&R": "MoyouMossBoxesLayout" },
    widgets_values: [1024, 1024, layout, ""],
  }],
  links: [], groups: [], config: {}, extra: {}, version: 0.4,
};

const frame = (page) => page.evaluate(() => {
  const app = window.comfyAPI.app.app;
  const n = app.graph._nodes.find((x) => /MoyouMoss/.test(x.type));
  if (!n) return { node: false, types: app.graph._nodes.map((x) => x.type) };
  const st = window.__moyou10Editors.get(n);
  const cv = st?.editor?.canvas?.getBoundingClientRect();
  return {
    node: true,
    canvasWidgets: (n.widgets || []).filter((w) => w.isMoyouCanvas).length,
    size: [n.size[0], n.size[1]],
    layoutLen: String(n.widgets.find((w) => w.name === "layout")?.value ?? "").length,
    boxes: JSON.parse(String(n.widgets.find((w) => w.name === "layout")?.value ?? "[]")).length,
    canvas: cv && cv.width > 0 ? [Math.round(cv.x), Math.round(cv.y), Math.round(cv.width), Math.round(cv.height)] : null,
  };
});

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ["--no-sandbox", "--disable-gpu"] });
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e).slice(0, 120)));
  await page.goto("http://127.0.0.1:8188", { waitUntil: "load" });
  await page.waitForFunction(() => window.comfyAPI?.app?.app?.graph, null, { timeout: 60000 });
  await page.waitForTimeout(2500);
  fs.writeFileSync(OUT + "/wf10.json", JSON.stringify(wf));
  await page.addScriptTag({ content: `window.__wf = ${JSON.stringify(wf)};` });
  await page.evaluate(async () => {
    const app = window.comfyAPI.app.app;
    for (const n of [...app.graph._nodes]) app.graph.remove(n);
    await new Promise((r) => setTimeout(r, 800));
    await app.loadGraphData(window.__wf);
  });
  await page.waitForTimeout(1200);

  let f = null;
  for (let i = 0; i < 12; i++) {
    f = await frame(page);
    if (f.canvas) break;
    await page.waitForTimeout(250);
  }
  console.log("FRAME", JSON.stringify(f));
  if (!f.canvas) { console.log("NO CANVAS"); await browser.close(); return; }

  const [x, y, w, h] = f.canvas;
  await page.screenshot({ path: OUT + "/v3_loaded.png" });
  const recheck = await frame(page);
  console.log("RECHECK", JSON.stringify(recheck));
  if (recheck.layoutLen < 3) { console.log("LAYOUT LOST AFTER MOUNT"); await browser.close(); return; }

  // select the first box and give it text + desc via DOM inputs
  // + adds a centred box (toolbar button, avoids blank-click semantics)
  await page.evaluate(() => {
    const app = window.comfyAPI.app.app;
    const n = app.graph._nodes.find((x) => /MoyouMoss/.test(x.type));
    const st = window.__moyou10Editors.get(n);
    st.editor.container.querySelector("button").click();
  });
  await page.waitForTimeout(250);
  const cnt = await page.evaluate(() => {
    const app = window.comfyAPI.app.app;
    const n = app.graph._nodes.find((x) => /MoyouMoss/.test(x.type));
    return JSON.parse(n.widgets.find((w) => w.name === "layout").value).length;
  });
  console.log("AFTER +", cnt);
  const cnt2 = await page.evaluate(() => {
    const app = window.comfyAPI.app.app;
    const n = app.graph._nodes.find((x) => /MoyouMoss/.test(x.type));
    const st = window.__moyou10Editors.get(n);
    return { widget: JSON.parse(n.widgets.find((w) => w.name === "layout").value).length, status: st.editor.container.querySelector("div:last-child").textContent };
  });
  console.log("STATE AFTER +", JSON.stringify(cnt2));
  // select the added box (centred, 20% size) and move it a bit
  await page.mouse.click(x + w * 0.5, y + h * 0.5);
  await page.waitForTimeout(200);
  await page.mouse.move(x + w * 0.5, y + h * 0.5);
  await page.mouse.down();
  await page.mouse.move(x + w * 0.62, y + h * 0.58, { steps: 6 });
  await page.mouse.up();
  await page.waitForTimeout(200);
  const inputInfo = await page.evaluate(() => {
    const app = window.comfyAPI.app.app;
    const n = app.graph._nodes.find((x) => /MoyouMoss/.test(x.type));
    const st = window.__moyou10Editors.get(n);
    const inputs = [...st.editor.container.querySelectorAll("input,textarea,select")];
    return inputs.map((el, i) => ({ i, tag: el.tagName, type: el.type, ph: el.placeholder || el.title || "", disabled: el.disabled }));
  });
  console.log("INPUTS", JSON.stringify(inputInfo));
  // desc input = the placeholder 「描述 desc」
  const descSel = await page.evaluate(() => {
    const app = window.comfyAPI.app.app;
    const n = app.graph._nodes.find((x) => /MoyouMoss/.test(x.type));
    const st = window.__moyou10Editors.get(n);
    const el = st.editor.container.querySelector('input[placeholder="描述 desc"]');
    const r = el.getBoundingClientRect();
    return [r.x + r.width / 2, r.y + r.height / 2];
  });
  await page.mouse.click(descSel[0], descSel[1]);
  await page.keyboard.type("edited desc");
  await page.waitForTimeout(200);
  const afterEdit = await page.evaluate(() => {
    const app = window.comfyAPI.app.app;
    const n = app.graph._nodes.find((x) => /MoyouMoss/.test(x.type));
    const boxes = JSON.parse(n.widgets.find((w) => w.name === "layout").value);
    return { count: boxes.length, metas: boxes.map((b) => b.metadata.desc || b.metadata.text || "") };
  });
  console.log("EDITED META", JSON.stringify(afterEdit));
  await page.screenshot({ path: OUT + "/v3_edited.png" });

  // run
  const q = await page.evaluate(async () => {
    const prompt = await window.comfyAPI.app.app.graphToPrompt();
    const res = await fetch("/prompt", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt: prompt.output, client_id: "v3c" }) });
    return await res.json();
  });
  let hist = null;
  for (let i = 0; i < 30 && !hist; i++) {
    await page.waitForTimeout(400);
    hist = await page.evaluate(async (id) => { const j = await (await fetch(`/history/${id}`)).json(); return j[id] || null; }, q.prompt_id);
  }
  if (hist) {
    const out = hist.outputs?.["1"] || {};
    console.log("RUN", hist.status?.status_str, "elements:", JSON.stringify(out.elements || []).slice(0, 400));
  } else {
    console.log("NO HISTORY", JSON.stringify(q).slice(0, 160));
  }
  await page.waitForTimeout(600);
  console.log("AFTER RUN", JSON.stringify(await frame(page)));
  console.log("ERRS", errs.filter((e) => /TypeError|moyou/i.test(e)).slice(0, 3));
  await browser.close();
})().catch((e) => { console.error("FAILED", e); process.exit(1); });
