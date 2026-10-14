import { ArrowRight, CircleAlert, ExternalLink, GitMerge, ShieldCheck } from "lucide-react";
import ResearchTabs from "./ResearchTabs";
import { auditedDatasets, closestWorks, reviewStatusLabels, safeNovelty } from "./reviewData";

const sections = [
  ["review-overview", "结论"],
  ["review-priors", "直接近邻"],
  ["review-data", "数据 shortlist"],
] as const;

function SourceLinks({ source, secondarySource }: { source: string; secondarySource?: string }) {
  return (
    <span className="review-source-links">
      <a href={source} target={source.startsWith("http") ? "_blank" : undefined} rel={source.startsWith("http") ? "noreferrer" : undefined}>
        Primary source <ExternalLink aria-hidden="true" />
      </a>
      {secondarySource && <a href={secondarySource} target={secondarySource.startsWith("http") ? "_blank" : undefined} rel={secondarySource.startsWith("http") ? "noreferrer" : undefined}>Companion <ExternalLink aria-hidden="true" /></a>}
    </span>
  );
}

export default function LiteratureDataReview() {
  return (
    <div className="site-shell latest-hub review-shell">
      <a className="skip-link" href="#review-main">跳到文献与数据</a>
      <aside className="side-rail" aria-label="文献与数据目录">
        <a className="brand" href="#review-overview">
          <span className="brand-mark">R</span>
          <span><strong>Evidence review</strong><small>closest work · shortlist</small></span>
        </a>
        <nav>{sections.map(([id, label], index) => <a key={id} href={`#${id}`}><span>{String(index + 1).padStart(2, "0")}</span>{label}</a>)}</nav>
        <div className="rail-footer"><div><span className="live-dot" />CURRENT AUDIT</div><small>Updated · 2026-08-20</small></div>
      </aside>

      <header className="mobile-header"><a className="mobile-brand" href="#review-overview"><span className="brand-mark">R</span> 文献与数据</a><span className="mobile-status">CURRENT AUDIT</span></header>
      <nav className="mobile-nav" aria-label="移动端文献与数据目录">{sections.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}</nav>

      <main id="review-main">
        <ResearchTabs active="review" />

        <section id="review-overview" className="hero latest-hero section-anchor">
          <div className="eyebrow"><span className="signal-dot" /> Literature + dataset audit · 2026-08-20</div>
          <div className="latest-hero-grid">
            <div>
              <div className="decision-pill"><ShieldCheck aria-hidden="true" /> EXACT MATCH NOT FOUND · COMPONENT SPACE CROWDED</div>
              <h1>完整闭环仍有新意，<br /><em>单个组件都不能再 claim first。</em></h1>
              <p className="hero-lead">现有工作已经覆盖 MCTS/PUCT 检索、solver-guided acquisition、跨 rollout memory 与 symbolic state sharing。我们能守住的只剩一个更窄的问题：真实循环文档中的 source-grounded executable state 与 online exact LFP，能否让同一个通用 LLM 更有效地使用 test-time compute。</p>
              <div className="hero-actions"><a className="primary-action" href="#review-priors">看直接近邻 <ArrowRight aria-hidden="true" /></a><a className="secondary-action" href="#review-data">看数据 shortlist</a></div>
            </div>
            <aside className="latest-question-card">
              <span>AC / SAC judgment</span>
              <h2>方向可做，主会结论仍取决于因果实验。</h2>
              <p>Self-Correcting RAG、SymBa、PRISM-MCTS 和 RL4RLA 分别占据最相邻的四个角；缺少 no-feedback、matched-compute 或自然外测，工作就会被看成组件拼装。</p>
            </aside>
          </div>
          <div className="schedule-note review-safe-claim"><GitMerge aria-hidden="true" /><div><strong>当前安全口径</strong><p>{safeNovelty}</p></div></div>
        </section>

        <section id="review-priors" className="content-section section-anchor">
          <div className="section-heading"><div><span className="section-kicker">Nearest prior art</span><h2>只列会改变论文写法或 baseline 的工作</h2></div><p>每一行对应一个 reviewer 可能提出的“其实已有”。</p></div>
          <div className="latest-table-scroll" role="region" aria-label="直接近邻文献表，可横向滚动">
            <table className="latest-dataset-table review-table">
              <thead><tr><th scope="col">工作</th><th scope="col">重叠</th><th scope="col">硬区别</th><th scope="col">实验动作</th></tr></thead>
              <tbody>{closestWorks.map((work) => (
                <tr key={work.title}>
                  <th scope="row"><small className={`review-status status-${work.status}`}>{reviewStatusLabels[work.status]}</small><strong>{work.title}</strong><span>{work.venue}</span><SourceLinks source={work.source} secondarySource={"secondarySource" in work ? work.secondarySource : undefined} /></th>
                  <td>{work.overlap}</td><td>{work.boundary}</td><td>{work.action}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <p className="table-note"><CircleAlert aria-hidden="true" /> 主方法比较优先覆盖 Self-Correcting RAG、SymBa、PRISM-MCTS 和通用 corpus agent；法律域加 LegalGraphRAG。RL4RLA 用来界定 MCGS claim，不必硬改造成 NLP baseline。</p>
        </section>

        <section id="review-data" className="content-section section-anchor">
          <div className="section-heading"><div><span className="section-kicker">Dataset shortlist</span><h2>没有万能数据集，只保留六个角色明确的选择</h2></div><p>核心受控机制、真实长 SCC、可执行法律、真实反馈与慢思考外测分别报告，不混成一个总分。</p></div>
          <div className="latest-table-scroll" role="region" aria-label="当前数据 shortlist，可横向滚动">
            <table className="latest-dataset-table review-table dataset-review-table">
              <thead><tr><th scope="col">数据 / 角色</th><th scope="col">实测审计</th><th scope="col">能回答</th><th scope="col">不能回答</th></tr></thead>
              <tbody>{auditedDatasets.map((dataset) => (
                <tr key={dataset.name}>
                  <th scope="row"><small className={`review-status status-${dataset.status}`}>{reviewStatusLabels[dataset.status]}</small><strong>{dataset.name}</strong><span>{dataset.role}<br />{dataset.scale}</span><SourceLinks source={dataset.source} secondarySource={"secondarySource" in dataset ? dataset.secondarySource : undefined} /><em>{dataset.license}</em></th>
                  <td>{dataset.audit}</td><td>{dataset.supports}</td><td>{dataset.cannot}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <p className="table-note"><CircleAlert aria-hidden="true" /> 受控注入遵循 contrast-set 与 executable-oracle 思路，但不代表自然分布。SIGNOR 4.0 仍是下一优先规模审计对象；正式下载复核前不展示 SCC 数量。不同数据只在自己的语义内计分。</p>
        </section>

        <footer className="site-footer"><div><span className="brand-mark">R</span><div><strong>Literature + Dataset Review</strong><p>Nearest work · audited shortlist · claim boundary</p></div></div><p>Audit snapshot · 2026-08-20</p></footer>
      </main>
    </div>
  );
}
