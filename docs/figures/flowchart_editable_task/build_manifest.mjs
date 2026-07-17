import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const taskDir = path.dirname(fileURLToPath(import.meta.url));
const manifestPath = path.join(taskDir, "manifest.json");

const C = {
  bg: "#F7F8FA",
  paper: "#FFFFFF",
  ink: "#182230",
  muted: "#667085",
  line: "#475467",
  hair: "#D0D5DD",
  data: "#E9EEF5",
  stage1: "#EAF2FB",
  stage1Stroke: "#3778A6",
  stage2: "#EAF6F2",
  stage2Stroke: "#2E7D6B",
  output: "#F1EFF8",
  outputStroke: "#6D5BA6",
  review: "#FFF3D8",
  reviewStroke: "#A46A10",
  neutral: "#F2F4F7",
};

const elements = [];
const add = (el) => elements.push({ decision: "redraw", review_status: "verified", ...el });

function rect(id, x, y, w, h, fill, stroke = "none", stroke_width = 0, rx = 14, layer = "sections") {
  add({ type: "rect", id, x, y, w, h, fill, stroke, stroke_width, rx, layer });
}

function text(id, x, y, value, font_size, fill = C.ink, font_weight = "400", anchor = "middle", layer = "texts") {
  const item = { type: "text", id, x, y, font_size, fill, font_weight, text_anchor: anchor, font_family: "Microsoft YaHei", layer, decision: "retype", review_status: "verified" };
  if (Array.isArray(value)) item.lines = value;
  else item.text = value;
  elements.push(item);
}

function node(id, x, y, w, h, lines, fill, stroke, fs = 19, weight = "600") {
  rect(`${id}-box`, x, y, w, h, fill, stroke, 2.2, 14, "sections");
  const lineGap = fs * 1.25;
  const total = (lines.length - 1) * lineGap;
  const baseline = y + h / 2 - total / 2 + fs * 0.34;
  text(`${id}-text`, x + w / 2, baseline, lines, fs, C.ink, weight);
}

function arrow(id, d, dashed = false) {
  add({ type: "path", id, d, fill: "none", stroke: C.line, stroke_width: 2.5, dasharray: dashed ? "8 6" : undefined, arrow_end: true, layer: "connectors" });
}

function line(id, x1, y1, x2, y2, color = C.hair, width = 1.5) {
  add({ type: "line", id, x1, y1, x2, y2, stroke: color, stroke_width: width, layer: "panels" });
}

// Canvas and title block.
rect("canvas-bg", 0, 0, 1600, 900, C.bg, "none", 0, 0, "background");
text("title", 56, 58, "DTA 制度型开放条款编码与指标构建流程", 44, C.ink, "700", "start");
text("subtitle", 56, 98, "当前正式口径：Stage 1 双模型识别与仲裁；Stage 2 双模型交叉验证与冲突仲裁", 20, C.muted, "400", "start");
line("title-rule", 56, 122, 1544, 122, C.hair, 1.5);

// Stage lanes.
const lanes = [
  ["data", 50, 145, 200, 565, C.data, "01  数据准备"],
  ["stage1", 270, 145, 420, 565, C.stage1, "02  Stage 1｜制度型开放识别"],
  ["stage2", 710, 145, 560, 565, C.stage2, "03  Stage 2｜贸易/投资影响识别"],
  ["output", 1290, 145, 260, 565, C.output, "04  指标输出"],
];
for (const [id, x, y, w, h, fill, label] of lanes) {
  rect(`${id}-lane`, x, y, w, h, C.paper, C.hair, 1.5, 18, "background");
  rect(`${id}-header`, x, y, w, 48, fill, "none", 0, 18, "panels");
  rect(`${id}-header-square`, x, y + 30, w, 18, fill, "none", 0, 0, "panels");
  text(`${id}-header-text`, x + 18, y + 31, label, 19, C.ink, "700", "start");
}

// Connectors are authored independently and terminate at node edges.
arrow("a-data-1", "M150 286 L150 326");
arrow("a-data-2", "M150 421 L150 461");
arrow("a-data-stage1", "M225 508 L258 508 L258 235 L292 235");

arrow("a-s1a-review", "M462 235 L510 235");
arrow("a-s1a-positive", "M590 280 L590 318");
arrow("a-s1a-negative", "M510 253 L480 253 L480 353 L462 353");
arrow("a-positive-s1b", "M590 388 L590 420 L377 420 L377 440");
arrow("a-s1b-review", "M462 485 L510 485");
arrow("a-s1b-final", "M590 530 L590 560 L480 560 L480 592");

arrow("a-s1-stage2", "M570 630 L700 630 L700 235 L732 235");
arrow("a-s2-model-a", "M820 277 L820 318");
arrow("a-s2-model-b", "M820 277 L718 277 L718 458 L732 458");
arrow("a-model-a-compare", "M908 358 L930 358 L930 420 L952 420");
arrow("a-model-b-compare", "M908 498 L930 498 L930 452 L952 452");
arrow("a-compare-consensus", "M1102 420 L1120 420 L1120 328 L1132 328");
arrow("a-compare-conflict", "M1102 452 L1120 452 L1120 525 L1132 525");
arrow("a-consensus-final", "M1195 365 L1195 575 L1070 575 L1070 592");
arrow("a-conflict-final", "M1195 562 L1195 575 L1070 575 L1070 592");
arrow("a-trace-conflict", "M908 644 L1110 644 L1110 548 L1132 548", true);

arrow("a-final-output", "M1160 630 L1280 630 L1280 280 L1312 280");
arrow("a-output-1", "M1420 322 L1420 385");
arrow("a-output-2", "M1420 477 L1420 540");

// Data nodes.
node("raw", 75, 206, 150, 80, ["DTA 2.0", "条款原始表"], C.neutral, C.line, 21);
node("clean", 75, 326, 150, 95, ["条款清洗", "唯一 ID 构造"], C.paper, C.line, 20);
node("matrix", 75, 461, 150, 94, ["协定—条款", "矩阵"], C.paper, C.line, 20);
text("data-note", 150, 600, ["统一条款粒度", "保留来源字段与文本"], 17, C.muted, "400");

// Stage 1 nodes.
node("s1a", 292, 202, 170, 78, ["1A 双模型判定", "制度型开放？", "样本 1,071 条"], C.stage1, C.stage1Stroke, 18);
node("s1a-review", 510, 202, 160, 78, ["比较与仲裁", "冲突 103 条", "冲突率 9.62%"], C.review, C.reviewStroke, 17);
node("non-inst", 292, 318, 170, 70, ["非制度型开放", "307 条", "→ not_applicable"], C.neutral, C.line, 17);
node("inst", 510, 318, 160, 70, ["制度型开放", "764 条", "进入 Stage 1B / 2"], C.stage1, C.stage1Stroke, 17);
node("s1b", 292, 440, 170, 90, ["1B 双模型判定", "四类制度维度", "规则·规制", "管理·标准"], C.stage1, C.stage1Stroke, 17);
node("s1b-review", 510, 440, 160, 90, ["比较与仲裁", "冲突 109 条", "分母：764", "冲突率 14.27%"], C.review, C.reviewStroke, 16);
node("s1-final", 390, 592, 180, 76, ["Stage 1 最终结果", "条款属性 + 制度维度"], C.paper, C.stage1Stroke, 18);

// Stage 2 nodes.
node("s2-sample", 732, 202, 176, 75, ["Stage 2 样本", "制度型开放条款", "764 条"], C.stage2, C.stage2Stroke, 18);
node("model-a", 732, 318, 176, 80, ["模型 A 独立编码", "mp / tr / both / none"], C.paper, C.stage2Stroke, 16);
node("model-b", 732, 458, 176, 80, ["模型 B 独立编码", "mp / tr / both / none"], C.paper, C.stage2Stroke, 16);
node("compare", 952, 386, 150, 96, ["一致性比较", "仅按影响类型", "核验权重规则"], C.stage2, C.stage2Stroke, 17);
node("consensus", 1132, 290, 126, 75, ["一致样本", "直接接受", "682 条"], C.stage2, C.stage2Stroke, 17);
node("conflict", 1132, 487, 126, 75, ["冲突样本", "盲审/仲裁", "82 条"], C.review, C.reviewStroke, 17);
node("trace", 732, 610, 176, 68, ["可追溯记录", "prompt / hash", "run_id"], C.paper, C.line, 15);
node("s2-final", 980, 592, 180, 76, ["最终影响类型与权重", "贸易权重 / 投资权重"], C.paper, C.stage2Stroke, 17);

// Output nodes.
node("out-provision", 1312, 238, 216, 84, ["条款层面", "贸易/投资权重"], C.output, C.outputStroke, 20);
node("out-agreement", 1312, 385, 216, 92, ["协定层面指数", "400 份协定"], C.paper, C.outputStroke, 20);
node("out-panel", 1312, 540, 216, 100, ["国家对—年份面板", "指标 / 生效 dummy", "及理想点距离"], C.paper, C.outputStroke, 18);
text("output-note", 1420, 680, ["最终全期表：1958—2023", "76 个经济体"], 16, C.muted, "400");

// Explanation band.
rect("legend-band", 50, 736, 1500, 118, C.paper, C.hair, 1.5, 16, "background");
text("legend-title", 76, 770, "影响类型与进入条件", 20, C.ink, "700", "start");
text("legend-line-1", 76, 806, "mp：仅直接作用于贸易；tr：仅直接作用于跨境投资；both：两条渠道均存在，权重均大于 0 且合计为 1。", 17, C.ink, "400", "start");
text("legend-line-2", 76, 836, "none：已进入 Stage 2，但无直接贸易/投资影响；not_applicable：Stage 1 判定为非制度型开放，未进入 Stage 2。", 17, C.muted, "400", "start");

const manifest = {
  project: "dta-institutional-opening-editable-flowchart",
  source_image: "work/flowchart-page-1.png",
  canvas: { width: 1600, height: 900, background: C.bg },
  classification: {
    layout_topology: "four-stage workflow",
    complexity: "high",
    style_type: "academic-editorial",
    reconstruction_mode: "semantic redraw",
    reconstruction_intent: "editable-layout-and-copy-revision",
    route: "simple text/shape workflow diagram",
    no_assets_needed: "Source contains only text, boxes, rules and arrows; all significant elements are rebuilt as editable primitives."
  },
  panels: lanes.map(([id, x, y, w, h]) => ({ id: `panel-${id}`, label: id, x, y, w, h, strategy: "semantic redraw" })),
  assets: [],
  elements,
  provenance: {
    original_source_pdf: "../流程图.pdf",
    content_basis: ["current PDF", "README.md", "docs/progress_update_20260711/材料核查记录_20260711.md", "current processed CSV row counts"]
  },
  quality_gates: {}
};

fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), "utf8");
console.log(manifestPath);
