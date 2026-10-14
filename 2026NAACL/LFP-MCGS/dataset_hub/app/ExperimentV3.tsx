import {
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  CircleAlert,
  Database,
  GitMerge,
  Network,
  RefreshCcw,
  Route,
  ShieldCheck,
} from "lucide-react";
import { interventionConditions, nextGates, sccSizeLadder } from "./datasets";
import ResearchTabs from "./ResearchTabs";

const sections = [
  ["confirm-overview", "结论"],
  ["confirm-results", "结果"],
  ["confirm-engine", "闭环"],
  ["confirm-data", "受控数据"],
  ["confirm-next", "下一步"],
] as const;

const engineStages = [
  { icon: Network, label: "公开输入", title: "cyclic document windows", text: "GraphPUCT 只接收 query、原文窗口与有向拓扑；gold 在搜索结束后才用于评分。" },
  { icon: BrainCircuit, label: "真实 simulation", title: "XHub LLM inside search", text: "首次评估候选窗口时真实调用通用 LLM；只有完全相同的窗口才复用冻结输出。" },
  { icon: Database, label: "分支执行", title: "validator → KB → LFP", text: "来源可核验的 facts / rules 只进入当前 branch，随后立即运行 exact LFP。" },
  { icon: GitMerge, label: "图搜索", title: "strict state sharing", text: "只有程序、closure、provenance、动作集与预算都相同的状态才共享统计。" },
  { icon: Route, label: "真实提交", title: "choose one root action", text: "按 root visits 选择一个窗口；只有该 observation 能进入 persistent root KB。" },
  { icon: RefreshCcw, label: "在线闭环", title: "LFP feedback → replan", text: "新 closure 与未满足的 proof obligations 改变下一轮 prior 与 value。" },
] as const;

const pureBaselineRows = [
  ["Full-SCC Direct", "0 / 6", "6", "38,663"],
  ["Full-SCC CoT", "0 / 6", "6", "39,369"],
  ["LEA-LFP full-cover", "6 / 6", "54", "192,201"],
] as const;

const realLoopSize9Rows = [
  ["Full-SCC Direct", "FAIL", "1", "6,691"],
  ["Full-SCC CoT", "FAIL", "1", "6,795"],
  ["LEA-LFP full-cover", "PASS", "8", "30,625"],
  ["GraphPUCT + LLM + online LFP", "PASS", "7", "27,313"],
] as const;

export default function ExperimentV3() {
  return (
    <div className="site-shell experiment-shell v3-shell">
      <a className="skip-link" href="#confirm-main">跳到实验结果</a>
      <aside className="side-rail experiment-rail" aria-label="实验结果目录">
        <a className="brand" href="#confirm-overview">
          <span className="brand-mark">E</span>
          <span><strong>Experiment</strong><small>baseline · real loop · next</small></span>
        </a>
        <nav>{sections.map(([id, label], index) => <a key={id} href={`#${id}`}><span>{String(index + 1).padStart(2, "0")}</span>{label}</a>)}</nav>
        <div className="rail-footer"><div><span className="amber-dot" />REAL LOOP · PASS</div><small>Algorithm advantage · open</small></div>
      </aside>

      <header className="mobile-header"><a className="mobile-brand" href="#confirm-overview"><span className="brand-mark">E</span> 实验结果</a><span className="mobile-status">ADVANTAGE OPEN</span></header>
      <nav className="mobile-nav" aria-label="移动端实验结果目录">{sections.map(([id, label]) => <a key={id} href={`#${id}`}>{label}</a>)}</nav>

      <main id="confirm-main">
        <ResearchTabs active="confirmatory" />

        <section id="confirm-overview" className="hero experiment-hero section-anchor">
          <div className="eyebrow"><span className="signal-dot" /> Current experiment · 2026-08-20</div>
          <div className="latest-hero-grid">
            <div>
              <div className="experiment-badges"><span>SAME BASE LM</span><span>REAL WINDOW READS</span><span>EXACT LFP</span></div>
              <h1>真实闭环已经跑通，<br /><em>算法优势还没有成立。</em></h1>
              <p className="hero-lead">现在比较的不是一个旧阶段编号，而是两条最终路线：Pure Baseline 直接或固定地处理证据；完整方法用 GraphPUCT 选择窗口，让真实 LLM 在 simulation 内解析，再把 exact LFP 的结果反馈给下一轮搜索。</p>
            </div>
            <aside className="latest-question-card experiment-verdict">
              <span>当前判断</span>
              <h2>工程 GO，论文主结论 OPEN</h2>
              <p>完整方法已得到可复核证明并守住 Clean 负例；但只有一个 9 节点正例，尚未完成同预算、no-feedback、no-PUCT 与多 carrier 比较。</p>
            </aside>
          </div>
          <div className="critical-gap latest-gap"><CheckCircle2 aria-hidden="true" /><div><strong>端到端机制可行</strong><p>Productive 用 2 个真实 root 窗口组成精确三来源证明，Clean 保持 Unknown。13 次 XHub 调用、48,885 tokens；结果证明接口真实接通，不证明 GraphPUCT、LFP 或 state sharing 各自带来优势。</p></div></div>
        </section>

        <section id="confirm-results" className="content-section section-anchor">
          <div className="section-heading"><div><span className="section-kicker">Current evidence</span><h2>只看两组仍有决策价值的结果</h2></div><p>六档 Pure Baseline 说明局部结构化聚合值得做；9 节点真实闭环说明在线搜索版本确实可运行。</p></div>

          <div className="latest-table-scroll" role="region" aria-label="六档 Productive Pure Baseline 结果，可横向滚动">
            <table className="latest-dataset-table"><thead><tr><th scope="col">Pure Baseline · 3/5/7/9/11/25</th><th scope="col">严格答案 + 证明</th><th scope="col">calls</th><th scope="col">tokens</th></tr></thead><tbody>{pureBaselineRows.map((row) => <tr key={row[0]}><th scope="row"><strong>{row[0]}</strong></th><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td></tr>)}</tbody></table>
          </div>
          <p className="table-note"><CircleAlert aria-hidden="true" /> 每个尺寸只有一个 Productive carrier。LEA-LFP 是固定局部窗口、透明合并与 end-only LFP；它没有 PUCT、在线反馈或动态停止，而且用了约 5 倍 tokens，因此不能直接叫“慢思考胜利”。</p>

          <div className="latest-table-scroll" role="region" aria-label="9 节点 Productive 真实闭环对照，可横向滚动">
            <table className="latest-dataset-table"><thead><tr><th scope="col">9-node Productive · exploratory</th><th scope="col">严格答案 + 证明</th><th scope="col">calls</th><th scope="col">tokens</th></tr></thead><tbody>{realLoopSize9Rows.map((row) => <tr key={row[0]}><th scope="row"><strong>{row[0]}</strong></th><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td></tr>)}</tbody></table>
          </div>
          <p className="table-note"><CircleAlert aria-hidden="true" /> GraphPUCT 比 full-cover LEA 少 1 call / 3,312 tokens，但 n=1；Productive 的 state-sharing hit 为 0，也没有 no-feedback 消融。这只能算值得扩大验证的信号。</p>
        </section>

        <section id="confirm-engine" className="content-section section-anchor">
          <div className="section-heading"><div><span className="section-kicker">Implemented loop</span><h2>真实 LLM 在搜索内部，而不是搜索后补跑</h2></div><p>每条 simulation 都建立独立知识分支；只有最终 root action 可以提交到真实状态。</p></div>
          <div className="v2-pipeline-canvas" aria-label="GraphPUCT、真实 LLM 与 online LFP 闭环">
            {engineStages.map((stage, index) => {
              const Icon = stage.icon;
              return <div className="v2-pipeline-item" key={stage.title}><span>{String(index + 1).padStart(2, "0")} · {stage.label}</span><Icon aria-hidden="true" /><strong>{stage.title}</strong><p>{stage.text}</p>{index < engineStages.length - 1 && <ArrowRight className="v2-stage-arrow" aria-hidden="true" />}</div>;
            })}
          </div>
          <div className="access-boundary compact-access">
            <div className="access-column allowed"><h3><CheckCircle2 aria-hidden="true" /> 可以提交</h3><ul><li>真实执行的 root window</li><li>通过来源与 schema gate 的 facts / rules</li><li>由 committed program 推出的 closure</li></ul></div>
            <div className="access-divider"><ShieldCheck aria-hidden="true" /><span>COMMIT<br />BOUNDARY</span></div>
            <div className="access-column blocked"><h3><CircleAlert aria-hidden="true" /> 不能提交</h3><ul><li>未执行窗口的隐藏解析</li><li>丢弃 simulation 的虚拟证据</li><li>没有来源锚点的模型猜测</li></ul></div>
          </div>
        </section>

        <section id="confirm-data" className="content-section section-anchor">
          <div className="section-heading"><div><span className="section-kicker">Controlled carriers</span><h2>真实 SCC 载体 + 最小可验证注入</h2></div><p>冻结真实 BGB 节点、边和原文窗口，只向现有窗口追加 seed / bridge / witness；人工机制结果与自然外测分开。</p></div>
          <div className="v2-pipeline-canvas intervention-pipeline" aria-label="受控 SCC 注入与 gold 生成流程">
            <div className="v2-pipeline-item"><span>01 · 真实载体</span><Network aria-hidden="true" /><strong>freeze document SCC</strong><p>使用原生 {sccSizeLadder.join(" / ")} 节点 SCC。</p><ArrowRight className="v2-stage-arrow" aria-hidden="true" /></div>
            <div className="v2-pipeline-item"><span>02 · 最小干预</span><GitMerge aria-hidden="true" /><strong>seed · bridge · witness</strong><p>三个来源分散，任何单窗都不足。</p><ArrowRight className="v2-stage-arrow" aria-hidden="true" /></div>
            <div className="v2-pipeline-item"><span>03 · 精确 gold</span><ShieldCheck aria-hidden="true" /><strong>LFP + provenance</strong><p>验证 closure、最小来源集和删除必要性。</p></div>
          </div>
          <div className="v3-condition-grid" aria-label="五组配对干预">
            {interventionConditions.map((condition) => <article key={condition.id}><span>{condition.id}</span><h3>{condition.title}</h3><p>{condition.text}</p></article>)}
          </div>
          <p className="table-note"><CircleAlert aria-hidden="true" /> P / D / B / C 共享冻结的 document SCC；Matched-DAG 是单独物理拓扑控制。positive Horn LFP 只做单调累积，不表示“旧 closure 被撤回”。</p>
        </section>

        <section id="confirm-next" className="content-section section-anchor">
          <div className="section-heading"><div><span className="section-kicker">Next decisive run</span><h2>接下来只过四道 Gate</h2></div><p>所有方法使用同一 base model 和 source access，并报告真实 calls、tokens、latency 与 proof。</p></div>
          <ol className="v2-gate-grid">{nextGates.map((gate) => <li key={gate.id}><span>{gate.id}</span><h3>{gate.title}</h3><p>{gate.test}</p><small><b>GO：</b>{gate.go}<br /><b>NO-GO：</b>{gate.fail}</small></li>)}</ol>
        </section>

        <footer className="site-footer"><div><span className="brand-mark">E</span><div><strong>Current Experiment</strong><p>Pure Baseline · real GraphPUCT loop · next gates</p></div></div><a href="/review">查看文献与数据 →</a></footer>
      </main>
    </div>
  );
}
