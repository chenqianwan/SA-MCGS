export const interventionConditions = [
  {
    id: "P",
    title: "Productive",
    text: "seed、bridge、witness 齐全；只有跨窗口 closure 后才能证明 query。",
  },
  {
    id: "D",
    title: "Decoy seed",
    text: "只替换实体或 guard；表面相似，但 cycle 无法启动。",
  },
  {
    id: "B",
    title: "Broken / inactive",
    text: "省略或用 no-op 替换拟注入的必要 bridge；不删除原始窗口内容。",
  },
  {
    id: "C",
    title: "Clean SCC",
    text: "原始 SCC 不注入；测量误报与模板 shortcut。",
  },
  {
    id: "G",
    title: "Matched DAG",
    text: "单独构造物理拓扑对照；保持程序、proof depth 与标签一致。",
  },
] as const;

export const sccSizeLadder = [3, 5, 7, 9, 11, 25] as const;

export const nextGates = [
  {
    id: "G1",
    title: "同模型 compute scaling",
    test: "固定 source access，按真实 calls / tokens 比较完整 success–compute 曲线。",
    go: "相对最强 compute-matched 通用 LLM baseline 的 AUC 与 proof recovery 均提升。",
    fail: "若只是消耗更多 token，停止“慢思考优势”主张。",
  },
  {
    id: "G2",
    title: "LFP 因果贡献",
    test: "比较 symbolic memory、end-only LFP、online LFP no-feedback 与完整 feedback。",
    go: "跨窗口 proof recovery 或 cost-to-proof 有稳定改善。",
    fail: "若 memory-only 持平，论文改为 symbolic memory，不主打 LFP。",
  },
  {
    id: "G3",
    title: "搜索策略必要性",
    test: "所有 controller 共用 parser、KB、LFP、reward 与预算，对比 Greedy / Beam / PUCT。",
    go: "PUCT 在准确率或成本 Pareto 上有独立收益。",
    fail: "若 Greedy / Beam 持平，采用更简单的 deterministic controller。",
  },
  {
    id: "G4",
    title: "真实循环文档外测",
    test: "在人审、非模板化法律或合同 SCC 上验证跨窗口 source-linked proofs。",
    go: "自然子集保持趋势，且所有 proof 可回溯到原文。",
    fail: "若只在受控 Horn 注入成立，收缩为 mechanism 结论。",
  },
] as const;

export const canonicalPosition = [
  "Paper 2 保留 SA-MCGS 在真实循环文档图上的 local-window GraphPUCT 搜索。",
  "只有已执行并通过来源验证的窗口可以写入 committed symbolic KB；exact LFP 产生的新事实和 proof obligations 在线反馈下一轮搜索。",
  "当前真实 GraphPUCT + XHub LLM + LFP 闭环已在一个 9-node Productive 与一个 Clean carrier 上跑通，但同预算优势、各组件因果贡献和自然任务迁移仍待验证。",
].join("\n");
