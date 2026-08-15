import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const sharp = require("sharp");
const HERE = path.dirname(fileURLToPath(import.meta.url));

const C = {
  ink: "#10243a",
  muted: "#586b80",
  faint: "#8ea0b2",
  line: "#cad5e1",
  panel: "#f8fafc",
  white: "#ffffff",
  navy: "#0b2a46",
  blue: "#2563eb",
  blueSoft: "#dbeafe",
  indigo: "#4f46e5",
  indigoSoft: "#e0e7ff",
  violet: "#7c3aed",
  violetSoft: "#ede9fe",
  teal: "#0f766e",
  tealSoft: "#ccfbf1",
  green: "#15803d",
  greenSoft: "#dcfce7",
  amber: "#c66a05",
  amberSoft: "#fef3c7",
  red: "#c62828",
  redSoft: "#fee2e2",
  graySoft: "#eef2f7",
};

const esc = (s) => String(s)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

function defs() {
  return `<defs>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="5" stdDeviation="7" flood-color="#10243a" flood-opacity="0.10"/>
    </filter>
    <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L10,5 L0,10 z" fill="${C.muted}"/>
    </marker>
    <marker id="arrow-blue" markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L10,5 L0,10 z" fill="${C.blue}"/>
    </marker>
    <marker id="arrow-violet" markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L10,5 L0,10 z" fill="${C.violet}"/>
    </marker>
    <marker id="arrow-green" markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L10,5 L0,10 z" fill="${C.green}"/>
    </marker>
    <marker id="arrow-red" markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L10,5 L0,10 z" fill="${C.red}"/>
    </marker>
    <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M40 0H0V40" fill="none" stroke="#e5ebf2" stroke-width="1"/>
    </pattern>
  </defs>`;
}

function begin(w, h, title, desc) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-labelledby="title desc">
  <title id="title">${esc(title)}</title><desc id="desc">${esc(desc)}</desc>${defs()}
  <rect width="${w}" height="${h}" fill="${C.white}"/><rect width="${w}" height="${h}" fill="url(#grid)" opacity="0.35"/>`;
}

const end = () => "</svg>";

function rect(x, y, w, h, { fill = C.white, stroke = C.line, sw = 2, r = 18, shadow = false, dash = "" } = {}) {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"${dash ? ` stroke-dasharray="${dash}"` : ""}${shadow ? ' filter="url(#shadow)"' : ""}/>`;
}

function text(x, y, value, { size = 24, weight = 500, fill = C.ink, anchor = "start", italic = false } = {}) {
  return `<text x="${x}" y="${y}" font-family="PingFang SC, Noto Sans CJK SC, Microsoft YaHei, Arial, sans-serif" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}"${italic ? ' font-style="italic"' : ""}>${esc(value)}</text>`;
}

function multiline(x, y, values, { size = 22, weight = 500, fill = C.ink, gap = 32, anchor = "start" } = {}) {
  return values.map((v, i) => text(x, y + i * gap, v, { size, weight, fill, anchor })).join("");
}

function line(x1, y1, x2, y2, { stroke = C.muted, sw = 3, arrow = true, marker = "arrow", dash = "" } = {}) {
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${stroke}" stroke-width="${sw}" stroke-linecap="round"${dash ? ` stroke-dasharray="${dash}"` : ""}${arrow ? ` marker-end="url(#${marker})"` : ""}/>`;
}

function curve(d, { stroke = C.muted, sw = 3, arrow = true, marker = "arrow", dash = "", fill = "none" } = {}) {
  return `<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round"${dash ? ` stroke-dasharray="${dash}"` : ""}${arrow ? ` marker-end="url(#${marker})"` : ""}/>`;
}

function circle(cx, cy, r, { fill = C.white, stroke = C.blue, sw = 3 } = {}) {
  return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`;
}

function pill(x, y, label, { fill = C.graySoft, stroke = C.line, color = C.ink, width = 150, size = 18 } = {}) {
  return `${rect(x, y, width, 38, { fill, stroke, sw: 1.5, r: 19 })}${text(x + width / 2, y + 26, label, { size, weight: 700, fill: color, anchor: "middle" })}`;
}

function header(s, title, subtitle, w) {
  s += text(64, 72, title, { size: 46, weight: 800 });
  s += text(64, 112, subtitle, { size: 23, weight: 500, fill: C.muted });
  s += line(64, 138, w - 64, 138, { stroke: C.line, sw: 2, arrow: false });
  return s;
}

function figureClaimEvidence() {
  const W = 2048, H = 1270;
  let s = begin(W, H, "LFP-MCGS 论文证据链", "五条 claim 必须分别由受控实验、强基线和可验证产物支撑");
  s = header(s, "PLANNED TESTS · 五条 claim，五条可证伪证据链", "以下均为实验计划与 decision gates，不代表已经得到结果。", W);

  const xs = [64, 515, 1122, 1695];
  const ws = [405, 555, 525, 289];
  ["论文必须证明什么", "决定性实验", "主指标 / 产物", "不过关就怎样"].forEach((v, i) => {
    s += rect(xs[i], 170, ws[i], 62, { fill: [C.navy, C.blue, C.teal, C.red][i], stroke: [C.navy, C.blue, C.teal, C.red][i], r: 13 });
    s += text(xs[i] + ws[i] / 2, 211, v, { size: 23, weight: 800, fill: C.white, anchor: "middle" });
  });

  const rows = [
    {
      y: 254, h: 154, n: "C1", color: C.red, soft: C.redSoft,
      claim: ["productive feedback 带来", "独立失败模式", "不是 predicate SCC 相关性"],
      exp: ["feedback instance 产出新 atom；delete 后 closure↓", "再做 matched DAG；控制 degree/proof/lexicon"],
      metric: ["PVQA、Δcycle、Circular-FPR、Propagation", "grounded oracle + pair audit + failure curves"],
      gate: ["无法隔离 feedback effect", "→ 只报相关性"]
    },
    {
      y: 428, h: 154, n: "C2", color: C.violet, soft: C.violetSoft,
      claim: ["MCGS 调度确有必要", "而非 solver / greedy /", "多采样已经足够"],
      exp: ["φ-Greedy / φ-Beam / TreeMCTS / ours", "共用 sketch simulator、compute 与 root budget"],
      metric: ["PVQA-token Pareto、exact merge、duplicate calls", "internal causal track + external system table"],
      gate: ["φ-Greedy/Beam", "或 Extract-All 支配", "→ 简化/停项"]
    },
    {
      y: 602, h: 154, n: "C3", color: C.blue, soft: C.blueSoft,
      claim: ["六个原子开关", "各自解决一个问题", "不是 SA-MCGS 换 prompt"],
      exp: ["anchor / validator / delta / obligation", "rollout depth / exact merge；固定 parse+budget"],
      metric: ["source support、PVQA、Closure F1、FPR、tokens", "formal validity 与 parse fidelity 分栏"],
      gate: ["方向不符或效应为零", "→ 删除该组件"]
    },
    {
      y: 776, h: 154, n: "C4", color: C.green, soft: C.greenSoft,
      claim: ["task-aligned 机制能泛化", "外域只作 interface case", "不做不相容语义平均"],
      exp: ["冻结方法跨 topology / language / model", "PW→ParaRules/human；external 单独降级"],
      metric: ["逐 block effect + method×condition interaction", "snapshot/hash + group split + adapters"],
      gate: ["只在模板/弱模型有效", "→ 收窄 claim"]
    },
    {
      y: 950, h: 154, n: "C5", color: C.amber, soft: C.amberSoft,
      claim: ["结论可信且可复现", "proof 不是对错误解析的", "自我验证"],
      exp: ["gold-parse diagnostic + 150–200 span 人审", "clustered stats；error/abstention/cost audit"],
      metric: ["program-relative verifier；source precision / agreement", "code、prompts、traces、licenses、limitations"],
      gate: ["解析/许可/统计不可审计", "→ 不能提交"]
    }
  ];

  for (const r of rows) {
    s += rect(xs[0], r.y, ws[0], r.h, { fill: r.soft, stroke: r.color, sw: 2.5, shadow: true });
    s += pill(xs[0] + 18, r.y + 18, r.n, { fill: C.white, stroke: r.color, color: r.color, width: 70, size: 20 });
    s += multiline(xs[0] + 105, r.y + 47, r.claim, { size: 19, weight: 700, gap: 28 });
    s += rect(xs[1], r.y, ws[1], r.h, { fill: C.white, stroke: C.line, sw: 2 });
    s += multiline(xs[1] + 24, r.y + 51, r.exp, { size: 20, weight: 600, gap: 35 });
    s += rect(xs[2], r.y, ws[2], r.h, { fill: C.white, stroke: C.line, sw: 2 });
    s += multiline(xs[2] + 24, r.y + 51, r.metric, { size: 20, weight: 600, gap: 35 });
    s += rect(xs[3], r.y, ws[3], r.h, { fill: r.soft, stroke: r.color, sw: 2 });
    s += multiline(xs[3] + ws[3] / 2, r.y + 51, r.gate, { size: 19, weight: 750, gap: 35, anchor: "middle" });
    s += line(xs[0] + ws[0] + 8, r.y + r.h / 2, xs[1] - 10, r.y + r.h / 2, { stroke: r.color, sw: 3, marker: "arrow" });
    s += line(xs[1] + ws[1] + 8, r.y + r.h / 2, xs[2] - 10, r.y + r.h / 2, { stroke: r.color, sw: 3, marker: "arrow" });
    s += line(xs[2] + ws[2] + 8, r.y + r.h / 2, xs[3] - 10, r.y + r.h / 2, { stroke: r.color, sw: 3, marker: "arrow" });
  }

  s += rect(64, 1134, W - 128, 80, { fill: C.navy, stroke: C.navy, r: 18 });
  s += text(W / 2, 1185, "Main-conference case = 新失败模式 × 不可替代的方法 × 跨条件因果一致性 × 可审计证据", { size: 28, weight: 800, fill: C.white, anchor: "middle" });
  return s + end();
}

function node(cx, cy, label, { fill = C.white, stroke = C.blue, r = 36, size = 20 } = {}) {
  return `${circle(cx, cy, r, { fill, stroke, sw: 3 })}${text(cx, cy + 7, label, { size, weight: 800, anchor: "middle" })}`;
}

function figureAlgorithm() {
  const W = 2048, H = 1320;
  let s = begin(W, H, "LFP-MCGS 三层语义与无泄漏搜索过程", "区分 recursive predicate graph、grounded productive trace、fixed-program LFP chain 与 exact transposition graph");
  s = header(s, "PLANNED ALGORITHM · 图可有环，固定程序闭包是单链，只有充分状态等价才合并", "未查询 test outcome 永远不可见；没有 dev-only simulator 或合法 merge，就不能称为 MCGS。", W);

  const cards = [
    { x: 64, w: 560, title: "① Predicate recursion + ground trace", sub: "SCC 在 predicate graph；贡献由 ground instance 验证", color: C.blue, soft: C.blueSoft },
    { x: 664, w: 590, title: "② Fixed-program LFP chain", sub: "固定 F/R：K₀ → K₁ → … → K* 是唯一单链", color: C.green, soft: C.greenSoft },
    { x: 1294, w: 690, title: "③ Exact transposition graph", sub: "只有 decision-sufficient state 等价才共享 value", color: C.violet, soft: C.violetSoft },
  ];
  for (const c of cards) {
    s += rect(c.x, 170, c.w, 440, { fill: C.white, stroke: c.color, sw: 2.5, shadow: true });
    s += rect(c.x, 170, c.w, 82, { fill: c.soft, stroke: c.color, sw: 2.5, r: 18 });
    s += text(c.x + 22, 206, c.title, { size: 24, weight: 800, fill: c.color });
    s += text(c.x + 22, 235, c.sub, { size: 17, weight: 600, fill: C.muted });
  }

  // graph 1: recursive predicate SCC plus a productive grounded feedback instance
  s += pill(88, 274, "predicate SCC: A ↔ B", { fill: C.blueSoft, stroke: C.blue, color: C.blue, width: 260, size: 17 });
  s += text(492, 299, "grounded derivation", { size: 16, weight: 700, fill: C.muted, anchor: "middle" });
  s += node(120, 390, "a(c₀)", { fill: C.white, stroke: C.blue, r: 40, size: 17 });
  s += node(285, 390, "b(c₁)", { fill: C.blueSoft, stroke: C.blue, r: 42, size: 17 });
  s += node(470, 390, "a(c₂)", { fill: C.blueSoft, stroke: C.blue, r: 42, size: 17 });
  s += node(470, 515, "q", { fill: C.white, stroke: C.blue, r: 38, size: 18 });
  s += line(160, 390, 242, 390, { stroke: C.blue, marker: "arrow-blue" });
  s += line(327, 390, 426, 390, { stroke: C.red, marker: "arrow-red" });
  s += line(470, 433, 470, 474, { stroke: C.blue, marker: "arrow-blue" });
  s += text(377, 366, "B→A feedback instance", { size: 15, weight: 750, fill: C.red, anchor: "middle" });
  s += text(286, 467, "external seed a(c₀) · feedback 产出新 a(c₂)", { size: 16, weight: 700, fill: C.blue, anchor: "middle" });
  s += text(344, 578, "delete b(c₁)→a(c₂)  ⇒  a(c₂), q disappear", { size: 16, weight: 800, fill: C.red, anchor: "middle" });

  // fixed-program chain
  const chain = [
    [728, 410, "K₀={a(c₀)}"], [875, 410, "K₁=+b(c₁)"], [1022, 410, "K₂=+a(c₂)"], [1170, 410, "K*=+q"],
  ];
  for (let i = 0; i < chain.length - 1; i++) s += line(chain[i][0] + 52, 410, chain[i + 1][0] - 52, 410, { stroke: C.green, marker: "arrow-green" });
  for (const [x, y, label] of chain) s += node(x, y, label, { fill: C.greenSoft, stroke: C.green, r: 52, size: 16 });
  s += text(959, 520, "每轮只传播 ΔK；无 seed 时整条链不启动", { size: 20, weight: 700, fill: C.green, anchor: "middle" });
  s += text(959, 565, "跨不同 commit actions 是 partial-program state poset，不是这条 LFP 链", { size: 16, weight: 650, fill: C.muted, anchor: "middle" });

  // transposition graph
  s += node(1635, 295, "s₀", { fill: C.violetSoft, stroke: C.violet, r: 42 });
  s += node(1460, 405, "读 W₁", { fill: C.white, stroke: C.violet, r: 48, size: 18 });
  s += node(1810, 405, "读 W₂", { fill: C.white, stroke: C.violet, r: 48, size: 18 });
  s += node(1635, 540, "same full key", { fill: C.violetSoft, stroke: C.violet, r: 62, size: 15 });
  s += line(1601, 323, 1496, 378, { stroke: C.violet, marker: "arrow-violet" });
  s += line(1669, 323, 1774, 378, { stroke: C.violet, marker: "arrow-violet" });
  s += line(1496, 439, 1592, 508, { stroke: C.violet, marker: "arrow-violet" });
  s += line(1774, 439, 1678, 508, { stroke: C.violet, marker: "arrow-violet" });
  s += text(1635, 585, "F/R/K + ledger + samples + action mask + cost + belief b_t / pφ version + reward", { size: 15, weight: 650, fill: C.violet, anchor: "middle" });

  // lower control loop
  s += rect(64, 660, W - 128, 566, { fill: C.panel, stroke: C.line, sw: 2.5, r: 24 });
  s += text(92, 708, "一次无 test leakage 的真实决策", { size: 29, weight: 800 });

  const lower = [
    { x: 92, w: 300, title: "Real root s(t)", color: C.blue, soft: C.blueSoft, body: ["materialized outcomes", "F/R/K + ledger", "coverage + cost"] },
    { x: 438, w: 340, title: "Abstract rollout ≥2", color: C.violet, soft: C.violetSoft, body: ["dev-only sketch p_phi", "embedding + state only", "no atom/rule/commit"] },
    { x: 824, w: 300, title: "Select root action", color: C.amber, soft: C.amberSoft, body: ["选择 window/sample", "simulation backprop", "真实状态尚未改变"] },
    { x: 1170, w: 370, title: "Charged real outcome", color: C.red, soft: C.redSoft, body: ["此时才调用 LLM", "或 replay reveal", "candidate + usage log"] },
    { x: 1586, w: 350, title: "Validate + advance", color: C.green, soft: C.greenSoft, body: ["gate + deterministic ΔLFP", "检查 exact merge key", "新 root / safe reuse"] },
  ];
  for (const c of lower) {
    s += rect(c.x, 748, c.w, 235, { fill: C.white, stroke: c.color, sw: 2.5, shadow: true });
    s += rect(c.x, 748, c.w, 58, { fill: c.soft, stroke: c.color, sw: 2.5, r: 17 });
    s += text(c.x + c.w / 2, 786, c.title, { size: 22, weight: 800, fill: c.color, anchor: "middle" });
    s += multiline(c.x + 22, 842, c.body, { size: 19, weight: 600, gap: 37 });
  }
  for (let i = 0; i < lower.length - 1; i++) {
    s += line(lower[i].x + lower[i].w + 8, 866, lower[i + 1].x - 10, 866, { stroke: C.muted, sw: 3 });
  }
  s += curve("M1760 995 C1760 1095 300 1110 244 994", { stroke: C.violet, sw: 4, marker: "arrow-violet", dash: "10 8" });
  s += text(1024, 1086, "只有 root action 获得真实 parse；sketch rollout 不产出符号；仅 exact-equivalent successor 共享 value", { size: 19, weight: 750, fill: C.violet, anchor: "middle" });

  s += rect(96, 1130, 875, 66, { fill: C.greenSoft, stroke: C.green, sw: 2, r: 16 });
  s += text(534, 1172, "保留 MCGS：sketch p_phi + rollout>1 + exact merge 均有独立收益", { size: 20, weight: 800, fill: C.green, anchor: "middle" });
  s += rect(1077, 1130, 859, 66, { fill: C.redSoft, stroke: C.red, sw: 2, r: 16 });
  s += text(1507, 1172, "无 simulator、非法 merge 或 TT hit≈0：改名 obligation-guided active search", { size: 19, weight: 800, fill: C.red, anchor: "middle" });
  return s + end();
}

function figureGenerality() {
  const W = 2048, H = 1210;
  let s = begin(W, H, "LFP-MCGS generality 证据栈", "冻结方法，在 task-aligned topology、language、model 上检验一致效应，外域只作 interface case");
  s = header(s, "PLANNED GENERALITY · 冻结机制，改变 task-aligned 条件，观察同一效应", "Debian/Wikidata/legal 不同时满足 NL + productive recursion + executable gold，因此不能补成 domain-general claim。", W);

  s += rect(720, 175, 608, 122, { fill: C.navy, stroke: C.navy, sw: 3, r: 22, shadow: true });
  s += text(1024, 222, "冻结的 task-aligned core", { size: 31, weight: 800, fill: C.white, anchor: "middle" });
  s += text(1024, 262, "同 prompt/schema · validator · LFP · budget · hyperparameters", { size: 19, weight: 600, fill: C.white, anchor: "middle" });

  const axes = [
    { x: 64, title: "Topology", color: C.blue, soft: C.blueSoft, items: ["predicate SCC ↔ matched DAG", "ground feedback contribution / rounds", "size / density / distractors"] },
    { x: 554, title: "Language", color: C.violet, soft: C.violetSoft, items: ["ProofWriter template", "ParaRules / human paraphrase", "unseen vocabulary / order"] },
    { x: 1044, title: "Model", color: C.amber, soft: C.amberSoft, items: ["1 open-weight", "1 frontier API", "第 3 家族放 appendix"] },
    { x: 1534, title: "Error isolation", color: C.green, soft: C.greenSoft, items: ["G0 producer-window recall", "committed semantic ↔ gold", "predicted ↔ gold parse"] },
  ];
  for (const a of axes) {
    s += line(1024, 305, a.x + 205, 352, { stroke: a.color, sw: 3, marker: "arrow" });
    s += rect(a.x, 354, 430, 225, { fill: C.white, stroke: a.color, sw: 2.5, shadow: true });
    s += rect(a.x, 354, 430, 62, { fill: a.soft, stroke: a.color, sw: 2.5, r: 18 });
    s += text(a.x + 215, 395, a.title, { size: 27, weight: 800, fill: a.color, anchor: "middle" });
    s += multiline(a.x + 25, 460, a.items, { size: 20, weight: 600, gap: 39 });
  }

  s += text(64, 642, "数据证据栈：角色不同，结论强度也不同", { size: 30, weight: 800 });
  const datasets = [
    { x: 64, w: 500, title: "P0 · ProofWriter / ParaRules", role: "唯一 task-aligned 主证据", color: C.blue, soft: C.blueSoft,
      lines: ["NL + formal rules + proofs", "productive ground feedback / matched DAG", "独立单位：theory / matched family"] },
    { x: 589, w: 500, title: "P1 · Debian botch / dose", role: "真实 structured interface", color: C.green, soft: C.greenSoft,
      lines: ["real SCC / solver certificates", "无 noisy NL→rule 环节", "不能验证 end-to-end domain claim"] },
    { x: 1114, w: 400, title: "P1 · Wikidata", role: "冻结 structured external", color: C.violet, soft: C.violetSoft,
      lines: ["P31/P279 closure + constraints", "机器证书，不伪称专家 gold", "按 entity/class family split"] },
    { x: 1539, w: 445, title: "P2 · Legal transfer", role: "只测 text / topology transfer", color: C.amber, soft: C.amberSoft,
      lines: ["BGB citation SCC / Contract evidence", "无原生 LFP 与内部冲突 gold", "不进入 LFP 主平均"] },
  ];
  for (const d of datasets) {
    s += rect(d.x, 680, d.w, 300, { fill: C.white, stroke: d.color, sw: 2.5, shadow: true });
    s += rect(d.x, 680, d.w, 78, { fill: d.soft, stroke: d.color, sw: 2.5, r: 18 });
    s += text(d.x + 22, 716, d.title, { size: 23, weight: 800, fill: d.color });
    s += text(d.x + 22, 744, d.role, { size: 17, weight: 700, fill: C.muted });
    s += multiline(d.x + 24, 812, d.lines, { size: 19, weight: 600, gap: 42 });
  }

  s += rect(64, 1022, 1230, 116, { fill: C.greenSoft, stroke: C.green, sw: 2.5, r: 19 });
  s += text(92, 1064, "可写 generality", { size: 23, weight: 800, fill: C.green });
  s += multiline(284, 1059, ["同一机制在 topology / language / model block 中方向一致", "按 block 报 interaction + 95% CI；参数只在 ProofWriter dev 调一次"], { size: 19, weight: 650, gap: 35 });
  s += rect(1322, 1022, 662, 116, { fill: C.redSoft, stroke: C.red, sw: 2.5, r: 19 });
  s += text(1350, 1064, "禁止", { size: 23, weight: 800, fill: C.red });
  s += multiline(1438, 1059, ["把 structured external 当 NL domain generality", "把 citation / predicate SCC 当 grounded recursion"], { size: 17, weight: 650, gap: 35 });
  return s + end();
}

function figureBaselineAblation() {
  const W = 2048, H = 1650;
  let s = begin(W, H, "LFP-MCGS baseline 公平协议与原子消融", "区分共享内部底座的 scheduler controls 与 method-native external systems，并使用 matched simulator controls、deterministic budget 和六个原子开关");
  s = header(s, "PLANNED BASELINES · 两层公平性，六个原子开关", "Internal controls 隔离 scheduler；external systems 分报 native answer 与 adapted certificate，不用接口差异制造胜负。", W);

  // A: exact scheduler controls
  s += rect(64, 165, W - 128, 102, { fill: C.navy, stroke: C.navy, sw: 3, r: 20, shadow: true });
  s += text(92, 206, "A · Scheduler causal controls", { size: 27, weight: 800, fill: C.white });
  s += text(92, 243, "same G0ret / parser / validator / LFP；φ-Greedy / Beam / TreeMCTS / ours 另共享 sketch pφ + inference cap", { size: 19, weight: 650, fill: C.white });
  const internal = [
    { x: 64, title: "Exhaustive", color: C.teal, soft: C.tealSoft, lines: ["Extract-All-Local", "否定：选择性无价值"] },
    { x: 445, title: "Deterministic", color: C.green, soft: C.greenSoft, lines: ["Static / Greedy / φ-Greedy", "否定：one-step policy 已足够"] },
    { x: 826, title: "Matched lookahead", color: C.violet, soft: C.violetSoft, lines: ["φ-Beam / TreeMCTS", "否定：MC 或 merge 无价值"] },
    { x: 1207, title: "Paper 1 policy", color: C.blue, soft: C.blueSoft, lines: ["SA-policy + LFP", "否定：只靠旧 backbone"] },
    { x: 1588, title: "Proposed", color: C.amber, soft: C.amberSoft, lines: ["LFP-MCGS", "same pφ + exact merge"] },
  ];
  for (const b of internal) {
    s += line(1024, 273, b.x + 166, 300, { stroke: b.color, sw: 2.5, marker: "arrow" });
    s += rect(b.x, 302, 332, 142, { fill: C.white, stroke: b.color, sw: 2.5, shadow: true });
    s += rect(b.x, 302, 332, 50, { fill: b.soft, stroke: b.color, sw: 2.5, r: 16 });
    s += text(b.x + 166, 335, b.title, { size: 21, weight: 800, fill: b.color, anchor: "middle" });
    s += multiline(b.x + 20, 389, b.lines, { size: 17, weight: 650, gap: 32 });
  }

  // B: external systems
  s += rect(64, 482, W - 128, 90, { fill: C.graySoft, stroke: C.line, sw: 2.5, r: 18 });
  s += text(92, 519, "B · Method-native external systems", { size: 26, weight: 800 });
  s += text(92, 552, "same raw input · model snapshot · actual-cost protocol；Native Answer 与 Certificate-Bearing Accuracy 分栏", { size: 19, weight: 650, fill: C.muted });
  const external = [
    { x: 64, w: 430, title: "Global formalization", color: C.blue, soft: C.blueSoft, lines: ["Full-Formalize + LFP", "native + certificate endpoints"] },
    { x: 554, w: 430, title: "Official SymBa", color: C.amber, soft: C.amberSoft, lines: ["method-native procedure", "先报原生 answer accuracy"] },
    { x: 1044, w: 430, title: "Authors’ adapters", color: C.violet, soft: C.violetSoft, lines: ["SymBa+Cert / Tabled+Cert", "两行；额外调用全计费"] },
    { x: 1534, w: 450, title: "External memory", color: C.green, soft: C.greenSoft, lines: ["Symbolic Working Memory", "N/A 不机械判错"] },
  ];
  for (const b of external) {
    s += rect(b.x, 596, b.w, 142, { fill: C.white, stroke: b.color, sw: 2.5, shadow: true });
    s += rect(b.x, 596, b.w, 50, { fill: b.soft, stroke: b.color, sw: 2.5, r: 16 });
    s += text(b.x + b.w / 2, 629, b.title, { size: 21, weight: 800, fill: b.color, anchor: "middle" });
    s += multiline(b.x + 22, 684, b.lines, { size: 17, weight: 650, gap: 32 });
  }

  // budget
  s += rect(64, 778, 1920, 170, { fill: C.panel, stroke: C.line, sw: 2.5, r: 20 });
  s += text(92, 820, "无内生预算、无 replay 泄漏", { size: 26, weight: 800 });
  s += pill(465, 793, "Scheduler replay", { fill: C.blueSoft, stroke: C.blue, color: C.blue, width: 190 });
  s += text(678, 820, "hidden outcome 仅在 action 后 reveal；p_phi 只看 dev", { size: 19, weight: 650 });
  s += pill(1322, 793, "Live E2E", { fill: C.greenSoft, stroke: C.green, color: C.green, width: 150 });
  s += text(1492, 820, "graph / retry / invalid / verifier 全计费", { size: 19, weight: 650 });
  s += text(92, 875, "Replay budget：deterministic B_ref = source tokens + fixed output cap。E2E：dev-frozen absolute budgets + actual-total-token Pareto。", { size: 19, weight: 700, fill: C.violet });
  s += text(92, 915, "C_all 只做事后归一化；one-shot 在其真实可运行成本形成 Pareto 单点，不能机械判 Unresolved。", { size: 18, weight: 650, fill: C.muted });

  s += text(64, 1010, "六个原子消融：每次只关一个机制", { size: 29, weight: 800 });
  const abls = [
    { y: 1048, n: "A1", title: "- source anchor", target: "Circular-FPR ↑", why: "cycle 产物不能伪装 base fact", color: C.red, soft: C.redSoft },
    { y: 1130, n: "A2", title: "- validator gate", target: "source support / PVQA ↓", why: "formal validity 仍应为 100%", color: C.amber, soft: C.amberSoft },
    { y: 1212, n: "A3", title: "- delta trigger", target: "Propagation Recall ↓", why: "新 ΔK 是否改变 action set", color: C.blue, soft: C.blueSoft },
    { y: 1294, n: "A4", title: "- obligation priority", target: "windows-to-proof ↑", why: "deficit priority vs static relevance", color: C.teal, soft: C.tealSoft },
    { y: 1376, n: "A5", title: "rollout depth >1 → 1", target: "PVQA-token Pareto ↓", why: "多步 planning vs one-step selection", color: C.green, soft: C.greenSoft },
    { y: 1458, n: "A6", title: "- exact state merge", target: "duplicate state / cost ↑", why: "合法 graph sharing 的价值", color: C.violet, soft: C.violetSoft },
  ];
  for (const a of abls) {
    s += rect(64, a.y, 1920, 66, { fill: a.soft, stroke: a.color, sw: 2, r: 13 });
    s += pill(82, a.y + 14, a.n, { fill: C.white, stroke: a.color, color: a.color, width: 70, size: 17 });
    s += text(178, a.y + 43, a.title, { size: 20, weight: 800, fill: a.color });
    s += text(820, a.y + 43, a.target, { size: 19, weight: 750 });
    s += text(1315, a.y + 43, a.why, { size: 17, weight: 650 });
  }
  s += rect(64, 1558, 1920, 58, { fill: C.navy, stroke: C.navy, r: 14 });
  s += text(1024, 1597, "判死线：φ-Greedy / φ-Beam / Extract-All / SymBa 持平，或 simulator/merge 不合法 → 删掉 MCGS 主张。", { size: 21, weight: 800, fill: C.white, anchor: "middle" });
  return s + end();
}

async function writeFigure(name, svg) {
  const svgPath = path.join(HERE, `${name}.svg`);
  const pngPath = path.join(HERE, `${name}.png`);
  fs.writeFileSync(svgPath, svg, "utf8");
  await sharp(Buffer.from(svg)).png({ compressionLevel: 9 }).toFile(pngPath);
}

await writeFigure("01_claim_evidence_chain", figureClaimEvidence());
await writeFigure("02_algorithm_and_search_graph", figureAlgorithm());
await writeFigure("03_generality_evidence_stack", figureGenerality());
await writeFigure("04_baseline_and_ablation", figureBaselineAblation());
