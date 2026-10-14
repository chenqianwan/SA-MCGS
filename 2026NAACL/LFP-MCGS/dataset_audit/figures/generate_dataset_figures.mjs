import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const sharp = require("sharp");
const HERE = path.dirname(fileURLToPath(import.meta.url));

const C = {
  ink: "#102a43",
  muted: "#52667a",
  line: "#cbd5e1",
  panel: "#f8fafc",
  white: "#ffffff",
  green: "#15803d",
  greenSoft: "#dcfce7",
  amber: "#b45309",
  amberSoft: "#fef3c7",
  gray: "#64748b",
  graySoft: "#f1f5f9",
  blue: "#2563eb",
  blueSoft: "#dbeafe",
  violet: "#7c3aed",
  violetSoft: "#ede9fe",
  teal: "#0f766e",
  tealSoft: "#ccfbf1",
  red: "#dc2626",
  redSoft: "#fee2e2",
};

const esc = (s) => String(s)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

function defs() {
  return `<defs>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="5" stdDeviation="7" flood-color="#102a43" flood-opacity="0.10"/>
    </filter>
    <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto">
      <path d="M0,0 L10,5 L0,10 z" fill="${C.gray}"/>
    </marker>
    <pattern id="grid" width="36" height="36" patternUnits="userSpaceOnUse">
      <path d="M36 0 L0 0 0 36" fill="none" stroke="#e2e8f0" stroke-width="1"/>
    </pattern>
  </defs>`;
}

function start(w, h, title, description) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(description)}">
    <title>${esc(title)}</title>${defs()}
    <rect width="${w}" height="${h}" fill="${C.white}"/>
    <rect width="${w}" height="${h}" fill="url(#grid)" opacity="0.25"/>`;
}

const end = () => "</svg>";

function rect(x, y, w, h, fill = C.white, stroke = C.line, sw = 2, r = 16, shadow = false) {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"${shadow ? ' filter="url(#shadow)"' : ""}/>`;
}

function text(x, y, value, size = 22, weight = 500, fill = C.ink, anchor = "start") {
  return `<text x="${x}" y="${y}" font-family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}">${esc(value)}</text>`;
}

function multiline(x, y, values, size = 20, gap = 29, weight = 500, fill = C.ink, anchor = "start") {
  return values.map((value, index) => text(x, y + index * gap, value, size, weight, fill, anchor)).join("");
}

function pill(x, y, w, label, fill, stroke, color, size = 17) {
  return `${rect(x, y, w, 36, fill, stroke, 1.5, 18)}${text(x + w / 2, y + 24, label, size, 800, color, "middle")}`;
}

function scoreCell(x, y, w, score) {
  const map = {
    2: { symbol: "●", label: "原生", color: C.green, soft: C.greenSoft },
    1: { symbol: "◐", label: "部分", color: C.amber, soft: C.amberSoft },
    0: { symbol: "—", label: "缺失", color: C.gray, soft: C.graySoft },
    x: { symbol: "!", label: "异语义", color: C.red, soft: C.redSoft },
  };
  const item = map[score];
  return `${rect(x + 22, y + 24, w - 44, 54, item.soft, item.color, 1.5, 14)}
    ${text(x + 55, y + 60, item.symbol, 23, 900, item.color, "middle")}
    ${text(x + 79, y + 59, item.label, 18, 800, item.color)}`;
}

function decisionMatrix() {
  const W = 2200;
  const H = 1450;
  let s = start(W, H, "LFP-MCGS 数据集决策矩阵", "下载和实测后的数据适配决策矩阵");
  s += text(58, 68, "第三轮 ACL 数据资格矩阵", 46, 900);
  s += text(58, 109, "同一数据必须同时支撑语义、SCC 内贡献与搜索；分散在不同数据上的半个证据不能相乘。", 22, 600, C.muted);
  s += pill(1782, 51, 160, "下载实测", C.blueSoft, C.blue, C.blue);
  s += pill(1955, 51, 180, "2026-08-18", C.violetSoft, C.violet, C.violet);

  const x0 = 48;
  const y0 = 158;
  const nameW = 340;
  const scoreW = 210;
  const decisionW = 692;
  const headers = ["自然语言", "可执行 gold", "SCC 内贡献", "获取压力代理", "完整 claim"];
  s += rect(x0, y0, nameW, 72, C.ink, C.ink, 1, 14);
  s += text(x0 + 24, y0 + 46, "数据源", 22, 800, C.white);
  headers.forEach((header, index) => {
    const x = x0 + nameW + index * scoreW;
    s += rect(x, y0, scoreW, 72, C.ink, C.ink, 1, 0);
    s += text(x + scoreW / 2, y0 + 46, header, 19, 800, C.white, "middle");
  });
  const decisionX = x0 + nameW + headers.length * scoreW;
  s += rect(decisionX, y0, decisionW, 72, C.ink, C.ink, 1, 14);
  s += text(decisionX + 24, y0 + 46, "在论文中的角色", 22, 800, C.white);

  const rows = [
    { name: "ProofWriter D5", sub: "strict positive slice", scores: [1, 2, 2, 1, 1], tag: "P0 主机制", color: C.green, soft: C.greenSoft, decision: ["2,778 theories；24,169 ground-instance-causal queries。", "record-level MAC≥3 为 88.3%；中位候选比 4.17。"] },
    { name: "ParaRules", sub: "ProofWriter NatLang", scores: [1, 2, 2, 1, 1], tag: "同族复现", color: C.violet, soft: C.violetSoft, decision: ["1,679 theories；8,723 ground-instance-causal queries。", "sentence-level MAC≥3 为 77.4%；不是独立任务。"] },
    { name: "CLUTRR", sub: "kinship composition", scores: [1, 2, 2, 1, 0], tag: "P1 闭包诊断", color: C.violet, soft: C.violetSoft, decision: ["3,977/3,977 被独立 closure 复现；instance-causal 递归链 629。", "不证明 cycle topology causal；规则全局已知。"] },
    { name: "StepGame · SpaRTUN", sub: "spatial closure", scores: [2, 2, 1, 2, 0], tag: "P1 空间外测", color: C.blue, soft: C.blueSoft, decision: ["78,777 canonical noisy cases；25,112 multi-hop SpaRTUN。", "规则全局已知；不能验证 latent rule 或复杂 SCC。"] },
    { name: "LogicNLI · SARA · FLD", sub: "small semantic slices", scores: [1, 1, 1, 0, 0], tag: "P2 小切片", color: C.amber, soft: C.amberSoft, decision: ["signed / nonmonotone / tiny strict slice 各有价值。", "语义或有效 family 数不足，不能承担 replication。"] },
    { name: "OpenBEL · SIGNOR · AOP", sub: "real feedback evidence", scores: [2, 1, 1, 1, 0], tag: "真实证据外测", color: C.teal, soft: C.tealSoft, decision: ["curated edges + context-stratified cycles。", "closure 是 reference semantics，不是 biological truth。"] },
    { name: "RuleArena · Debian", sub: "profile-specific utility", scores: [1, 2, 1, 2, 0], tag: "分 Profile", color: C.blue, soft: C.blueSoft, decision: ["真实规则选择与 solver certificate 很强。", "分别缺 productive NL-LFP 或属于 constraint semantics。"] },
    { name: "BoardgameQA · ROBUSTLR", sub: "DAG / nonrecursive", scores: [1, 1, 0, 1, 0], tag: "不进核心", color: C.red, soft: C.redSoft, decision: ["BoardgameQA 7,500 theories：grounded cycles = 0。", "EntailmentBank / C-DBR 等同样只提供 DAG 证据。"] },
  ];

  const rowH = 112;
  rows.forEach((row, rowIndex) => {
    const y = y0 + 72 + rowIndex * rowH;
    const fill = rowIndex % 2 === 0 ? C.white : C.panel;
    s += rect(x0, y, nameW, rowH, fill, C.line, 1, 0);
    s += text(x0 + 22, y + 43, row.name, 22, 850);
    s += text(x0 + 22, y + 76, row.sub, 17, 650, C.muted);
    row.scores.forEach((score, scoreIndex) => {
      const x = x0 + nameW + scoreIndex * scoreW;
      s += rect(x, y, scoreW, rowH, fill, C.line, 1, 0);
      s += scoreCell(x, y, scoreW, score);
    });
    s += rect(decisionX, y, decisionW, rowH, fill, C.line, 1, 0);
    s += pill(decisionX + 18, y + 18, 142, row.tag, row.soft, row.color, row.color, 16);
    s += multiline(decisionX + 178, y + 39, row.decision, 17, 30, 650, C.ink);
  });

  const footY = y0 + 72 + rows.length * rowH + 27;
  s += rect(48, footY, 2086, 104, C.blueSoft, C.blue, 2, 16);
  s += text(74, footY + 39, "结论", 22, 900, C.blue);
  s += text(154, footY + 39, "ProofWriter 已通过机制数据门；MCGS 必要性仍须由 Greedy / Beam / TreeMCTS 实验关闭。", 21, 800);
  s += text(154, footY + 74, "因此主结论只来自严格 positive-LFP；CLUTRR / spatial suite 与真实生物反馈按各自边界补证据。", 20, 700, C.muted);
  s += end();
  return s;
}

function connector(x1, y1, x2, y2, color = C.gray) {
  return `<path d="M${x1} ${y1} C${x1 + 85} ${y1}, ${x2 - 85} ${y2}, ${x2} ${y2}" fill="none" stroke="${color}" stroke-width="4" stroke-linecap="round" marker-end="url(#arrow)"/>`;
}

function sourceCard(x, y, w, h, number, title, subtitle, lines, color, soft) {
  let s = rect(x, y, w, h, C.white, color, 2.5, 20, true);
  s += rect(x, y, w, 60, soft, color, 0, 20);
  s += `<path d="M${x} ${y + 38}v22h${w}v-22" fill="${soft}"/>`;
  s += pill(x + 18, y + 12, 44, number, color, color, C.white, 18);
  s += text(x + 76, y + 40, title, 24, 900, color);
  s += text(x + 24, y + 92, subtitle, 18, 750, C.ink);
  s += multiline(x + 24, y + 129, lines, 17, 28, 600, C.muted);
  return s;
}

function recommendedStack() {
  const W = 2200;
  const H = 1260;
  let s = start(W, H, "LFP-MCGS 推荐数据栈", "四域数据经统一适配器进入共同指标和分域效用指标");
  s += text(58, 68, "推荐数据栈：主表只回答一个问题", 46, 900);
  s += text(58, 109, "其余数据分别验证语言、搜索、真实证据与外部效用；禁止跨语义做一个总分。", 22, 650, C.muted);

  const cardW = 520;
  const cardH = 270;
  const leftX = 56;
  const rightX = 1624;
  s += sourceCard(leftX, 174, cardW, cardH, "A", "确认性主表", "ProofWriter strict positive", ["2,778 ground-instance-causal theories", "source-linked proof + exact least-Herbrand closure", "productive / inactive SCC 与 DAG matched controls"], C.violet, C.violetSoft);
  s += sourceCard(leftX, 486, cardW, cardH, "B", "独立闭包复现", "CLUTRR · StepGame · SpaRTUN", ["629 个 instance-causal recursive chains；空间集有强 closure", "规则已知，只验证 fact acquisition 与 closure", "不能替代 SCC / latent NL rule recovery 主结论"], C.green, C.greenSoft);
  s += sourceCard(rightX, 174, cardW, cardH, "C", "真实反馈证据", "OpenBEL · SIGNOR · AOP-Wiki", ["curated edges + passage / PMID + context-stratified cycles", "严格过滤后规模小，但 provenance 强", "只称 benchmark-semantics derivability"], C.teal, C.tealSoft);
  s += sourceCard(rightX, 486, cardW, cardH, "D", "分 Profile 效用", "RuleArena · Debian · LogicNLI", ["规则选择 / constraint certificate / signed logic", "各报 method-native endpoint 与实际成本", "不进入 positive-LFP macro average"], C.blue, C.blueSoft);

  const cx = 732;
  const cy = 208;
  const cw = 736;
  const ch = 510;
  s += rect(cx, cy, cw, ch, C.white, C.ink, 3, 24, true);
  s += rect(cx, cy, cw, 76, C.ink, C.ink, 1, 24);
  s += text(cx + cw / 2, cy + 49, "Claim → Data Ledger", 28, 900, C.white, "middle");
  const schema = [
    ["C1 递归", "PW instance deletion + matched DAG"],
    ["C2 调度", "PW closure feedback；跨集只验证 closure transfer"],
    ["C3 state merge", "TreeMCTS 对照 + TT hit / shared-stat savings"],
    ["C4 语言", "ParaRules + CLUTRR / SpaRP，逐数据报告"],
    ["C5 真实证据", "OpenBEL / SIGNOR / AOP，仅 interface claim"],
  ];
  schema.forEach((item, index) => {
    const y = cy + 104 + index * 70;
    s += rect(cx + 34, y, 668, 52, index % 2 === 0 ? C.panel : C.white, C.line, 1.5, 12);
    s += text(cx + 56, y + 33, item[0], 18, 850, C.ink);
    s += text(cx + 272, y + 33, item[1], 17, 600, C.muted);
  });
  s += pill(cx + 36, cy + 462, 200, "D4 仍未关闭", C.redSoft, C.red, C.red, 16);
  s += text(cx + 254, cy + 487, "没有第二个 corpus 同时验证 latent rules + SCC + search", 18, 750, C.red);

  s += connector(leftX + cardW, 309, cx, 330, C.violet);
  s += connector(leftX + cardW, 621, cx, 583, C.green);
  s += connector(rightX, 309, cx + cw, 330, C.teal);
  s += connector(rightX, 621, cx + cw, 583, C.blue);

  const metricY = 802;
  s += rect(56, metricY, 2088, 284, C.panel, C.ink, 2.5, 22, true);
  s += text(84, metricY + 47, "结果必须分四张表，而不是一个大平均", 25, 900);
  const metrics = [
    ["确认性主表", "PW PVQA · Closure-F1 · Circular-FPR"],
    ["机制诊断", "SCC×method · ablation · exact merge"],
    ["独立复现", "CLUTRR / spatial suite 原生指标 + cost"],
    ["真实外测", "passage / PMID / solver certificate"],
  ];
  metrics.forEach((metric, index) => {
    const x = 84 + index * 503;
    s += rect(x, metricY + 72, 468, 94, C.white, [C.violet, C.green, C.teal, C.blue][index], 2, 16);
    s += text(x + 20, metricY + 107, metric[0], 18, 850, [C.violet, C.green, C.teal, C.blue][index]);
    s += text(x + 20, metricY + 139, metric[1], 15, 600, C.muted);
  });
  s += text(84, metricY + 214, "投稿升级条件", 21, 900, C.amber);
  s += text(270, metricY + 214, "closure feedback 胜 Greedy/Beam，state merge 胜 TreeMCTS，且优势在 productive SCC 放大。", 18, 700, C.ink);
  s += text(84, metricY + 252, "没有这三个 interaction，就把论文降级为 deterministic symbolic controller，而不是硬讲 MCGS。", 19, 850, C.red);

  s += rect(56, 1120, 2088, 76, C.blueSoft, C.blue, 2, 16);
  s += text(1100, 1168, "核心：ProofWriter　｜　独立闭包：CLUTRR / spatial suite　｜　真实证据：OpenBEL / SIGNOR / AOP", 23, 900, C.blue, "middle");
  s += end();
  return s;
}

async function writeFigure(baseName, svg) {
  const svgPath = path.join(HERE, `${baseName}.svg`);
  const pngPath = path.join(HERE, `${baseName}.png`);
  fs.writeFileSync(svgPath, svg, "utf8");
  await sharp(Buffer.from(svg)).png({ compressionLevel: 9 }).toFile(pngPath);
}

await writeFigure("01_dataset_decision_matrix", decisionMatrix());
await writeFigure("02_recommended_dataset_stack", recommendedStack());
