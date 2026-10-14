import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const sharp = require("sharp");

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRAME_DIR = path.join(HERE, "keyframes");
fs.mkdirSync(FRAME_DIR, { recursive: true });

const C = {
  ink: "#0b1f33",
  muted: "#526579",
  faint: "#94a3b8",
  line: "#cbd5e1",
  panel: "#f8fafc",
  white: "#ffffff",
  blue: "#2563eb",
  blueSoft: "#dbeafe",
  indigo: "#4f46e5",
  indigoSoft: "#e0e7ff",
  violet: "#7c3aed",
  violetSoft: "#ede9fe",
  amber: "#d97706",
  amberSoft: "#fef3c7",
  green: "#15803d",
  greenSoft: "#dcfce7",
  teal: "#0f766e",
  tealSoft: "#ccfbf1",
  cyan: "#0891b2",
  cyanSoft: "#cffafe",
  red: "#dc2626",
  redSoft: "#fee2e2",
  graySoft: "#f1f5f9",
  gray: "#64748b",
};

const esc = (s) => String(s)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");

function svgDefs() {
  return `<defs>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="#0b1f33" flood-opacity="0.10"/>
    </filter>
    <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="7" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L10,5 L0,10 z" fill="${C.gray}"/>
    </marker>
    <marker id="arrow-blue" markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L10,5 L0,10 z" fill="${C.blue}"/>
    </marker>
    <marker id="arrow-green" markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L10,5 L0,10 z" fill="${C.green}"/>
    </marker>
    <marker id="arrow-violet" markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L10,5 L0,10 z" fill="${C.violet}"/>
    </marker>
    <marker id="arrow-red" markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L10,5 L0,10 z" fill="${C.red}"/>
    </marker>
    <pattern id="grid" width="36" height="36" patternUnits="userSpaceOnUse">
      <path d="M 36 0 L 0 0 0 36" fill="none" stroke="#e2e8f0" stroke-width="1"/>
    </pattern>
  </defs>`;
}

function startSvg(w, h, title, subtitle = "") {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-labelledby="title desc">
  <title id="title">${esc(title)}</title>
  <desc id="desc">${esc(subtitle)}</desc>
  ${svgDefs()}
  <rect width="${w}" height="${h}" fill="#ffffff"/>
  <rect width="${w}" height="${h}" fill="url(#grid)" opacity="0.32"/>`;
}

const endSvg = () => "</svg>";

function rr(x, y, w, h, { fill = C.white, stroke = C.line, sw = 2, r = 18, shadow = false, dash = "" } = {}) {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"${dash ? ` stroke-dasharray="${dash}"` : ""}${shadow ? ` filter="url(#shadow)"` : ""}/>`;
}

function line(x1, y1, x2, y2, { stroke = C.gray, sw = 3, dash = "", arrow = true, marker = "arrow" } = {}) {
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${stroke}" stroke-width="${sw}" stroke-linecap="round"${dash ? ` stroke-dasharray="${dash}"` : ""}${arrow ? ` marker-end="url(#${marker})"` : ""}/>`;
}

function curve(d, { stroke = C.gray, sw = 3, dash = "", arrow = true, marker = "arrow", fill = "none" } = {}) {
  return `<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round"${dash ? ` stroke-dasharray="${dash}"` : ""}${arrow ? ` marker-end="url(#${marker})"` : ""}/>`;
}

function txt(x, y, value, { size = 24, weight = 500, fill = C.ink, anchor = "start", family = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", italic = false } = {}) {
  return `<text x="${x}" y="${y}" font-family="${family}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}"${italic ? ` font-style="italic"` : ""}>${esc(value)}</text>`;
}

function lines(x, y, values, { size = 21, weight = 500, fill = C.ink, gap = 30, anchor = "start" } = {}) {
  return values.map((v, i) => txt(x, y + i * gap, v, { size, weight, fill, anchor })).join("");
}

function chip(x, y, label, { fill = C.graySoft, stroke = C.line, color = C.ink, size = 18, w = null } = {}) {
  const width = w ?? Math.max(82, label.length * size * 0.63 + 30);
  return `${rr(x, y, width, 38, { fill, stroke, sw: 1.5, r: 19 })}${txt(x + width / 2, y + 26, label, { size, weight: 700, fill: color, anchor: "middle" })}`;
}

function sectionTitle(x, y, index, title, color) {
  return `${rr(x, y - 31, 44, 44, { fill: color, stroke: color, r: 12 })}${txt(x + 22, y, index, { size: 22, weight: 800, fill: C.white, anchor: "middle" })}${txt(x + 58, y, title, { size: 28, weight: 800, fill: C.ink })}`;
}

function columnHeader(x, y, w, title, subtitle, color, soft) {
  return `${rr(x, y, w, 92, { fill: soft, stroke: color, sw: 2.5, r: 20 })}${txt(x + 24, y + 38, title, { size: 28, weight: 800, fill: color })}${txt(x + 24, y + 70, subtitle, { size: 18, weight: 600, fill: C.muted })}`;
}

function miniNode(cx, cy, label, { fill = C.white, stroke = C.gray, sw = 3, r = 33, textColor = C.ink, glow = false } = {}) {
  return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"${glow ? ` filter="url(#glow)"` : ""}/>${txt(cx, cy + 7, label, { size: 20, weight: 800, fill: textColor, anchor: "middle" })}`;
}

function write(name, content) {
  fs.writeFileSync(path.join(HERE, name), content, "utf8");
}

function writeFrame(name, content) {
  fs.writeFileSync(path.join(FRAME_DIR, name), content, "utf8");
}

function makeOverview() {
  const W = 2048;
  const H = 1320;
  let s = startSvg(W, H, "LFP-MCGS 总体算法架构", "从自然语言规则图到可验证最小不动点闭包与证明的完整控制回路");
  s += txt(64, 72, "LFP-MCGS：从自然语言循环规则到可验证最小不动点", { size: 48, weight: 900 });
  s += txt(64, 112, "MCGS 只决定下一段文本读哪里；LLM 只提出候选；确定性内核负责真值、闭包与证明。", { size: 24, weight: 600, fill: C.muted });
  s += chip(1558, 48, "finite positive Horn", { fill: C.greenSoft, stroke: C.green, color: C.green, w: 210 });
  s += chip(1782, 48, "anytime", { fill: C.violetSoft, stroke: C.violet, color: C.violet, w: 120 });
  s += chip(1914, 48, "proof-carrying", { fill: C.blueSoft, stroke: C.blue, color: C.blue, w: 118, size: 15 });

  const y0 = 150;
  s += columnHeader(48, y0, 350, "输入与拓扑", "真实输入仍是文本 records", C.blue, C.blueSoft);
  s += columnHeader(424, y0, 440, "MCGS 调度与局部解析", "预算控制、并发与缓存", C.violet, C.violetSoft);
  s += columnHeader(890, y0, 650, "可信符号内核", "候选可修改；committed state 单调", C.green, C.greenSoft);
  s += columnHeader(1566, y0, 434, "反馈、证明与终止", "三种不同的结束状态", C.teal, C.tealSoft);

  // Input column
  s += rr(48, 264, 350, 158, { fill: C.white, stroke: C.blue, sw: 2.5, shadow: true });
  s += txt(72, 302, "自然语言 records + query q", { size: 24, weight: 800, fill: C.blue });
  s += lines(72, 338, ["• facts / rules 仍是原文", "• candidate links 高召回", "• 不预设抽取结果正确"], { size: 19, gap: 28, fill: C.muted });

  s += rr(48, 452, 350, 238, { fill: C.panel, stroke: C.blue, sw: 2.5 });
  s += txt(72, 488, "Candidate dependency graph", { size: 23, weight: 800 });
  s += miniNode(130, 572, "P", { stroke: C.blue, fill: C.blueSoft });
  s += miniNode(232, 535, "Q", { stroke: C.blue, fill: C.blueSoft });
  s += miniNode(310, 610, "R", { stroke: C.blue, fill: C.blueSoft });
  s += line(163, 560, 198, 547, { stroke: C.blue, marker: "arrow-blue" });
  s += line(258, 557, 287, 586, { stroke: C.blue, marker: "arrow-blue" });
  s += curve("M278 628 C220 672 138 650 126 608", { stroke: C.blue, marker: "arrow-blue" });
  s += txt(222, 668, "结构上可能有环", { size: 18, weight: 700, fill: C.blue, anchor: "middle" });

  s += rr(48, 720, 350, 168, { fill: C.blueSoft, stroke: C.blue, sw: 2.5 });
  s += txt(72, 758, "Tarjan SCC + condensation DAG", { size: 22, weight: 800, fill: C.blue });
  s += lines(72, 796, ["① 定位 recursive regions", "② 逆向切出 query-relevant 区域", "③ SCC 只分区，不产生逻辑事实"], { size: 19, gap: 29 });

  s += rr(48, 918, 350, 190, { fill: C.white, stroke: C.indigo, sw: 2.5 });
  s += txt(72, 958, "初始化 S_0", { size: 24, weight: 800, fill: C.indigo });
  s += lines(72, 996, ["Fhat=Rhat=K=Pi=∅", "O={prove q}", "C=∅, Z=0, budget=B"], { size: 22, gap: 33, fill: C.ink });

  // Scheduler column
  s += rr(424, 264, 440, 154, { fill: C.violetSoft, stroke: C.violet, sw: 2.5, shadow: true });
  s += txt(450, 302, "O_t / C_t / Z_t 驱动 UCB 选择", { size: 24, weight: 800, fill: C.violet });
  s += txt(450, 342, "history + exploration + Relq + Deficit + Unseen", { size: 19, weight: 650, fill: C.ink });
  s += txt(450, 378, "proof obligation 是调度信号，不是事实", { size: 18, weight: 700, fill: C.red });

  s += rr(424, 448, 440, 142, { fill: C.white, stroke: C.violet, sw: 2.5 });
  s += txt(450, 486, "EXPAND local window", { size: 24, weight: 800 });
  s += lines(450, 522, ["围绕缺失 premise / producer 扩张", "并发 worker 使用 virtual loss 去重"], { size: 19, gap: 30, fill: C.muted });

  s += rr(424, 620, 440, 128, { fill: C.graySoft, stroke: C.gray, sw: 2.5 });
  s += txt(450, 660, "Static parse cache H_t", { size: 24, weight: 800, fill: C.gray });
  s += lines(450, 696, ["window + prompt/model version", "若 prompt 读 K，则 key 加 projected K"], { size: 18, gap: 28 });

  s += rr(424, 778, 440, 210, { fill: C.amberSoft, stroke: C.amber, sw: 3, shadow: true });
  s += txt(450, 820, "Local LLM extractor", { size: 27, weight: 900, fill: C.amber });
  s += lines(450, 860, ["自然语言窗口 → candidate facts", "自然语言窗口 → candidate Horn rules", "+ source spans / confidence / ambiguity"], { size: 20, gap: 32 });
  s += chip(450, 942, "不确定输出", { fill: C.white, stroke: C.amber, color: C.amber, w: 132 });
  s += chip(592, 942, "不能写入 K", { fill: C.redSoft, stroke: C.red, color: C.red, w: 138 });

  s += rr(424, 1018, 440, 90, { fill: C.violetSoft, stroke: C.violet, sw: 2 });
  s += txt(644, 1055, "reward / backprop + remove virtual loss", { size: 19, weight: 750, fill: C.violet, anchor: "middle" });
  s += txt(644, 1084, "+ΔK  +closed obligation  +query  −invalid  −cost", { size: 17, weight: 650, fill: C.ink, anchor: "middle" });

  // Trusted kernel
  s += rr(890, 264, 650, 174, { fill: C.amberSoft, stroke: C.amber, sw: 2.5 });
  s += txt(918, 304, "Mutable candidate ledger L_t", { size: 25, weight: 850, fill: C.amber });
  s += lines(918, 342, ["聚合重复支持；保留原文 span；允许 retry / reject", "candidate 尚未参与 rule firing"], { size: 19, gap: 31 });
  s += chip(1282, 378, "mutable", { fill: C.white, stroke: C.amber, color: C.amber, w: 110 });

  s += rr(890, 468, 650, 164, { fill: C.white, stroke: C.red, sw: 2.5 });
  s += txt(918, 508, "Validation gate", { size: 25, weight: 850, fill: C.red });
  s += lines(918, 546, ["span grounded · schema · binding · direction · support", "accept → ΔF/ΔR   retry → L   reject → audit log"], { size: 19, gap: 32 });

  s += rr(890, 662, 650, 138, { fill: C.greenSoft, stroke: C.green, sw: 3 });
  s += txt(918, 702, "Committed program  Fhat_t / Rhat_t", { size: 26, weight: 900, fill: C.green });
  s += lines(918, 740, ["只增不减；每个元素都绑定 source span", "只有 committed rules 才进入求闭包器"], { size: 19, gap: 30 });

  s += rr(890, 830, 650, 278, { fill: C.tealSoft, stroke: C.teal, sw: 3.5, shadow: true });
  s += txt(918, 872, "Deterministic incremental LFP engine", { size: 27, weight: 900, fill: C.teal });
  s += lines(918, 912, ["agenda → uses[a] → body 全满足 → fire once", "K_t = lfp_Rhat(Fhat)     ΔK_t = K_t minus K_(t-1)", "Pi_t：atom → Fact(span) 或 Rule(children)", "closing rule 的 head 已知：ΔK=∅，不会自启动"], { size: 19, gap: 34 });
  s += chip(918, 1053, "K 单调", { fill: C.white, stroke: C.green, color: C.green, w: 100 });
  s += chip(1028, 1053, "proof grounded", { fill: C.white, stroke: C.teal, color: C.teal, w: 150 });
  s += chip(1188, 1053, "semi-naive", { fill: C.white, stroke: C.blue, color: C.blue, w: 130 });

  // Feedback and outputs
  s += rr(1566, 264, 434, 192, { fill: C.violetSoft, stroke: C.violet, sw: 2.5 });
  s += txt(1594, 304, "更新 frontier / obligations", { size: 24, weight: 850, fill: C.violet });
  s += lines(1594, 344, ["ΔK 唤醒 uses[a]", "缺 premise → ProducerWindows(a)", "只重访相关区域，不全图重扫"], { size: 19, gap: 31 });

  s += rr(1566, 486, 434, 156, { fill: C.greenSoft, stroke: C.green, sw: 3 });
  s += txt(1594, 526, "① VERIFIED ENTAILED", { size: 24, weight: 900, fill: C.green });
  s += lines(1594, 564, ["q ∈ K 且 VERIFY_PROOF(Pi[q])", "返回 answer + backward-sliced proof core"], { size: 18, gap: 31 });

  s += rr(1566, 672, 434, 174, { fill: C.blueSoft, stroke: C.blue, sw: 2.5 });
  s += txt(1594, 712, "② COVERAGE-CERTIFIED NOT", { size: 22, weight: 900, fill: C.blue });
  s += lines(1594, 750, ["agenda 空；ledger 不再影响 q", "query-relevant coverage 完整", "返回 not-entailed / unknown + certificate"], { size: 18, gap: 30 });

  s += rr(1566, 876, 434, 150, { fill: C.graySoft, stroke: C.gray, sw: 2.5 });
  s += txt(1594, 916, "③ UNRESOLVED", { size: 24, weight: 900, fill: C.gray });
  s += lines(1594, 954, ["预算耗尽，但仍有 producer 未覆盖", "不能把“没找到 proof”当作否定"], { size: 18, gap: 30 });

  s += rr(1566, 1056, 434, 52, { fill: C.redSoft, stroke: C.red, sw: 2, r: 12 });
  s += txt(1783, 1090, "结构环 ≠ 事实；无 seed 的 cycle 不能自证", { size: 17, weight: 850, fill: C.red, anchor: "middle" });

  // Main arrows
  s += line(398, 342, 424, 342, { stroke: C.blue, sw: 5, marker: "arrow-blue" });
  s += line(864, 882, 890, 352, { stroke: C.amber, sw: 4, marker: "arrow" });
  s += line(1215, 438, 1215, 468, { stroke: C.amber, sw: 4 });
  s += line(1215, 632, 1215, 662, { stroke: C.green, sw: 5, marker: "arrow-green" });
  s += line(1215, 800, 1215, 830, { stroke: C.green, sw: 5, marker: "arrow-green" });
  s += line(1540, 936, 1566, 360, { stroke: C.teal, sw: 4, marker: "arrow-green" });
  s += curve("M1566 402 C1470 410 1460 1170 660 1170 C470 1170 440 1140 440 1060", { stroke: C.violet, sw: 4, dash: "10 8", marker: "arrow-violet" });
  s += txt(1040, 1208, "ΔK / missing premises 改变下一窗口价值；MCGS backprop 只更新调度统计，不改变逻辑真值", { size: 20, weight: 750, fill: C.violet, anchor: "middle" });

  s += rr(48, 1240, 1952, 48, { fill: C.ink, stroke: C.ink, r: 12 });
  s += txt(1024, 1272, "核心边界：LLM proposes → validator commits → deterministic engine derives → MCGS schedules the next read", { size: 21, weight: 800, fill: C.white, anchor: "middle" });
  s += endSvg();
  return s;
}

function panelShell(x, y, w, h, label, title, color, soft) {
  return `${rr(x, y, w, h, { fill: C.white, stroke: color, sw: 2.5, r: 22, shadow: true })}${rr(x, y, w, 58, { fill: soft, stroke: color, sw: 0, r: 22 })}<path d="M${x} ${y + 40} v18 h${w} v-18" fill="${soft}"/>${chip(x + 16, y + 10, label, { fill: color, stroke: color, color: C.white, w: 46, size: 18 })}${txt(x + 76, y + 40, title, { size: 25, weight: 850, fill: color })}`;
}

function makeModuleAtlas() {
  const W = 2400;
  const H = 1940;
  let s = startSvg(W, H, "LFP-MCGS 模块总览", "八个子模块在一张大图中的详细映射");
  s += txt(60, 70, "LFP-MCGS 模块总览：八个小图放进一张算法地图", { size: 48, weight: 900 });
  s += txt(60, 112, "统一语义：蓝=输入结构　紫=MCGS 调度　橙=LLM 候选　绿=已验证程序　青=确定性闭包　红=阻塞/拒绝", { size: 23, weight: 650, fill: C.muted });
  s += rr(60, 135, 2280, 54, { fill: C.ink, stroke: C.ink, r: 12 });
  s += txt(1200, 171, "LLM 只能进入 L；只有 validation 通过的 ΔF/ΔR 才能进入 LFP engine；K 中每个 atom 必须有 base-fact leaves。", { size: 21, weight: 800, fill: C.white, anchor: "middle" });

  const xs = [60, 645, 1230, 1815];
  const y1 = 220;
  const y2 = 1060;
  const pw = 525;
  const ph = 790;

  // A: graph layers
  s += panelShell(xs[0], y1, pw, ph, "A", "三种图不能混淆", C.blue, C.blueSoft);
  s += txt(xs[0] + 28, y1 + 100, "1. Rule dependency graph（可有环）", { size: 19, weight: 800 });
  s += miniNode(xs[0] + 110, y1 + 178, "P", { stroke: C.blue, fill: C.blueSoft, r: 27 });
  s += miniNode(xs[0] + 265, y1 + 150, "Q", { stroke: C.blue, fill: C.blueSoft, r: 27 });
  s += miniNode(xs[0] + 405, y1 + 205, "R", { stroke: C.blue, fill: C.blueSoft, r: 27 });
  s += line(xs[0] + 138, y1 + 173, xs[0] + 235, y1 + 155, { stroke: C.blue, marker: "arrow-blue" });
  s += line(xs[0] + 292, y1 + 160, xs[0] + 376, y1 + 193, { stroke: C.blue, marker: "arrow-blue" });
  s += curve(`M${xs[0] + 380} ${y1 + 226} C${xs[0] + 300} ${y1 + 278} ${xs[0] + 145} ${y1 + 270} ${xs[0] + 113} ${y1 + 207}`, { stroke: C.blue, marker: "arrow-blue" });
  s += txt(xs[0] + 28, y1 + 310, "2. SCC condensation（一定是 DAG）", { size: 19, weight: 800 });
  s += rr(xs[0] + 30, y1 + 340, 112, 62, { fill: C.blueSoft, stroke: C.blue, r: 14 });
  s += rr(xs[0] + 202, y1 + 326, 150, 90, { fill: C.violetSoft, stroke: C.violet, r: 14 });
  s += rr(xs[0] + 412, y1 + 340, 82, 62, { fill: C.greenSoft, stroke: C.green, r: 14 });
  s += txt(xs[0] + 86, y1 + 378, "upstream", { size: 16, weight: 750, anchor: "middle" });
  s += txt(xs[0] + 277, y1 + 363, "SCC", { size: 20, weight: 850, fill: C.violet, anchor: "middle" });
  s += txt(xs[0] + 277, y1 + 389, "{P,Q,R}", { size: 16, weight: 700, anchor: "middle" });
  s += txt(xs[0] + 453, y1 + 378, "query", { size: 16, weight: 750, anchor: "middle" });
  s += line(xs[0] + 142, y1 + 371, xs[0] + 202, y1 + 371, { stroke: C.gray });
  s += line(xs[0] + 352, y1 + 371, xs[0] + 412, y1 + 371, { stroke: C.gray });
  s += txt(xs[0] + 28, y1 + 470, "3. Closure-state graph（单调 DAG / lattice）", { size: 19, weight: 800 });
  const ky = y1 + 535;
  ["K0", "K1", "K2", "K*"].forEach((k, i) => {
    s += rr(xs[0] + 25 + i * 125, ky, 94, 72, { fill: i === 3 ? C.tealSoft : C.graySoft, stroke: i === 3 ? C.teal : C.gray, r: 16 });
    s += txt(xs[0] + 72 + i * 125, ky + 32, k, { size: 21, weight: 850, fill: i === 3 ? C.teal : C.ink, anchor: "middle" });
    s += txt(xs[0] + 72 + i * 125, ky + 57, `|K|=${i}`, { size: 14, weight: 650, fill: C.muted, anchor: "middle" });
    if (i < 3) s += line(xs[0] + 119 + i * 125, ky + 36, xs[0] + 150 + i * 125, ky + 36, { stroke: C.teal, marker: "arrow-green" });
  });
  s += rr(xs[0] + 25, y1 + 660, 475, 90, { fill: C.redSoft, stroke: C.red, r: 14 });
  s += lines(xs[0] + 44, y1 + 694, ["结构环存在 ≠ closure 回退", "递归规则存在 ≠ proof 必须有环"], { size: 18, weight: 800, fill: C.red, gap: 29 });

  // B: selection
  s += panelShell(xs[1], y1, pw, ph, "B", "Proof-obligation 驱动选择", C.violet, C.violetSoft);
  s += rr(xs[1] + 28, y1 + 90, 469, 96, { fill: C.violetSoft, stroke: C.violet, r: 14 });
  s += txt(xs[1] + 50, y1 + 126, "O_t: Certified(Alice)", { size: 21, weight: 850, fill: C.violet });
  s += txt(xs[1] + 50, y1 + 160, "missing → Approved(Alice)", { size: 19, weight: 700 });
  s += line(xs[1] + 262, y1 + 186, xs[1] + 262, y1 + 232, { stroke: C.violet, sw: 4, marker: "arrow-violet" });
  s += rr(xs[1] + 28, y1 + 232, 469, 148, { fill: C.white, stroke: C.violet, r: 14 });
  s += txt(xs[1] + 50, y1 + 270, "ProducerWindows(Approved)", { size: 21, weight: 800 });
  s += chip(xs[1] + 50, y1 + 298, "W1: r2,r3", { fill: C.violetSoft, stroke: C.violet, color: C.violet, w: 132 });
  s += chip(xs[1] + 196, y1 + 298, "W2: r1,seed", { fill: C.white, stroke: C.gray, color: C.gray, w: 144 });
  s += chip(xs[1] + 354, y1 + 298, "W3: decoy", { fill: C.white, stroke: C.gray, color: C.gray, w: 120 });
  s += txt(xs[1] + 50, y1 + 362, "选择不是沿环乱走，而是追缺失 premise", { size: 17, weight: 750, fill: C.red });
  s += rr(xs[1] + 28, y1 + 410, 469, 206, { fill: C.panel, stroke: C.line, r: 14 });
  s += txt(xs[1] + 50, y1 + 448, "Score(window)", { size: 23, weight: 850, fill: C.violet });
  const comps = [
    ["历史收益 Q/N", C.indigoSoft, C.indigo],
    ["探索项 √logN/N", C.blueSoft, C.blue],
    ["query relevance", C.greenSoft, C.green],
    ["deficit / readiness", C.amberSoft, C.amber],
    ["unseen bonus", C.graySoft, C.gray],
  ];
  comps.forEach((c, i) => { s += chip(xs[1] + 50 + (i % 2) * 215, y1 + 475 + Math.floor(i / 2) * 52, c[0], { fill: c[1], stroke: c[2], color: c[2], w: 198, size: 16 }); });
  s += rr(xs[1] + 28, y1 + 648, 469, 102, { fill: C.graySoft, stroke: C.gray, r: 14 });
  s += lines(xs[1] + 50, y1 + 684, ["virtual loss：只避免并发重复窗口", "不进入 K，不改变 entailment"], { size: 18, gap: 30, weight: 750 });

  // C: parser/cache
  s += panelShell(xs[2], y1, pw, ph, "C", "局部解析与两种缓存", C.amber, C.amberSoft);
  s += rr(xs[2] + 28, y1 + 88, 469, 106, { fill: C.blueSoft, stroke: C.blue, r: 14 });
  s += txt(xs[2] + 50, y1 + 128, "Selected natural-language window", { size: 21, weight: 850, fill: C.blue });
  s += txt(xs[2] + 50, y1 + 162, "records r2, r3, source spans visible", { size: 17, weight: 650 });
  s += line(xs[2] + 262, y1 + 194, xs[2] + 262, y1 + 238, { stroke: C.amber, sw: 4 });
  s += rr(xs[2] + 28, y1 + 238, 469, 142, { fill: C.amberSoft, stroke: C.amber, sw: 2.5, r: 14 });
  s += txt(xs[2] + 50, y1 + 278, "LLM local extractor", { size: 23, weight: 900, fill: C.amber });
  s += lines(xs[2] + 50, y1 + 314, ["candidate fact/rule + span", "ambiguity / unsupported fragments"], { size: 18, gap: 30 });
  s += rr(xs[2] + 28, y1 + 416, 469, 132, { fill: C.graySoft, stroke: C.gray, r: 14 });
  s += txt(xs[2] + 50, y1 + 454, "Static parse cache H", { size: 22, weight: 850, fill: C.gray });
  s += lines(xs[2] + 50, y1 + 488, ["key = window + prompt + model", "prompt 若读取 K：再加 projected K"], { size: 17, gap: 28 });
  s += rr(xs[2] + 28, y1 + 584, 469, 132, { fill: C.violetSoft, stroke: C.violet, r: 14 });
  s += txt(xs[2] + 50, y1 + 622, "Closure-state transposition", { size: 22, weight: 850, fill: C.violet });
  s += lines(xs[2] + 50, y1 + 656, ["key = committed signature + K + coverage", "合并调度统计；provenance 另存"], { size: 17, gap: 28 });
  s += txt(xs[2] + 262, y1 + 758, "解析缓存 ≠ 逻辑状态缓存", { size: 19, weight: 850, fill: C.red, anchor: "middle" });

  // D: validation
  s += panelShell(xs[3], y1, pw, ph, "D", "Candidate → Commit 分层", C.red, C.redSoft);
  s += rr(xs[3] + 28, y1 + 90, 469, 120, { fill: C.amberSoft, stroke: C.amber, r: 14 });
  s += txt(xs[3] + 50, y1 + 130, "Candidate ledger L_t", { size: 23, weight: 900, fill: C.amber });
  s += lines(xs[3] + 50, y1 + 166, ["r2? Ready(x) ∧ Clear(x) → Approved(x)", "support=2 · span=d7:14–91"], { size: 16, gap: 28 });
  s += line(xs[3] + 262, y1 + 210, xs[3] + 262, y1 + 250, { stroke: C.red, sw: 4, marker: "arrow-red" });
  s += rr(xs[3] + 28, y1 + 250, 469, 200, { fill: C.white, stroke: C.red, sw: 2.5, r: 14 });
  s += txt(xs[3] + 50, y1 + 290, "Validation gate", { size: 23, weight: 900, fill: C.red });
  ["source span", "positive-Horn schema", "binding / scope", "direction / support"].forEach((v, i) => {
    s += miniNode(xs[3] + 69, y1 + 330 + i * 30, "✓", { fill: C.greenSoft, stroke: C.green, r: 11, sw: 2, textColor: C.green });
    s += txt(xs[3] + 92, y1 + 336 + i * 30, v, { size: 17, weight: 700 });
  });
  s += line(xs[3] + 120, y1 + 450, xs[3] + 120, y1 + 505, { stroke: C.green, sw: 4, marker: "arrow-green" });
  s += line(xs[3] + 262, y1 + 450, xs[3] + 262, y1 + 505, { stroke: C.amber, sw: 4, dash: "7 5" });
  s += line(xs[3] + 404, y1 + 450, xs[3] + 404, y1 + 505, { stroke: C.red, sw: 4, marker: "arrow-red" });
  s += chip(xs[3] + 54, y1 + 518, "ACCEPT", { fill: C.greenSoft, stroke: C.green, color: C.green, w: 132 });
  s += chip(xs[3] + 196, y1 + 518, "RETRY", { fill: C.amberSoft, stroke: C.amber, color: C.amber, w: 132 });
  s += chip(xs[3] + 338, y1 + 518, "REJECT", { fill: C.redSoft, stroke: C.red, color: C.red, w: 132 });
  s += rr(xs[3] + 28, y1 + 594, 469, 120, { fill: C.greenSoft, stroke: C.green, sw: 2.5, r: 14 });
  s += txt(xs[3] + 50, y1 + 634, "Committed Fhat / Rhat", { size: 23, weight: 900, fill: C.green });
  s += lines(xs[3] + 50, y1 + 670, ["monotone · canonical · source-linked", "只有这里的规则能 firing"], { size: 17, gap: 28 });
  s += txt(xs[3] + 262, y1 + 760, "Candidate ≠ Truth", { size: 21, weight: 900, fill: C.red, anchor: "middle" });

  // E: LFP engine
  s += panelShell(xs[0], y2, pw, ph, "E", "增量 LFP 内核", C.teal, C.tealSoft);
  const ex = xs[0];
  s += rr(ex + 28, y2 + 90, 200, 90, { fill: C.cyanSoft, stroke: C.cyan, r: 14 });
  s += txt(ex + 128, y2 + 126, "new atom a", { size: 21, weight: 850, fill: C.cyan, anchor: "middle" });
  s += txt(ex + 128, y2 + 156, "atomAgenda", { size: 16, weight: 700, anchor: "middle" });
  s += line(ex + 228, y2 + 135, ex + 292, y2 + 135, { stroke: C.teal, sw: 4, marker: "arrow-green" });
  s += rr(ex + 292, y2 + 90, 205, 90, { fill: C.tealSoft, stroke: C.teal, r: 14 });
  s += txt(ex + 394, y2 + 126, "uses[a]", { size: 22, weight: 850, fill: C.teal, anchor: "middle" });
  s += txt(ex + 394, y2 + 156, "唤醒相关 rules", { size: 16, weight: 700, anchor: "middle" });
  s += line(ex + 394, y2 + 180, ex + 394, y2 + 230, { stroke: C.teal, sw: 4, marker: "arrow-green" });
  s += rr(ex + 28, y2 + 230, 469, 122, { fill: C.white, stroke: C.teal, r: 14 });
  s += txt(ex + 50, y2 + 270, "body(r) ⊆ satisfied[r] ?", { size: 22, weight: 850 });
  s += chip(ex + 50, y2 + 294, "NO → keep waiting", { fill: C.redSoft, stroke: C.red, color: C.red, w: 190, size: 16 });
  s += chip(ex + 252, y2 + 294, "YES → fire once", { fill: C.greenSoft, stroke: C.green, color: C.green, w: 190, size: 16 });
  s += line(ex + 394, y2 + 352, ex + 394, y2 + 402, { stroke: C.green, sw: 4, marker: "arrow-green" });
  s += rr(ex + 28, y2 + 402, 469, 122, { fill: C.greenSoft, stroke: C.green, r: 14 });
  s += txt(ex + 50, y2 + 442, "head h 不在 K：add h + Pi[h]", { size: 21, weight: 850, fill: C.green });
  s += txt(ex + 50, y2 + 478, "head h 已在 K：fired=true, ΔK=∅", { size: 18, weight: 750, fill: C.red });
  s += rr(ex + 28, y2 + 560, 469, 150, { fill: C.panel, stroke: C.line, r: 14 });
  s += txt(ex + 50, y2 + 600, "全程复杂度（已 ground program）", { size: 20, weight: 850 });
  s += lines(ex + 50, y2 + 638, ["每个 atom 首次入 K 一次", "每条 rule 首次 firing 一次", "总计 O(n + m + Σ|body|)"], { size: 18, gap: 30 });
  s += chip(ex + 50, y2 + 732, "no circular bootstrap", { fill: C.redSoft, stroke: C.red, color: C.red, w: 220, size: 16 });

  // F: delta revisit
  s += panelShell(xs[1], y2, pw, ph, "F", "ΔK-triggered revisit", C.cyan, C.cyanSoft);
  s += rr(xs[1] + 28, y2 + 92, 469, 92, { fill: C.cyanSoft, stroke: C.cyan, r: 14 });
  s += txt(xs[1] + 262, y2 + 130, "ΔK = {Ready(Alice)}", { size: 22, weight: 900, fill: C.cyan, anchor: "middle" });
  s += txt(xs[1] + 262, y2 + 158, "这是新事件，不是重新扫描全图", { size: 16, weight: 700, anchor: "middle" });
  s += line(xs[1] + 262, y2 + 184, xs[1] + 262, y2 + 230, { stroke: C.cyan, sw: 4, marker: "arrow-blue" });
  s += rr(xs[1] + 28, y2 + 230, 218, 162, { fill: C.greenSoft, stroke: C.green, r: 14 });
  s += txt(xs[1] + 137, y2 + 270, "已提交程序", { size: 20, weight: 850, fill: C.green, anchor: "middle" });
  s += txt(xs[1] + 137, y2 + 308, "uses[Ready]", { size: 20, weight: 800, anchor: "middle" });
  s += txt(xs[1] + 137, y2 + 344, "→ wake r2", { size: 18, weight: 700, anchor: "middle" });
  s += rr(xs[1] + 279, y2 + 230, 218, 162, { fill: C.violetSoft, stroke: C.violet, r: 14 });
  s += txt(xs[1] + 388, y2 + 270, "未覆盖文本", { size: 20, weight: 850, fill: C.violet, anchor: "middle" });
  s += txt(xs[1] + 388, y2 + 308, "ProducerWindows", { size: 18, weight: 800, anchor: "middle" });
  s += txt(xs[1] + 388, y2 + 344, "→ prioritize consumers", { size: 16, weight: 700, anchor: "middle" });
  s += line(xs[1] + 137, y2 + 392, xs[1] + 137, y2 + 446, { stroke: C.green, sw: 4, marker: "arrow-green" });
  s += line(xs[1] + 388, y2 + 392, xs[1] + 388, y2 + 446, { stroke: C.violet, sw: 4, marker: "arrow-violet" });
  s += rr(xs[1] + 28, y2 + 446, 469, 120, { fill: C.white, stroke: C.cyan, r: 14 });
  s += txt(xs[1] + 50, y2 + 486, "Update obligations O_(t+1)", { size: 22, weight: 850, fill: C.cyan });
  s += lines(xs[1] + 50, y2 + 522, ["close satisfied tuples", "add exact missing-premise sets"], { size: 17, gap: 28 });
  s += rr(xs[1] + 28, y2 + 606, 469, 112, { fill: C.redSoft, stroke: C.red, r: 14 });
  s += lines(xs[1] + 50, y2 + 648, ["Conjunction 必须记录完整 tuple", "Ready ∧ Clear → Approved 不能退化成 pair"], { size: 17, gap: 29, weight: 800, fill: C.red });
  s += chip(xs[1] + 50, y2 + 738, "semi-naive scheduling", { fill: C.cyanSoft, stroke: C.cyan, color: C.cyan, w: 220, size: 16 });

  // G: transposition/provenance
  s += panelShell(xs[2], y2, pw, ph, "G", "Transposition 与 provenance", C.indigo, C.indigoSoft);
  s += txt(xs[2] + 70, y2 + 115, "Path A", { size: 18, weight: 800, fill: C.indigo });
  s += chip(xs[2] + 40, y2 + 135, "W1", { fill: C.blueSoft, stroke: C.blue, color: C.blue, w: 90 });
  s += line(xs[2] + 130, y2 + 154, xs[2] + 180, y2 + 154, { stroke: C.indigo });
  s += chip(xs[2] + 180, y2 + 135, "W2", { fill: C.greenSoft, stroke: C.green, color: C.green, w: 90 });
  s += txt(xs[2] + 70, y2 + 235, "Path B", { size: 18, weight: 800, fill: C.indigo });
  s += chip(xs[2] + 40, y2 + 255, "W2", { fill: C.greenSoft, stroke: C.green, color: C.green, w: 90 });
  s += line(xs[2] + 130, y2 + 274, xs[2] + 180, y2 + 274, { stroke: C.indigo });
  s += chip(xs[2] + 180, y2 + 255, "W1", { fill: C.blueSoft, stroke: C.blue, color: C.blue, w: 90 });
  s += curve(`M${xs[2] + 270} ${y2 + 154} C${xs[2] + 340} ${y2 + 154} ${xs[2] + 330} ${y2 + 215} ${xs[2] + 385} ${y2 + 215}`, { stroke: C.indigo, sw: 4 });
  s += curve(`M${xs[2] + 270} ${y2 + 274} C${xs[2] + 340} ${y2 + 274} ${xs[2] + 330} ${y2 + 215} ${xs[2] + 385} ${y2 + 215}`, { stroke: C.indigo, sw: 4 });
  s += rr(xs[2] + 385, y2 + 167, 112, 96, { fill: C.indigoSoft, stroke: C.indigo, r: 14 });
  s += txt(xs[2] + 441, y2 + 202, "same", { size: 17, weight: 800, fill: C.indigo, anchor: "middle" });
  s += txt(xs[2] + 441, y2 + 229, "closure", { size: 17, weight: 800, fill: C.indigo, anchor: "middle" });
  s += txt(xs[2] + 441, y2 + 250, "state", { size: 15, weight: 700, anchor: "middle" });
  s += rr(xs[2] + 28, y2 + 340, 469, 128, { fill: C.violetSoft, stroke: C.violet, r: 14 });
  s += txt(xs[2] + 50, y2 + 380, "合并什么？", { size: 21, weight: 850, fill: C.violet });
  s += lines(xs[2] + 50, y2 + 416, ["visits / value / coverage-compatible stats", "canonical committed program + relevant K"], { size: 17, gap: 29 });
  s += rr(xs[2] + 28, y2 + 500, 469, 128, { fill: C.greenSoft, stroke: C.green, r: 14 });
  s += txt(xs[2] + 50, y2 + 540, "不能丢什么？", { size: 21, weight: 850, fill: C.green });
  s += lines(xs[2] + 50, y2 + 576, ["Pi 的 alternative support hyperedges", "source spans / multi-parent provenance sidecar"], { size: 17, gap: 29 });
  s += rr(xs[2] + 28, y2 + 660, 469, 78, { fill: C.graySoft, stroke: C.gray, r: 14 });
  s += txt(xs[2] + 262, y2 + 709, "不同读取顺序，同一逻辑闭包", { size: 19, weight: 850, fill: C.indigo, anchor: "middle" });

  // H: proof/termination
  s += panelShell(xs[3], y2, pw, ph, "H", "Proof core 与终止", C.green, C.greenSoft);
  s += miniNode(xs[3] + 75, y2 + 135, "f0", { fill: C.greenSoft, stroke: C.green, r: 25 });
  s += miniNode(xs[3] + 185, y2 + 135, "a", { fill: C.greenSoft, stroke: C.green, r: 25 });
  s += miniNode(xs[3] + 295, y2 + 135, "b", { fill: C.greenSoft, stroke: C.green, r: 25 });
  s += miniNode(xs[3] + 430, y2 + 135, "q", { fill: C.tealSoft, stroke: C.teal, r: 29, glow: true });
  s += line(xs[3] + 101, y2 + 135, xs[3] + 157, y2 + 135, { stroke: C.green, sw: 5, marker: "arrow-green" });
  s += line(xs[3] + 211, y2 + 135, xs[3] + 267, y2 + 135, { stroke: C.green, sw: 5, marker: "arrow-green" });
  s += line(xs[3] + 322, y2 + 135, xs[3] + 397, y2 + 135, { stroke: C.green, sw: 5, marker: "arrow-green" });
  s += curve(`M${xs[3] + 430} ${y2 + 165} C${xs[3] + 420} ${y2 + 230} ${xs[3] + 180} ${y2 + 230} ${xs[3] + 185} ${y2 + 165}`, { stroke: C.gray, sw: 3, dash: "8 7", marker: "arrow" });
  s += txt(xs[3] + 305, y2 + 236, "closing edge：不在最短 proof", { size: 16, weight: 750, fill: C.gray, anchor: "middle" });
  s += rr(xs[3] + 28, y2 + 278, 469, 112, { fill: C.greenSoft, stroke: C.green, sw: 2.5, r: 14 });
  s += txt(xs[3] + 50, y2 + 318, "ENTAILMENT early stop", { size: 22, weight: 900, fill: C.green });
  s += lines(xs[3] + 50, y2 + 354, ["q ∈ K + verified Pi[q]", "返回 backward-sliced proof core"], { size: 17, gap: 28 });
  s += rr(xs[3] + 28, y2 + 422, 469, 136, { fill: C.blueSoft, stroke: C.blue, r: 14 });
  s += txt(xs[3] + 50, y2 + 462, "COVERAGE-CERTIFIED NOT", { size: 21, weight: 900, fill: C.blue });
  s += lines(xs[3] + 50, y2 + 498, ["agenda empty + ledger irrelevant", "query producers fully covered"], { size: 17, gap: 28 });
  s += rr(xs[3] + 28, y2 + 590, 469, 112, { fill: C.graySoft, stroke: C.gray, r: 14 });
  s += txt(xs[3] + 50, y2 + 630, "UNRESOLVED", { size: 22, weight: 900, fill: C.gray });
  s += lines(xs[3] + 50, y2 + 666, ["budget exhausted while coverage incomplete", "absence of proof is not a negative proof"], { size: 16, gap: 27 });
  s += chip(xs[3] + 50, y2 + 730, "one-sided anytime correctness", { fill: C.greenSoft, stroke: C.green, color: C.green, w: 260, size: 16 });

  s += endSvg();
  return s;
}

const ruleEdges = {
  r1: [310, 590, 470, 590],
  r2a: [530, 590, 690, 590],
  r2b: [530, 710, 690, 620],
  r3: [750, 590, 920, 590],
};

function graphNode(x, y, label, status, small = "") {
  const styles = {
    unseen: { fill: C.white, stroke: C.faint, sw: 2, text: C.muted },
    candidate: { fill: C.amberSoft, stroke: C.amber, sw: 4, text: C.amber },
    committed: { fill: C.white, stroke: C.green, sw: 4, text: C.green },
    known: { fill: C.blueSoft, stroke: C.blue, sw: 4, text: C.blue },
    delta: { fill: C.cyanSoft, stroke: C.cyan, sw: 6, text: C.teal },
    proof: { fill: C.greenSoft, stroke: C.green, sw: 6, text: C.green },
    blocked: { fill: C.redSoft, stroke: C.red, sw: 4, text: C.red },
  };
  const st = styles[status];
  return `${rr(x - 72, y - 39, 144, 78, { fill: st.fill, stroke: st.stroke, sw: st.sw, r: 18 })}${txt(x, y - 2, label, { size: 18, weight: 850, fill: st.text, anchor: "middle" })}${small ? txt(x, y + 24, small, { size: 13, weight: 700, fill: C.muted, anchor: "middle" }) : ""}`;
}

function edgeForFrame(key, status, label, custom = null) {
  const styles = {
    unseen: { stroke: C.faint, sw: 2, dash: "8 7", marker: "arrow" },
    candidate: { stroke: C.amber, sw: 4, dash: "8 6", marker: "arrow" },
    committed: { stroke: C.green, sw: 3, dash: "", marker: "arrow-green" },
    active: { stroke: C.cyan, sw: 7, dash: "", marker: "arrow-blue" },
    proof: { stroke: C.green, sw: 7, dash: "", marker: "arrow-green" },
    blocked: { stroke: C.red, sw: 4, dash: "9 7", marker: "arrow-red" },
  };
  const st = styles[status];
  let out;
  if (custom) {
    out = curve(custom, st);
  } else {
    const [x1, y1, x2, y2] = ruleEdges[key];
    out = line(x1, y1, x2, y2, st);
  }
  if (label) {
    const labelPos = {
      r1: [390, 576], r2a: [610, 576], r2b: [610, 657], r3: [835, 576], r4: [700, 500],
    }[key];
    out += chip(labelPos[0] - 23, labelPos[1] - 21, label, { fill: C.white, stroke: st.stroke, color: st.stroke, w: 54, size: 14 });
  }
  return out;
}

const frameData = [
  {
    title: "输入仍是自然语言，而不是已知 Datalog 程序",
    subtitle: "只有高召回 candidate graph；精确规则、SCC 与真值尚未验证。",
    window: ["未选择窗口", "query q = Certified(Alice)", "candidate frontier 初始化"],
    ledger: ["L = ∅", "Fhat = ∅", "Rhat = ∅"],
    engine: ["K = ∅", "ΔK = ∅", "Pi = ∅"],
    obligation: ["O = { prove q }", "Coverage = ∅", "Status: RUNNING"],
    nodes: { anchor: "unseen", clear: "unseen", ready: "unseen", approved: "unseen", certified: "unseen" },
    edges: { r1: "unseen", r2a: "unseen", r2b: "unseen", r3: "unseen", r4: "unseen" },
    footer: "结构提示可以有环，但 candidate edge 既不是已提交规则，也不是 proof。",
  },
  {
    title: "Query-backward 选择第一个递归窗口",
    subtitle: "MCGS 根据 q 的候选 producer 和 SCC 邻接选择 Wq={r3,r4}。",
    window: ["Selected Wq", "r3: Approved → Certified", "r4: Certified → Ready"],
    ledger: ["LLM call in flight", "virtual loss(Wq)", "parse cache miss"],
    engine: ["尚未 commit", "K = ∅", "不能 firing"],
    obligation: ["goal: Certified(Alice)", "producer region: Wq", "Status: PARSING"],
    nodes: { anchor: "unseen", clear: "unseen", ready: "candidate", approved: "candidate", certified: "candidate" },
    edges: { r1: "unseen", r2a: "unseen", r2b: "unseen", r3: "candidate", r4: "candidate" },
    footer: "蓝/紫的 query-backward 调度与绿色的逻辑传播方向不同。",
  },
  {
    title: "解析出循环，但循环没有启动",
    subtitle: "r3/r4 通过验证进入 Rhat；没有 base fact，因此 LFP closure 仍为空。",
    window: ["Wq extraction complete", "span/schema/binding ✓", "r3,r4 committed"],
    ledger: ["L → validation gate", "Rhat={r3,r4}", "Fhat=∅"],
    engine: ["body 均未满足", "K = ∅", "ΔK = ∅"],
    obligation: ["q via r3", "missing {Approved(Alice)}", "Status: STALLED"],
    nodes: { anchor: "unseen", clear: "unseen", ready: "committed", approved: "committed", certified: "committed" },
    edges: { r1: "unseen", r2a: "unseen", r2b: "unseen", r3: "committed", r4: "blocked" },
    footer: "No body is satisfied. A committed cycle edge is still not a fact.",
  },
  {
    title: "找到 conjunction 的一半，并记录完整缺失前提",
    subtitle: "Wmid={r2,d2} 提交 Clear(Alice) 与 r2；r2 仍缺 Ready(Alice)。",
    window: ["Selected Wmid", "d2: Clear(Alice)", "r2: Ready∧Clear→Approved"],
    ledger: ["Fhat={Clear(Alice)}", "Rhat={r2,r3,r4}", "all source-linked"],
    engine: ["K={Clear(Alice)}", "ΔK={Clear(Alice)}", "r2 missing Ready"],
    obligation: ["q ← Approved", "r2: has Clear", "missing {Ready(Alice)}"],
    nodes: { anchor: "unseen", clear: "delta", ready: "committed", approved: "committed", certified: "committed" },
    edges: { r1: "unseen", r2a: "committed", r2b: "active", r3: "committed", r4: "blocked" },
    footer: "Obligation 保存 missing-premise set：Ready ∧ Clear 不能被压成任意一个 premise。",
  },
  {
    title: "沿缺失 premise 找到 producer rule，而不是继续绕环",
    subtitle: "r1 已提交，但 Anchor(Alice) 尚未发现；closing rule r4 仍是 blocked branch。",
    window: ["Selected Wseed-rule", "r1: Anchor → Ready", "producer jump outside SCC"],
    ledger: ["Rhat={r1,r2,r3,r4}", "Fhat={Clear(Alice)}", "L=∅"],
    engine: ["K={Clear(Alice)}", "ΔK=∅", "r1/r4 均不能 firing"],
    obligation: ["Ready via r1: missing Anchor", "Ready via r4: cyclic blocked", "next W={d1}"],
    nodes: { anchor: "candidate", clear: "known", ready: "committed", approved: "committed", certified: "committed" },
    edges: { r1: "candidate", r2a: "committed", r2b: "committed", r3: "committed", r4: "blocked" },
    footer: "MCGS 的价值：missing premise 把搜索从 SCC 内部跳到真正的 grounded entry。",
  },
  {
    title: "Seed 提交；一次增量 saturation 开始传播",
    subtitle: "同一次 INCREMENTAL_SATURATE 内：Anchor 入 agenda，r1 firing 得到 Ready。",
    window: ["Selected Wd1", "d1: Anchor(Alice)", "validation accepted"],
    ledger: ["Fhat={Clear, Anchor}", "Rhat={r1…r4}", "无额外 LLM call"],
    engine: ["ΔK={Anchor, Ready}", "r1 fired once", "ruleAgenda=[r2]"],
    obligation: ["Ready obligation closed", "r2 body now complete", "Status: SATURATING"],
    nodes: { anchor: "delta", clear: "known", ready: "delta", approved: "committed", certified: "committed" },
    edges: { r1: "active", r2a: "active", r2b: "proof", r3: "committed", r4: "blocked" },
    footer: "Frame 5–6 是一次确定性 saturation 的内部微步，不是每推一步都调用 LLM。",
  },
  {
    title: "LFP 连续到达 query；closing rule 不覆写 grounded proof",
    subtitle: "r2 推出 Approved，r3 推出 Certified；r4 的 head Ready 已存在，因此 ΔK 不再增加。",
    window: ["No new LLM call", "incremental agenda running", "proof verifier ready"],
    ledger: ["Fhat={Clear, Anchor}", "Rhat={r1,r2,r3,r4}", "committed program fixed"],
    engine: ["K*=5 atoms", "r2→Approved; r3→q", "r4 fired, head known"],
    obligation: ["all q obligations closed", "Pi[q] verified", "Status: ENTAILED"],
    nodes: { anchor: "proof", clear: "proof", ready: "proof", approved: "proof", certified: "proof" },
    edges: { r1: "proof", r2a: "proof", r2b: "proof", r3: "proof", r4: "blocked" },
    footer: "返回 proof：Anchor─r1→Ready 与 Clear 共同经 r2→Approved─r3→Certified；r4 不在 proof core。",
  },
  {
    title: "Matched negative：同样的循环仍不能凭空自证",
    subtitle: "将 Anchor(Alice) 换为 Anchor(Bob)；拓扑和文本量不变，但实体 binding 阻止错误传播。",
    window: ["Relevant coverage complete", "all candidates resolved", "agenda empty"],
    ledger: ["Fhat={Clear(Alice), Anchor(Bob)}", "Rhat={r1…r4}", "no hidden producer"],
    engine: ["K*={Clear(A),Anchor(B),Ready(B)}", "Ready(A) missing", "q ∉ K*"],
    obligation: ["Alice: Clear✓ Ready✗", "Bob: Ready✓ Clear✗", "NOT ENTAILED (certified)"],
    nodes: { anchor: "blocked", clear: "known", ready: "blocked", approved: "blocked", certified: "blocked" },
    edges: { r1: "blocked", r2a: "blocked", r2b: "committed", r3: "committed", r4: "blocked" },
    footer: "未蕴含不等于 contradicted；只有覆盖完整才可 certified not-entailed，否则必须 UNRESOLVED。",
    negative: true,
  },
];

function frameCard(x, y, w, h, title, values, color, soft) {
  let out = rr(x, y, w, h, { fill: C.white, stroke: color, sw: 2.5, r: 18, shadow: true });
  out += rr(x, y, w, 46, { fill: soft, stroke: color, sw: 0, r: 18 });
  out += `<path d="M${x} ${y + 30} v16 h${w} v-16" fill="${soft}"/>`;
  out += txt(x + 18, y + 31, title, { size: 19, weight: 850, fill: color });
  out += lines(x + 18, y + 78, values, { size: 16, weight: 700, gap: 28, fill: C.ink });
  return out;
}

function makeFrame(index, d) {
  const W = 1600;
  const H = 900;
  let s = startSvg(W, H, `LFP-MCGS 动态演算 ${index + 1}/8`, d.title);
  s += chip(40, 28, `STEP ${index}`, { fill: C.ink, stroke: C.ink, color: C.white, w: 102 });
  s += txt(160, 61, d.title, { size: 34, weight: 900 });
  s += txt(160, 94, d.subtitle, { size: 18, weight: 650, fill: C.muted });
  s += chip(1404, 30, `${index + 1} / 8`, { fill: C.violetSoft, stroke: C.violet, color: C.violet, w: 150 });

  s += frameCard(40, 126, 345, 190, "① Selected text window", d.window, C.violet, C.violetSoft);
  s += frameCard(405, 126, 345, 190, "② Candidate → Commit", d.ledger, C.amber, C.amberSoft);
  s += frameCard(770, 126, 345, 190, "③ Incremental LFP", d.engine, C.teal, C.tealSoft);
  s += frameCard(1135, 126, 425, 190, "④ Obligations / output", d.obligation, d.negative ? C.red : C.green, d.negative ? C.redSoft : C.greenSoft);

  s += rr(40, 344, 1520, 428, { fill: C.panel, stroke: C.line, sw: 2, r: 20 });
  s += txt(64, 380, "Worked example graph（canonical form 仅用于解释；实际输入是对应自然语言 records）", { size: 19, weight: 800, fill: C.muted });

  // Edges first
  s += edgeForFrame("r1", d.edges.r1, "r1");
  s += edgeForFrame("r2a", d.edges.r2a, "r2");
  s += edgeForFrame("r2b", d.edges.r2b, "r2");
  s += edgeForFrame("r3", d.edges.r3, "r3");
  s += edgeForFrame("r4", d.edges.r4, "r4", "M920 555 C900 425 515 420 470 555");

  // Nodes
  s += graphNode(238, 590, d.negative ? "Anchor(Bob)" : "Anchor(Alice)", d.nodes.anchor, "seed d1");
  s += graphNode(458, 710, "Clear(Alice)", d.nodes.clear, "fact d2");
  s += graphNode(500, 590, "Ready(Alice)", d.nodes.ready, "recursive SCC");
  s += graphNode(720, 590, "Approved(Alice)", d.nodes.approved, "conjunction");
  s += graphNode(950, 590, "Certified(Alice)", d.nodes.certified, "QUERY q");

  // SCC hull
  s += `<path d="M420 510 C500 455 890 455 1015 520 L1015 650 C900 705 520 700 420 650 Z" fill="none" stroke="${C.violet}" stroke-width="3" stroke-dasharray="12 8"/>`;
  s += txt(720, 493, "candidate / verified recursive SCC: {Ready, Approved, Certified}", { size: 17, weight: 750, fill: C.violet, anchor: "middle" });

  // No-seed details
  if (d.negative) {
    s += graphNode(238, 690, "Ready(Bob)", "known", "derived by r1");
    s += line(238, 629, 238, 650, { stroke: C.blue, sw: 4, marker: "arrow-blue" });
    s += chip(250, 638, "r1[Bob]", { fill: C.white, stroke: C.blue, color: C.blue, w: 82, size: 13 });
    s += rr(1100, 500, 390, 180, { fill: C.redSoft, stroke: C.red, sw: 2.5, r: 16 });
    s += txt(1124, 540, "Binding check", { size: 22, weight: 900, fill: C.red });
    s += lines(1124, 578, ["Alice: Clear ✓   Ready ✗", "Bob:   Ready ✓   Clear ✗", "No grounding satisfies r2"], { size: 19, gap: 32, weight: 800 });
  } else if (index === 6) {
    s += rr(1100, 500, 390, 180, { fill: C.greenSoft, stroke: C.green, sw: 2.5, r: 16 });
    s += txt(1124, 540, "Verified proof core", { size: 22, weight: 900, fill: C.green });
    s += lines(1124, 578, ["Fact(d1), Fact(d2)", "r1 → r2 → r3", "r4 excluded: head known"], { size: 19, gap: 32, weight: 800 });
  } else {
    s += rr(1100, 525, 390, 130, { fill: C.white, stroke: C.line, sw: 2, r: 16 });
    s += txt(1124, 564, "State invariant", { size: 20, weight: 850, fill: C.indigo });
    s += lines(1124, 598, ["Fhat/Rhat/K only grow", "L and O may change"], { size: 17, gap: 29, weight: 750 });
  }

  s += rr(40, 798, 1520, 62, { fill: C.ink, stroke: C.ink, r: 14 });
  s += txt(800, 838, d.footer, { size: 18, weight: 800, fill: C.white, anchor: "middle" });
  s += endSvg();
  return s;
}

function makeContactSheet(frameSvgs) {
  const W = 3300;
  const H = 3820;
  let s = startSvg(W, H, "LFP-MCGS 八个关键帧", "从 query 初始化到正例闭包与 matched negative 的逐帧演算");
  s += txt(70, 78, "LFP-MCGS 动态演算：八个关键帧总览", { size: 50, weight: 900 });
  s += txt(70, 120, "按 STEP 0→7 阅读；前七帧为 grounded positive，最后一帧为 topology-matched decoy-seed negative。", { size: 24, weight: 650, fill: C.muted });
  const scale = 0.975;
  const fw = 1600 * scale;
  const fh = 900 * scale;
  frameSvgs.forEach((svg, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 60 + col * 1620;
    const y = 160 + row * 905;
    const uri = `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
    s += rr(x - 8, y - 8, fw + 16, fh + 16, { fill: C.white, stroke: i === 7 ? C.red : C.line, sw: i === 7 ? 4 : 2, r: 18, shadow: true });
    s += `<image x="${x}" y="${y}" width="${fw}" height="${fh}" href="${uri}"/>`;
  });
  s += endSvg();
  return s;
}

function makeDynamicHtml() {
  const framesJson = JSON.stringify(frameData.map((d, i) => ({
    src: `keyframes/step_${String(i).padStart(2, "0")}.svg`,
    title: d.title,
    note: d.footer,
  })));
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LFP-MCGS 动态算法演示</title>
  <style>
    :root { color-scheme: light; --ink:#0b1f33; --muted:#526579; --line:#cbd5e1; --violet:#7c3aed; --soft:#ede9fe; }
    * { box-sizing: border-box; }
    body { margin:0; background:#eef2f7; color:var(--ink); font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    main { max-width:1520px; margin:0 auto; padding:24px; }
    header { display:flex; align-items:flex-end; justify-content:space-between; gap:20px; margin-bottom:16px; }
    h1 { margin:0 0 5px; font-size:clamp(26px,3vw,42px); }
    .sub { color:var(--muted); font-weight:650; }
    .stage { position:relative; background:white; border:1px solid var(--line); border-radius:18px; overflow:hidden; box-shadow:0 14px 34px rgba(11,31,51,.12); }
    .stage img { display:block; width:100%; height:auto; opacity:1; transition:opacity .16s ease; }
    .stage img.swap { opacity:.18; }
    .controls { display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:14px; margin-top:16px; }
    button { appearance:none; border:1px solid var(--violet); background:white; color:var(--violet); font-weight:800; border-radius:12px; padding:10px 16px; cursor:pointer; }
    button.primary { background:var(--violet); color:white; }
    button:disabled { opacity:.35; cursor:not-allowed; }
    input[type=range] { width:100%; accent-color:var(--violet); }
    .meta { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; margin-top:14px; padding:14px 18px; border-left:5px solid var(--violet); background:white; border-radius:10px; }
    .meta strong { display:block; font-size:18px; margin-bottom:4px; }
    .meta span { color:var(--muted); font-weight:650; }
    .steps { display:grid; grid-template-columns:repeat(8,1fr); gap:7px; margin-top:12px; }
    .steps button { padding:8px 4px; font-size:13px; border-color:var(--line); color:var(--muted); }
    .steps button[aria-pressed=true] { border-color:var(--violet); color:white; background:var(--violet); }
    @media (max-width:720px) { main{padding:10px}.controls{grid-template-columns:1fr 1fr}.controls input{grid-column:1/-1;grid-row:1}.steps{grid-template-columns:repeat(4,1fr)}.meta{display:block}.meta .counter{margin-top:8px}.sub{font-size:13px} }
  </style>
</head>
<body>
<main>
  <header><div><h1>LFP-MCGS 动态算法演示</h1><div class="sub">Query → candidate parsing → verified commit → incremental LFP → proof / certified negative</div></div></header>
  <section class="stage"><img id="frame" src="keyframes/step_00.svg" alt="LFP-MCGS algorithm frame 1"></section>
  <div class="controls">
    <button id="prev" type="button">← 上一步</button>
    <input id="scrub" type="range" min="0" max="7" step="1" value="0" aria-label="选择算法步骤">
    <button id="play" class="primary" type="button">▶ 播放</button>
    <button id="next" type="button">下一步 →</button>
  </div>
  <div class="steps" id="steps"></div>
  <div class="meta"><div><strong id="title"></strong><span id="note"></span></div><strong class="counter" id="counter"></strong></div>
</main>
<script>
  const frames = ${framesJson};
  let index = 0;
  let timer = null;
  const img = document.getElementById('frame');
  const scrub = document.getElementById('scrub');
  const prev = document.getElementById('prev');
  const next = document.getElementById('next');
  const play = document.getElementById('play');
  const title = document.getElementById('title');
  const note = document.getElementById('note');
  const counter = document.getElementById('counter');
  const steps = document.getElementById('steps');
  frames.forEach((_, i) => {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = 'STEP ' + i; b.addEventListener('click', () => { stop(); show(i); });
    steps.appendChild(b);
  });
  function show(i) {
    index = Math.max(0, Math.min(frames.length - 1, i));
    img.classList.add('swap');
    window.setTimeout(() => { img.src = frames[index].src; img.alt = frames[index].title; img.classList.remove('swap'); }, 80);
    scrub.value = String(index); title.textContent = frames[index].title; note.textContent = frames[index].note;
    counter.textContent = (index + 1) + ' / ' + frames.length;
    prev.disabled = index === 0; next.disabled = index === frames.length - 1;
    [...steps.children].forEach((b, j) => b.setAttribute('aria-pressed', j === index ? 'true' : 'false'));
  }
  function stop() { if (timer) window.clearInterval(timer); timer = null; play.textContent = '▶ 播放'; }
  function start() { stop(); play.textContent = 'Ⅱ 暂停'; timer = window.setInterval(() => { if (index === frames.length - 1) show(0); else show(index + 1); }, 2400); }
  prev.addEventListener('click', () => { stop(); show(index - 1); });
  next.addEventListener('click', () => { stop(); show(index + 1); });
  scrub.addEventListener('input', e => { stop(); show(Number(e.target.value)); });
  play.addEventListener('click', () => timer ? stop() : start());
  show(0);
</script>
</body>
</html>`;
}

async function renderPng(svgName, pngName, width) {
  await sharp(path.join(HERE, svgName), { density: 180 })
    .resize({ width, withoutEnlargement: false })
    .png({ compressionLevel: 9, adaptiveFiltering: true })
    .toFile(path.join(HERE, pngName));
}

async function main() {
  const overview = makeOverview();
  const atlas = makeModuleAtlas();
  write("01_overall_architecture.svg", overview);
  write("02_module_atlas.svg", atlas);

  const frameSvgs = frameData.map((d, i) => makeFrame(i, d));
  frameSvgs.forEach((svg, i) => writeFrame(`step_${String(i).padStart(2, "0")}.svg`, svg));
  write("03_keyframes_contact_sheet.svg", makeContactSheet(frameSvgs));
  write("03_dynamic_walkthrough.html", makeDynamicHtml());

  await renderPng("01_overall_architecture.svg", "01_overall_architecture.png", 2400);
  await renderPng("02_module_atlas.svg", "02_module_atlas.png", 2800);
  await renderPng("03_keyframes_contact_sheet.svg", "03_keyframes_contact_sheet.png", 3000);
  for (let i = 0; i < frameSvgs.length; i += 1) {
    const id = String(i).padStart(2, "0");
    await sharp(path.join(FRAME_DIR, `step_${id}.svg`), { density: 150 })
      .resize({ width: 1600 })
      .png({ compressionLevel: 9, adaptiveFiltering: true })
      .toFile(path.join(FRAME_DIR, `step_${id}.png`));
  }

  const ffmpegCandidates = [process.env.FFMPEG_BIN, "ffmpeg", "/opt/homebrew/anaconda3/bin/ffmpeg"].filter(Boolean);
  const ffmpeg = ffmpegCandidates.find((candidate) => spawnSync(candidate, ["-version"], { encoding: "utf8" }).status === 0);
  if (ffmpeg) {
    const palette = path.join(FRAME_DIR, "palette.png");
    const input = path.join(FRAME_DIR, "step_%02d.png");
    const paletteRun = spawnSync(ffmpeg, ["-y", "-framerate", "0.5", "-i", input, "-vf", "scale=1280:-1:flags=lanczos,palettegen=max_colors=128", palette], { encoding: "utf8" });
    if (paletteRun.status !== 0) throw new Error(paletteRun.stderr);
    const gifRun = spawnSync(ffmpeg, ["-y", "-framerate", "0.5", "-i", input, "-i", palette, "-lavfi", "scale=1280:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer", "-loop", "0", path.join(HERE, "03_dynamic_walkthrough.gif")], { encoding: "utf8" });
    if (gifRun.status !== 0) throw new Error(gifRun.stderr);
    fs.rmSync(palette);
  }
}

await main();
