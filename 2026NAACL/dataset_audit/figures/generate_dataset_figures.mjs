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
  s += text(58, 68, "LFP-MCGS 数据集决策矩阵", 46, 900);
  s += text(58, 109, "“原生”表示数据本身直接提供该属性；“部分”表示可派生但不能混同为原生 gold。", 22, 600, C.muted);
  s += pill(1782, 51, 160, "实测审计", C.blueSoft, C.blue, C.blue);
  s += pill(1955, 51, 180, "2026-08-16", C.violetSoft, C.violet, C.violet);

  const x0 = 48;
  const y0 = 158;
  const nameW = 340;
  const scoreW = 210;
  const decisionW = 692;
  const headers = ["真实来源", "自然语言", "SCC / 递归", "精确 LFP", "天然风险"];
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
    { name: "ProofWriter OWA", sub: "+ ParaRules", scores: [0, 1, 2, 2, 0], tag: "P0 机制主集", color: C.green, soft: C.greenSoft, decision: ["官方逻辑式、proof 与 exact closure；已有大量正递归。", "只重切 recursive-SCC / seeded split，不生成 LLM gold。"] },
    { name: "Debian", sub: "botch + dose", scores: [2, 1, 2, 1, 2], tag: "P0 真实主域", color: C.green, soft: C.greenSoft, decision: ["真实 bootstrap SCC 与 solver failure certificate。", "完整 installability 是约束问题；LFP 仅做 grounded closure。"] },
    { name: "Wikidata", sub: "constraints", scores: [2, 1, 1, 1, 1], tag: "P1 KG 外测", color: C.blue, soft: C.blueSoft, decision: ["真实、人类维护 KG；可执行传递闭包与 constraint。", "violation 是机器证书、非人工裁决；必须冻结 dump。"] },
    { name: "C-DBR + BGB XML", sub: "德国法", scores: [2, 2, 1, 0, 0], tag: "P1 法律迁移", color: C.blue, soft: C.blueSoft, decision: ["C-DBR edgelist 为 DAG；BGB 确定性 cross-ref 有 21 SCC。", "引用环不是逻辑递归；没有 LFP / 冲突 gold。"] },
    { name: "ContractNLI", sub: "607 NDAs", scores: [2, 2, 0, 0, 1], tag: "证据迁移", color: C.amber, soft: C.amberSoft, decision: ["1,156 个 Contradiction 是 hypothesis-vs-document 标签。", "当前 loader 仅 3 个非平凡 SCC；不能做 cycle 主表。"] },
    { name: "CUAD", sub: "510 contracts", scores: [2, 2, 1, 0, 0], tag: "长文本迁移", color: C.amber, soft: C.amberSoft, decision: ["专家 clause spans 权威；当前 loader 得 67 个派生 SCC。", "无 entailment / conflict / proof gold；只做 transfer。"] },
    { name: "ASPBench", sub: "stable models", scores: [0, 1, 2, "x", 0], tag: "暂不采用", color: C.red, soft: C.redSoft, decision: ["正递归样本都混有 negation / disjunction。", "stable-model ≠ positive-Horn LFP；并且官方仓库无 LICENSE。"] },
    { name: "Mancoosi", sub: "CUDF", scores: [1, 0, 1, "x", 1], tag: "历史回归", color: C.gray, soft: C.graySoft, decision: ["真实用户请求 + 可校验 solution，但约 2009–2011。", "无自然语言；FAIL 通常没有 UNSAT proof。"] },
    { name: "deps.dev + OSV", sub: "supply chain", scores: [2, 0, 0, 1, 1], tag: "安全外测", color: C.gray, soft: C.graySoft, decision: ["真实 vulnerability labels；依赖响应会随时间重解。", "抽查 20 个 npm 图均无 SCC；exposure ≠ exploitability。"] },
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
  s += text(154, footY + 39, "不存在一个数据集同时满足：真实长文本 + query-relevant SCC + exact LFP + 天然风险证书。", 21, 800);
  s += text(154, footY + 74, "因此用 ProofWriter 证明机制、Debian 验证真实风险、Wikidata 验证跨域闭包，法律集只承担迁移。", 20, 700, C.muted);
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
  s += text(58, 68, "推荐数据栈：同一算法，四种互补证据", 46, 900);
  s += text(58, 109, "generality 来自统一任务接口与共同指标，不是把不同语义强行叫作同一种 conflict。", 22, 650, C.muted);

  const cardW = 520;
  const cardH = 270;
  const leftX = 56;
  const rightX = 1624;
  s += sourceCard(leftX, 174, cardW, cardH, "A", "受控语言逻辑", "ProofWriter OWA D5 + ParaRules", ["2,959 个 strict-positive theories", "2,792 个含正递归 SCC", "exact proof / closure；人类 paraphrase 外测"], C.violet, C.violetSoft);
  s += sourceCard(leftX, 486, cardW, cardH, "B", "真实软件系统", "Debian snapshot + botch + dose", ["botch: 30 SCC / 5,367 cyclic vertices", "dose amd64: 525 failures / 105 summaries", "solver/graph certificate；按根因分组切分"], C.green, C.greenSoft);
  s += sourceCard(rightX, 174, cardW, cardH, "C", "真实知识库", "Wikidata dump + constraints", ["P31 / P279 closure + constraint rules", "violation 可机器验证，但不是人工 adjudication", "只用冻结子图；在线报告仅作发现入口"], C.teal, C.tealSoft);
  s += sourceCard(rightX, 486, cardW, cardH, "D", "真实法律文本", "BGB XML + ContractNLI + CUAD", ["法条/合同原文与人工 evidence spans", "BGB deterministic cross-ref: 21 个 SCC", "文本与拓扑迁移；不承担 LFP 主结论"], C.blue, C.blueSoft);

  const cx = 732;
  const cy = 208;
  const cw = 736;
  const ch = 510;
  s += rect(cx, cy, cw, ch, C.white, C.ink, 3, 24, true);
  s += rect(cx, cy, cw, 76, C.ink, C.ink, 1, 24);
  s += text(cx + cw / 2, cy + 49, "统一 LFP-MCGS Case Adapter", 28, 900, C.white, "middle");
  const schema = [
    ["records.jsonl", "record_id · original text · source span"],
    ["graph.jsonl", "candidate nodes/edges · SCC · provenance"],
    ["program.jsonl", "verified facts/rules · semantic profile"],
    ["queries.jsonl", "query · label · split/group key"],
    ["certificates.jsonl", "proof / blocked frontier / external certificate"],
  ];
  schema.forEach((item, index) => {
    const y = cy + 104 + index * 70;
    s += rect(cx + 34, y, 668, 52, index % 2 === 0 ? C.panel : C.white, C.line, 1.5, 12);
    s += text(cx + 56, y + 33, item[0], 18, 850, C.ink);
    s += text(cx + 272, y + 33, item[1], 17, 600, C.muted);
  });
  s += pill(cx + 36, cy + 462, 200, "semantic_profile", C.redSoft, C.red, C.red, 16);
  s += text(cx + 254, cy + 487, "必须标注 positive-LFP / constraint / evidence-only", 18, 750, C.red);

  s += connector(leftX + cardW, 309, cx, 330, C.violet);
  s += connector(leftX + cardW, 621, cx, 583, C.green);
  s += connector(rightX, 309, cx + cw, 330, C.teal);
  s += connector(rightX, 621, cx + cw, 583, C.blue);

  const metricY = 802;
  s += rect(56, metricY, 2088, 284, C.panel, C.ink, 2.5, 22, true);
  s += text(84, metricY + 47, "共同主指标", 25, 900);
  const metrics = [
    ["Proof-carrying accuracy", "答案正确 + certificate 通过 verifier"],
    ["Query-relevant closure F1", "只评估与 query 有关的 facts / rules"],
    ["Circular-support FPR", "无 seed 的 SCC 不得自我推出事实"],
    ["Anytime cost", "calls / tokens / wall time 到首个有效 proof"],
  ];
  metrics.forEach((metric, index) => {
    const x = 84 + index * 503;
    s += rect(x, metricY + 72, 468, 94, C.white, [C.violet, C.green, C.teal, C.blue][index], 2, 16);
    s += text(x + 20, metricY + 107, metric[0], 18, 850, [C.violet, C.green, C.teal, C.blue][index]);
    s += text(x + 20, metricY + 139, metric[1], 15, 600, C.muted);
  });
  s += text(84, metricY + 214, "分域 utility（分开报）", 21, 900, C.amber);
  s += text(310, metricY + 214, "Debian buildability / dose failure root cause · Wikidata constraint type · Legal evidence recall", 18, 700, C.ink);
  s += text(84, metricY + 252, "禁止合并成一个 risk score：三者的 truth condition 不同。", 19, 850, C.red);

  s += rect(56, 1120, 2088, 76, C.blueSoft, C.blue, 2, 16);
  s += text(1100, 1168, "核心表：ProofWriter + Debian　｜　外测：Wikidata　｜　迁移/案例：BGB XML + ContractNLI + CUAD", 23, 900, C.blue, "middle");
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
