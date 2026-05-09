import React, { useState } from 'react';
import { motion } from 'framer-motion';
import {
  FileText, Brain, Network, Scissors, GitBranch, BarChart3,
  Search, ShieldAlert, CheckCircle, ArrowDown, ChevronDown, ChevronUp,
  Layers, FlaskConical, Beaker,
} from 'lucide-react';

const steps = [
  {
    id: 1,
    title: 'Legal Graph Input',
    subtitle: 'Data Layer',
    icon: FileText,
    color: 'bg-slate-700',
    borderColor: 'border-slate-500',
    textColor: 'text-slate-300',
    details: [
      'QuantLaw DE 2019: pre-built cross-reference graphs (NetworkX DiGraph)',
      'Raw contract text → LLM clause parsing (alternative path)',
      'QuantLawLoader: filter hierarchy edges, keep cross-references only',
      'pipeline.run_from_graph() — skip parsing, start from Step 3',
    ],
    tag: 'DATA',
    tagColor: 'bg-slate-600',
  },
  {
    id: 2,
    title: 'Clause Extraction & Classification',
    subtitle: 'LLM Extraction',
    icon: Brain,
    color: 'bg-blue-900',
    borderColor: 'border-blue-500',
    textColor: 'text-blue-300',
    details: [
      'Clause segmentation via LLM or heuristic',
      'ClauseType classification: Def → Obl → Cond → Rem → Lim',
      'Pairwise dependency extraction → directed edges',
      '(Skipped for QuantLaw pre-built graphs)',
    ],
    tag: 'LLM',
    tagColor: 'bg-blue-700',
  },
  {
    id: 3,
    title: 'Domain-Informed Graph Pruning',
    subtitle: '⭐ Core Contribution',
    icon: Scissors,
    color: 'bg-amber-900',
    borderColor: 'border-amber-400',
    textColor: 'text-amber-300',
    details: [
      '1. Noise Edge Removal: filter LLM false positives (low weight, self-loops, duplicate reasoning)',
      '2. Hierarchical Prior: enforce Def→Obl→Cond→Rem→Lim layer structure',
      '3. Information Bottleneck: min I(G\';G) − β·I(G\';Y) compression',
      'Greedy strategy: 3-stage sequential pruning',
    ],
    tag: 'NOVEL',
    tagColor: 'bg-amber-600',
    highlight: true,
  },
  {
    id: 4,
    title: 'SCC Detection (Tarjan\'s)',
    subtitle: 'Structure Decomposition',
    icon: GitBranch,
    color: 'bg-purple-900',
    borderColor: 'border-purple-500',
    textColor: 'text-purple-300',
    details: [
      'Tarjan\'s algorithm → identify non-trivial SCCs',
      'Separate graph into DAG nodes (~85%) + SCC nodes (~15%)',
      'Compute condensation DAG and topological order',
      'SCC size & density analysis',
    ],
    tag: 'ALGO',
    tagColor: 'bg-purple-700',
  },
  {
    id: 5,
    title: 'DAG Evaluation + SCC Sampling',
    subtitle: 'Dual-Path Assessment',
    icon: Layers,
    color: 'bg-sky-900',
    borderColor: 'border-sky-500',
    textColor: 'text-sky-300',
    details: [
      'DAG nodes: deterministic eval (temperature=0) in topological order',
      'Upstream context propagation along dependency edges',
      'SCC nodes: K stochastic samples (temperature>0) per SCC',
      'Joint LLM evaluation of all clauses within each SCC',
    ],
    tag: 'LLM',
    tagColor: 'bg-sky-700',
  },
  {
    id: 6,
    title: 'Three-Stage Search Tree Pruning',
    subtitle: 'Branch Reduction',
    icon: Scissors,
    color: 'bg-orange-900',
    borderColor: 'border-orange-500',
    textColor: 'text-orange-300',
    details: [
      'a) Variance Pruning: collapse low-variance SCCs (σ² ≤ threshold)',
      'b) Dominance Pruning: remove Pareto-dominated branches',
      'c) Influence Pruning: prune low-impact SCCs based on graph centrality',
      'Builds search tree with remaining active branches',
    ],
    tag: 'PRUNE',
    tagColor: 'bg-orange-700',
  },
  {
    id: 7,
    title: 'MCGS Search (UCB1)',
    subtitle: '⭐ Core Algorithm',
    icon: Search,
    color: 'bg-indigo-900',
    borderColor: 'border-indigo-400',
    textColor: 'text-indigo-300',
    details: [
      'Monte Carlo Graph Search on SCC search tree',
      'UCB1 branch selection: exploitation + exploration balance',
      'Reward = 0.5·max_risk + 0.3·avg_risk + 0.2·√var',
      'Early stopping on reward convergence',
    ],
    tag: 'NOVEL',
    tagColor: 'bg-indigo-600',
    highlight: true,
  },
  {
    id: 8,
    title: 'Aggregation & Risk Identification',
    subtitle: 'Output Layer',
    icon: ShieldAlert,
    color: 'bg-red-900',
    borderColor: 'border-red-500',
    textColor: 'text-red-300',
    details: [
      'Statistical aggregation: DAG deterministic + SCC collapsed + MCGS rollouts',
      'Per-clause: mean / median / max / std risk scores',
      'SCC risk patterns: circular amplification, hidden dependency, complex cycle',
      'High-risk & high-uncertainty clause identification',
    ],
    tag: 'OUTPUT',
    tagColor: 'bg-red-700',
  },
];

const experimentPhases = [
  {
    label: 'QuantLaw DE 2019',
    desc: '4500 nodes · 85% DAG · 15% SCC',
    color: 'bg-slate-800',
    border: 'border-slate-500',
  },
  {
    label: 'Counterfactual Perturbation',
    desc: 'Type A/B/C on DAG + SCC nodes',
    color: 'bg-violet-900',
    border: 'border-violet-500',
  },
  {
    label: 'Ablation Study',
    desc: 'Full / No-Prune / No-MCGS / Direct-LLM',
    color: 'bg-cyan-900',
    border: 'border-cyan-500',
  },
  {
    label: 'Publication Figures',
    desc: 'Detection rates · Risk delta · Convergence',
    color: 'bg-emerald-900',
    border: 'border-emerald-500',
  },
];

const perturbTypes = [
  {
    type: 'Type A',
    name: 'Semantic Contradiction',
    target: 'DAG + SCC',
    difficulty: 'Easy',
    mcgs: 'Detect',
    llm: 'Detect',
    color: 'text-green-400',
  },
  {
    type: 'Type B',
    name: 'Circular Precondition Deadlock',
    target: 'SCC only',
    difficulty: 'Medium',
    mcgs: 'Detect',
    llm: 'Partial',
    color: 'text-yellow-400',
  },
  {
    type: 'Type C',
    name: 'Stealthy Scope Expansion',
    target: 'SCC only',
    difficulty: 'Hard',
    mcgs: 'Detect',
    llm: 'Miss',
    color: 'text-red-400',
  },
];

export default function WorkflowDiagram() {
  const [expandedStep, setExpandedStep] = useState(3);

  return (
    <div className="min-h-screen bg-gray-950 text-white p-4 md:p-8">
      <div className="max-w-4xl mx-auto">
        {/* Title */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mb-10"
        >
          <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">
            SA-MCGS: Structure-Aware Monte Carlo Graph Search
          </h1>
          <p className="text-gray-400 text-sm md:text-base">
            Legal Risk Evaluation via Graph Pruning, SCC Analysis & MCGS
          </p>
        </motion.div>

        {/* Main Pipeline */}
        <div className="space-y-3">
          {steps.map((step, idx) => {
            const Icon = step.icon;
            const isExpanded = expandedStep === step.id;
            return (
              <motion.div
                key={step.id}
                initial={{ opacity: 0, x: -30 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.08 }}
              >
                {idx > 0 && (
                  <div className="flex justify-center py-1">
                    <ArrowDown className="text-gray-600" size={20} />
                  </div>
                )}

                <div
                  className={`rounded-xl border-2 ${step.highlight ? 'border-amber-400 shadow-lg shadow-amber-900/30' : step.borderColor} ${step.color} cursor-pointer transition-all duration-200 hover:scale-[1.01]`}
                  onClick={() => setExpandedStep(isExpanded ? null : step.id)}
                >
                  <div className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg ${step.highlight ? 'bg-amber-800' : 'bg-black/30'}`}>
                          <Icon size={22} className={step.textColor} />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono text-gray-500">
                              Step {step.id}
                            </span>
                            <span className={`text-xs font-mono px-2 py-0.5 rounded ${step.tagColor} text-white`}>
                              {step.tag}
                            </span>
                            {step.highlight && (
                              <span className="text-xs font-mono px-2 py-0.5 rounded bg-amber-500 text-black font-bold">
                                KEY
                              </span>
                            )}
                          </div>
                          <h3 className="font-bold text-white text-sm md:text-base mt-1">{step.title}</h3>
                          <p className={`text-xs ${step.textColor}`}>{step.subtitle}</p>
                        </div>
                      </div>
                      <div className="text-gray-500">
                        {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                      </div>
                    </div>

                    {isExpanded && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        className="mt-3 pl-12"
                      >
                        <div className="space-y-1.5">
                          {step.details.map((detail, i) => (
                            <div key={i} className="flex items-start gap-2 text-xs md:text-sm text-gray-300">
                              <span className={`mt-1 w-1.5 h-1.5 rounded-full ${step.textColor} bg-current flex-shrink-0`} />
                              <span>{detail}</span>
                            </div>
                          ))}
                        </div>
                      </motion.div>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* Experiment Design */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.8 }}
          className="mt-8"
        >
          <div className="flex justify-center py-2">
            <ArrowDown className="text-gray-600" size={20} />
          </div>

          <div className="rounded-xl border-2 border-violet-500 bg-violet-950 p-4">
            <div className="flex items-center gap-2 mb-4">
              <FlaskConical size={20} className="text-violet-400" />
              <h3 className="font-bold text-violet-300 text-sm md:text-base">
                Counterfactual Perturbation Experiment
              </h3>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-violet-700 text-white ml-1">
                EXPERIMENT
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {experimentPhases.map((ep, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.9 + i * 0.1 }}
                  className={`rounded-lg border ${ep.border} ${ep.color} p-3 text-center`}
                >
                  <div className="font-bold text-white text-xs md:text-sm">{ep.label}</div>
                  <div className="text-gray-400 text-xs mt-1">{ep.desc}</div>
                </motion.div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* Perturbation Type Matrix */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.0 }}
          className="mt-4 rounded-xl border border-gray-700 bg-gray-900 p-4"
        >
          <div className="flex items-center gap-2 mb-3">
            <Beaker size={16} className="text-gray-400" />
            <h3 className="font-bold text-gray-300 text-sm">Perturbation Types & Expected Results</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs md:text-sm">
              <thead>
                <tr className="text-gray-500 border-b border-gray-700">
                  <th className="text-left py-2 pr-3">Type</th>
                  <th className="text-left py-2 pr-3">Target</th>
                  <th className="text-left py-2 pr-3">Difficulty</th>
                  <th className="text-center py-2 pr-3">SA-MCGS</th>
                  <th className="text-center py-2">Direct LLM</th>
                </tr>
              </thead>
              <tbody>
                {perturbTypes.map((p, i) => (
                  <tr key={i} className="border-b border-gray-800">
                    <td className="py-2.5 pr-3">
                      <span className={`font-bold ${p.color}`}>{p.type}</span>
                      <div className="text-gray-500 text-xs">{p.name}</div>
                    </td>
                    <td className="py-2.5 pr-3 text-gray-300">{p.target}</td>
                    <td className="py-2.5 pr-3">
                      <span className={p.color}>{p.difficulty}</span>
                    </td>
                    <td className="py-2.5 pr-3 text-center">
                      <span className="text-green-400 font-bold">{p.mcgs}</span>
                    </td>
                    <td className="py-2.5 text-center">
                      <span className={p.llm === 'Miss' ? 'text-red-400' : p.llm === 'Partial' ? 'text-yellow-400' : 'text-green-400'}>
                        {p.llm}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.div>

        {/* Theoretical Framing */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1.2 }}
          className="mt-4 rounded-xl border border-gray-700 bg-gray-900 p-4"
        >
          <h3 className="font-bold text-gray-300 text-sm mb-3">Theoretical Framing</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
            <div className="bg-gray-800 rounded-lg p-3 border border-gray-700">
              <div className="text-amber-400 font-bold mb-1">Graph Denoising</div>
              <div className="text-gray-400">LLM extraction noise creates false SCCs. Pruning removes O(k) spurious merges.</div>
            </div>
            <div className="bg-gray-800 rounded-lg p-3 border border-gray-700">
              <div className="text-amber-400 font-bold mb-1">Hierarchical Prior</div>
              <div className="text-gray-400">Def→Obl→Cond→Rem→Lim. Enforce domain knowledge via edge direction constraints.</div>
            </div>
            <div className="bg-gray-800 rounded-lg p-3 border border-gray-700">
              <div className="text-amber-400 font-bold mb-1">Information Bottleneck</div>
              <div className="text-gray-400">min I(G';G) − β·I(G';Y). Compress graph while retaining task-relevant signal.</div>
            </div>
          </div>
        </motion.div>

        <p className="text-center text-gray-600 text-xs mt-6">Click each pipeline step to expand details</p>
      </div>
    </div>
  );
}
