"use client";

import {
  ArrowRight,
  BrainCircuit,
  Check,
  CircleAlert,
  Copy,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useState } from "react";
import { canonicalPosition } from "./datasets";
import ResearchTabs from "./ResearchTabs";

const sections = [
  ["overview", "当前结论"],
  ["method", "方法闭环"],
] as const;

function MethodCanvas() {
  return (
    <div className="semantics-canvas" aria-label="LFP-MCGS 当前方法闭环">
      <article className="semantic-layer snapshot-layer">
        <div className="semantic-layer-head">
          <span>Observation layer</span>
          <strong>窗口仍然存在</strong>
        </div>
        <div className="semantic-flow">
          <div><small>真实循环文档</small><b>Document SCC</b></div>
          <ArrowRight aria-hidden="true" />
          <div><small>SA-MCGS / PUCT</small><b>选择 local window</b></div>
          <ArrowRight aria-hidden="true" />
          <div><small>同一个通用 LLM</small><b>解释原文</b></div>
          <ArrowRight aria-hidden="true" />
          <div className="semantic-core"><small>source grounding</small><b>validator commit</b></div>
        </div>
        <p>局部窗口是模型读取原文的接口。LFP 不替代窗口，也不读取尚未执行的来源。</p>
      </article>

      <div className="semantic-bridge" aria-hidden="true"><BrainCircuit /><span>persistent state</span></div>

      <article className="semantic-layer reasoning-layer">
        <div className="semantic-layer-head">
          <span>Reasoning layer</span>
          <strong>闭包在线改变搜索</strong>
        </div>
        <div className="semantic-flow">
          <div><small>已确认知识</small><b>committed KB</b></div>
          <ArrowRight aria-hidden="true" />
          <div><small>deterministic executor</small><b>incremental LFP</b></div>
          <ArrowRight aria-hidden="true" />
          <div><small>search feedback</small><b>Δfacts · obligations</b></div>
          <ArrowRight aria-hidden="true" />
          <div className="semantic-core"><small>next inference step</small><b>重新分配 compute</b></div>
        </div>
        <p>只有真实执行、通过验证的读取才能进入知识库；closure 产生的新事实和缺失前提指导下一轮。</p>
      </article>
    </div>
  );
}

export default function DatasetHub() {
  const [activeSection, setActiveSection] = useState("overview");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible?.target.id) setActiveSection(visible.target.id);
      },
      { rootMargin: "-18% 0px -64% 0px", threshold: [0.05, 0.25, 0.5] },
    );
    sections.forEach(([id]) => {
      const node = document.getElementById(id);
      if (node) observer.observe(node);
    });
    return () => observer.disconnect();
  }, []);

  const copyPosition = async () => {
    await navigator.clipboard.writeText(canonicalPosition);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div className="site-shell latest-hub">
      <a className="skip-link" href="#main-content">跳到主要内容</a>

      <aside className="side-rail" aria-label="页面目录">
        <a className="brand" href="#overview">
          <span className="brand-mark">μ</span>
          <span><strong>LFP-MCGS</strong><small>Current research framework</small></span>
        </a>
        <nav>
          {sections.map(([id, label], index) => (
            <a key={id} href={`#${id}`} className={activeSection === id ? "active" : ""} aria-current={activeSection === id ? "location" : undefined}>
              <span>{String(index + 1).padStart(2, "0")}</span>{label}
            </a>
          ))}
        </nav>
        <div className="rail-footer">
          <div><span className="live-dot" />最新口径</div>
          <small>Updated · 2026-08-20</small>
          <small>Research GO · confirmatory claim open</small>
        </div>
      </aside>

      <header className="mobile-header">
        <a className="mobile-brand" href="#overview"><span className="brand-mark">μ</span> LFP-MCGS</a>
        <span className="mobile-status"><span className="amber-dot" />CURRENT FRAMEWORK</span>
      </header>
      <nav className="mobile-nav" aria-label="移动端页面目录">
        {sections.map(([id, label]) => <a key={id} href={`#${id}`} className={activeSection === id ? "active" : ""}>{label}</a>)}
      </nav>

      <main id="main-content">
        <ResearchTabs active="framework" />

        <section id="overview" className="hero latest-hero section-anchor">
          <div className="eyebrow"><span className="signal-dot" /> Current conclusion · 2026-08-20</div>
          <div className="latest-hero-grid">
            <div>
              <div className="decision-pill"><ShieldCheck aria-hidden="true" /> RESEARCH GO · MAIN CLAIM NOT YET TESTED</div>
              <h1>让通用 LLM 在循环文档上<br /><em>进行可验证的 test-time reasoning。</em></h1>
              <p className="hero-lead">Paper 2 继承 SA-MCGS 在真实 document SCC 上的局部搜索能力。核心机制集冻结真实 SCC 的节点与边，只在现有窗口最小注入 seed / bridge / witness；incremental LFP 组合跨窗口证据，并把 closure 与 proof obligations 反馈给下一轮搜索。</p>
              <div className="hero-actions">
                <a className="primary-action" href="/experiment-v3">看实验结果 <ArrowRight aria-hidden="true" /></a>
                <a className="secondary-action" href="/review">看文献与数据</a>
                <button className="secondary-action" type="button" onClick={copyPosition}>
                  {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}{copied ? "已复制" : "复制当前口径"}
                </button>
              </div>
            </div>
            <aside className="latest-question-card">
              <span>唯一主问题</span>
              <h2>同一个通用 LLM，能否因为结构化 test-time compute 而得到更多 source-grounded proofs？</h2>
              <p>主比较是 Direct、CoT / Best-of-N、通用 agent、固定局部聚合与强 reasoning model，并统一核对真实 calls、tokens 和 source-linked proof。</p>
            </aside>
          </div>

          <div className="critical-gap latest-gap">
            <CircleAlert aria-hidden="true" />
            <div><strong>当前结论：闭环成立，优势未定</strong><p>真实 GraphPUCT + XHub LLM + online LFP 已在一个 9 节点 Productive 与一个 Clean carrier 上跑通并通过严格证明检查；这是端到端可行性，不是算法优势。下一步只做多案例、同成本和 no-feedback / no-PUCT 消融。</p></div>
          </div>
        </section>

        <section id="method" className="content-section section-anchor">
          <div className="section-heading">
            <div><span className="section-kicker">Paper 1 → Paper 2</span><h2>不是给 SA-MCGS 接一个末端 solver</h2></div>
            <p>LFP 必须进入搜索状态、反馈和停止条件；否则它只是一项后处理。</p>
          </div>
          <MethodCanvas />
          <div className="schedule-note"><ShieldCheck aria-hidden="true" /><div><strong>Paper 2 的唯一新增状态</strong><p>真实执行并通过验证的窗口进入 committed KB；exact LFP 产生的新事实和缺失前提再反馈下一轮 PUCT。窗口、知识与搜索由这一条闭环连接。</p></div></div>
        </section>

        <footer className="site-footer">
          <div><span className="brand-mark">μ</span><div><strong>LFP-MCGS Research Hub</strong><p>Cyclic documents · symbolic closure · test-time compute</p></div></div>
          <p>Current conclusion · 2026-08-20</p>
        </footer>
      </main>
    </div>
  );
}
